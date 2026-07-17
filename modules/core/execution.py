"""
Firmware-delegated execution: the board runs everything, the host proxies
commands and observes status.

The FluidNC firmware owns kinematics, `.thr` playback, playlist sequencing,
pre-execution clears, quiet hours and auto-home. This module is the host's
entire runtime layer on top of that:

  - Commands: each user action is one or a few HTTP calls to the board
    ($Sand/Run, $Playlist/Run, /sand_stop, /sand_pause, /sand_resume,
    $Playlist/Skip, /sand_feed, /sand_goto).
  - Truth: /sand_status is the single source of runtime state. One observer
    task polls it, translates it into the frontend's /ws/status contract,
    detects edges (file transitions -> play history, Hold -> pause accounting,
    clearing -> clear-speed shim, run end -> state reset) and broadcasts.
  - Context: the host remembers what run *it* started (RunContext) to fill the
    contract fields the board doesn't report (playlist files, run mode).

No sequencing happens on the host. If the board reboots or the backend
restarts mid-run, the observer resynchronizes from /sand_status alone.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Literal, Optional

from modules.connection import connection_manager
from modules.core.state import state

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Board log harvesting (/sand_log)
#
# The board keeps only a small RAM ring buffer (~8 KB) that is lost on reboot.
# The observer periodically pulls it and merges new lines (keyed by the
# "[+<uptime>]" prefix) into a persistent host-side file, so users get table
# history that outlives reboots — same idea as the mobile app's table log.
# ---------------------------------------------------------------------------

BOARD_LOG_FILE = "board_log.txt"
BOARD_LOG_MAX_LINES = 4000
BOARD_LOG_HARVEST_EVERY = 300.0  # seconds


def _log_uptime(line: str) -> Optional[float]:
    """'[+1104] [MSG:...]' -> 1104.0; None for lines without the prefix."""
    if not line.startswith("[+"):
        return None
    end = line.find("]")
    if end < 2:
        return None
    try:
        return float(line[2:end])
    except ValueError:
        return None


def merge_board_log(fetched: list[str], last_uptime: float, last_count: int) -> tuple[list[str], float, int, bool]:
    """Return (new_lines, new_last_uptime, new_last_count, restarted).

    Lines strictly newer than last_uptime are new; at exactly last_uptime we
    skip the `last_count` occurrences already stored (the ring can hold several
    lines within the same second). A drop in max uptime means the board
    rebooted — everything is new again.
    """
    parsed = [(u, ln) for ln in fetched if ln.strip() and (u := _log_uptime(ln)) is not None]
    if not parsed:
        return [], last_uptime, last_count, False
    max_uptime = max(u for u, _ in parsed)
    restarted = max_uptime < last_uptime
    if restarted:
        last_uptime, last_count = -1.0, 0

    new_lines: list[str] = []
    seen_at_last = 0
    for u, ln in parsed:
        if u > last_uptime:
            new_lines.append(ln)
        elif u == last_uptime:
            seen_at_last += 1
            if seen_at_last > last_count:
                new_lines.append(ln)
    new_count = sum(1 for u, _ in parsed if u == max_uptime)
    return new_lines, max_uptime, new_count, restarted


# Firmware clear modes; legacy host values are mapped onto them.
CLEAR_MODES = ("none", "adaptive", "in", "out", "sideway", "random")
_LEGACY_CLEAR = {
    "clear_from_in": "in",
    "clear_from_out": "out",
    "clear_sideway": "sideway",
    "clear_in": "in",
    "clear_out": "out",
}


class ExecutionError(Exception):
    """Raised when the board rejects or times out on an execution command."""


@dataclass
class RunContext:
    """Host-side knowledge about the run we started (not board truth)."""
    kind: Literal["pattern", "playlist"]
    playlist_name: Optional[str] = None
    files: Optional[list] = None  # host paths, unshuffled mirror order
    run_mode: str = "single"      # frontend value: 'single' | 'indefinite'
    shuffle: bool = False
    clear_pattern: str = "none"
    started_at: float = field(default_factory=time.time)


current_run: Optional[RunContext] = None


def map_clear_mode(value) -> str:
    """Map a frontend/legacy clear value onto the firmware's clear modes."""
    if not value:
        return "none"
    value = str(value).lower()
    if value in CLEAR_MODES:
        return value
    if value in _LEGACY_CLEAR:
        return _LEGACY_CLEAR[value]
    logger.warning(f"Unknown clear mode '{value}', using none")
    return "none"


def _state(st: Optional[dict]) -> str:
    """Machine state without the GRBL substate suffix ('Hold:0' -> 'Hold')."""
    return ((st or {}).get("state") or "").split(":", 1)[0]


def _from_sd_path(sd_path: str) -> Optional[str]:
    """Map a board SD path ('/patterns/x.thr', '/sd/patterns/x.thr') to the
    host-relative path ('./patterns/x.thr') the frontend/history expect."""
    if not sd_path:
        return None
    p = sd_path.replace("\\", "/")
    if p.startswith("/sd/"):
        p = p[3:]
    if not p.startswith("/"):
        p = "/" + p
    return "." + p


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _require_conn():
    if not state.conn or not state.conn.is_connected():
        raise ExecutionError("Connection not established")
    return state.conn


async def _wait_for_idle(timeout: float = 15.0) -> bool:
    """Poll the board until it reports Idle (used before idle-gated NVS writes)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            st = await asyncio.to_thread(state.conn.get_status)
            if _state(st) == "Idle" and not st.get("running"):
                return True
        except Exception as e:
            logger.debug(f"Idle wait poll failed: {e}")
        await asyncio.sleep(0.5)
    return False


async def run_pattern(file_path: str, clear_pattern: str = "none") -> None:
    """Run one pattern via $Sand/Run (firmware sequences clear -> pattern and
    aborts any current job first)."""
    global current_run
    conn = _require_conn()
    from modules.core.pattern_manager import _ensure_on_board, make_sd_path_resolver

    # Prefer a copy already on the board SD over uploading a duplicate.
    resolve_sd = make_sd_path_resolver(conn)
    sd_path = await asyncio.to_thread(resolve_sd, file_path)
    await asyncio.to_thread(_ensure_on_board, file_path, sd_path)
    try:
        await asyncio.to_thread(conn.set_feed, int(state.speed))
    except Exception as e:
        logger.warning(f"Could not set feed before run: {e}")
    mode = map_clear_mode(clear_pattern)
    await asyncio.to_thread(conn.run_pattern, sd_path, mode)

    current_run = RunContext(kind="pattern", clear_pattern=mode)
    state.current_playlist = None
    state.current_playlist_name = None
    # Optimistic; the observer confirms/corrects from /sand_status.
    state.current_playing_file = file_path
    observer.on_run_started()


async def start_playlist(playlist_name: str, run_mode: str = "single",
                         pause_time: float = 0, clear_pattern: str = "none",
                         shuffle: bool = False) -> None:
    """Run a playlist on the board via $Playlist/Run.

    The run options are the firmware's NVS $Playlist/* globals; NVS writes are
    idle-gated, so a run-while-running stops the board first.
    """
    global current_run
    conn = _require_conn()
    from modules.core import playlist_manager, board_settings
    from modules.core.pattern_manager import THETA_RHO_DIR, _ensure_on_board, make_sd_path_resolver

    playlist = playlist_manager.get_playlist(playlist_name)
    if not playlist:
        raise ExecutionError(f"Playlist '{playlist_name}' not found")
    files = playlist["files"]
    if not files:
        raise ExecutionError(f"Playlist '{playlist_name}' is empty")
    host_paths = [os.path.join(THETA_RHO_DIR, f) for f in files]

    # Idle-gate: NVS settings writes are rejected mid-motion.
    st = None
    try:
        st = await asyncio.to_thread(conn.get_status)
    except Exception:
        pass
    if st and (st.get("running") or _state(st) not in ("Idle", "Alarm")):
        await asyncio.to_thread(conn.stop)
        if not await _wait_for_idle(15.0):
            raise ExecutionError("Table is busy and did not stop in time")

    mode = map_clear_mode(clear_pattern)
    for key, value in (
        ("Playlist/Mode", "loop" if run_mode == "indefinite" else "single"),
        ("Playlist/Shuffle", "ON" if shuffle else "OFF"),
        ("Playlist/PauseTime", max(0, int(pause_time or 0))),
        ("Playlist/ClearPattern", mode),
    ):
        await asyncio.to_thread(conn.set_setting, key, value)

    # The board needs the playlist file before Run; patterns can trail behind
    # (each one plays for minutes) except the first, which is ensured now.
    # One shared resolver so the playlist lines and the uploads agree on
    # paths, and existing board copies are reused instead of duplicated.
    resolve_sd = make_sd_path_resolver(conn)
    await asyncio.to_thread(
        board_settings.mirror_playlist, playlist_name, files, conn, False, resolve_sd)
    first_sd = await asyncio.to_thread(resolve_sd, host_paths[0])
    await asyncio.to_thread(_ensure_on_board, host_paths[0], first_sd)

    def _mirror_rest():
        for p in host_paths[1:]:
            _ensure_on_board(p, resolve_sd(p))
    import threading
    threading.Thread(target=_mirror_rest, daemon=True).start()

    try:
        await asyncio.to_thread(conn.set_feed, int(state.speed))
    except Exception as e:
        logger.warning(f"Could not set feed before playlist: {e}")
    await asyncio.to_thread(conn.run_command, f"$Playlist/Run={playlist_name}")

    current_run = RunContext(
        kind="playlist", playlist_name=playlist_name, files=host_paths,
        run_mode=run_mode, shuffle=shuffle, clear_pattern=mode,
    )
    state.current_playlist = host_paths
    state.current_playlist_name = playlist_name
    state.playlist_mode = run_mode
    observer.on_run_started()
    logger.info(f"Started playlist '{playlist_name}' on the board "
                f"(mode={run_mode}, shuffle={shuffle}, pause={pause_time}s, clear={mode})")


async def stop(force: bool = False) -> bool:
    """Clean stop. Returns True once the board is Idle (always True for force)."""
    try:
        conn = _require_conn()
        await asyncio.to_thread(conn.stop)
    except Exception as e:
        if not force:
            raise ExecutionError(f"Stop failed: {e}")
        logger.warning(f"Force stop: board stop failed ({e}), resetting host state anyway")
    if force:
        _reset_run_state()
        observer.reset()
        return True
    return await _wait_for_idle(10.0)


async def pause() -> None:
    conn = _require_conn()
    await asyncio.to_thread(conn.pause)


async def resume() -> None:
    conn = _require_conn()
    await asyncio.to_thread(conn.resume)


async def skip() -> bool:
    """Skip the current pattern: $Playlist/Skip for playlists (also overrides
    quiet hours for one pattern); stopping is the 'skip' of a single pattern."""
    conn = _require_conn()
    st = observer.last_raw or {}
    pl = st.get("playlist") or {}
    if pl.get("active"):
        await asyncio.to_thread(conn.skip)
        return True
    if st.get("running"):
        await asyncio.to_thread(conn.stop)
        return True
    return False


async def set_speed(speed: float) -> None:
    conn = _require_conn()
    state.speed = speed
    await asyncio.to_thread(conn.set_feed, int(speed))


def _reset_run_state() -> None:
    global current_run
    current_run = None
    state.current_playing_file = None
    state.current_playlist = None
    state.current_playlist_name = None
    state.pause_requested = False
    state.pause_time_remaining = 0
    state.execution_progress = None


# ---------------------------------------------------------------------------
# Status translation: /sand_status -> the frontend's /ws/status contract
# ---------------------------------------------------------------------------

def _board_health(st: Optional[dict]) -> dict:
    """Board health telemetry for the /ws/status payload (firmware API.md).

    Prefers the live /sand_status values; falls back to the last-known values
    mirrored into state so the UI keeps a reading across a dropped poll. Older
    firmware omits these keys — they surface as null.
    """
    def pick(key: str, attr: str):
        if st and key in st:
            return st[key]
        return getattr(state, attr, None)

    return {
        "heap": pick("heap", "board_heap"),
        "heap_min": pick("heap_min", "board_heap_min"),
        "heap_largest": pick("heap_largest", "board_heap_largest"),
        "last_reset": pick("last_reset", "board_last_reset"),
        "sd_ok": pick("sd_ok", "board_sd_ok"),
        "uptime": pick("uptime", "board_uptime"),
    }


def translate_status(st: Optional[dict], obs: Optional["BoardObserver"] = None,
                     now: Optional[float] = None) -> dict:
    """Translate a raw board status into the /ws/status data object.

    Pure given (st, observer timing, state); unit-testable with fixtures.
    """
    obs = obs or observer
    now = now if now is not None else time.time()
    connected = bool(state.conn and state.conn.is_connected())

    if st is None:
        return {
            "connection_status": connected,
            "current_file": None,
            "is_running": False,
            "is_paused": False,
            "is_alarm": False,
            "is_homing": state.is_homing,
            "sensor_homing_failed": state.sensor_homing_failed,
            "is_clearing": False,
            "speed": state.speed,
            "pause_time_remaining": 0,
            "original_pause_time": None,
            "progress": None,
            "playlist": None,
            "current_theta": state.current_theta,
            "current_rho": state.current_rho,
            "firmware_version": state.firmware_version,
            "table_type": None,
            "health": _board_health(None),
        }

    pl = st.get("playlist") or {}
    running = bool(st.get("running"))
    # GRBL states can carry a substate suffix (e.g. "Hold:0", "Door:1").
    machine_state = _state(st)
    clearing = bool(pl.get("clearing"))
    pause_remaining = pl.get("pause_remaining", -1)
    pause_total = pl.get("pause_total", -1)

    current_file = _from_sd_path(st.get("file")) if running else None

    # --- progress ---
    progress_obj = None
    if running:
        fraction = st.get("progress", -1)
        fraction = fraction if isinstance(fraction, (int, float)) and fraction >= 0 else 0
        elapsed = max(0.0, now - obs.file_started_at - obs.hold_accumulated
                      - (now - obs.hold_started_at if obs.hold_started_at else 0))
        if fraction > 0.02:
            remaining = max(0.0, elapsed / fraction - elapsed)
        elif obs.cached_history and obs.cached_history.get("actual_time_seconds"):
            remaining = max(0.0, obs.cached_history["actual_time_seconds"] - elapsed)
        else:
            remaining = None
        progress_obj = {
            "current": int(fraction * 1000),
            "total": 1000,
            "percentage": round(fraction * 100, 1),
            "elapsed_time": elapsed,
            "remaining_time": remaining,
        }
        if obs.cached_history:
            progress_obj["last_completed_time"] = obs.cached_history

    # --- playlist ---
    playlist_obj = None
    playlist_active = bool(pl.get("active"))
    ctx = current_run
    if (playlist_active and pl.get("total", 0) > 0) or (ctx and ctx.kind == "playlist"):
        files = [f for f in (state.current_playlist or [])]
        index = int(pl.get("index", 0) or 0)
        total = int(pl.get("total", 0) or 0) or len(files)
        shuffled = bool(ctx.shuffle) if ctx else False
        next_file = None
        if files and not shuffled:
            # While clearing, the "next" thing is the pattern the clear precedes.
            next_idx = index if clearing else index + 1
            if 0 <= next_idx < len(files):
                next_file = files[next_idx]
        playlist_obj = {
            "name": pl.get("name") or (ctx.playlist_name if ctx else None),
            "current_index": index,
            "total_files": total,
            "mode": (ctx.run_mode if ctx else "indefinite"),
            "files": files,
            "next_file": next_file,
            "shuffled": shuffled,
        }

    return {
        "connection_status": connected,
        "current_file": current_file,
        "is_running": running,
        "is_paused": machine_state == "Hold",
        "is_alarm": machine_state == "Alarm",
        "is_homing": machine_state == "Home" or state.is_homing,
        "sensor_homing_failed": state.sensor_homing_failed,
        "is_clearing": clearing,
        "speed": state.speed,
        "pause_time_remaining": pause_remaining if pause_remaining >= 0 else 0,
        "original_pause_time": pause_total if pause_total >= 0 else None,
        "progress": progress_obj,
        "playlist": playlist_obj,
        "current_theta": st.get("theta", state.current_theta),
        "current_rho": st.get("rho", state.current_rho),
        "firmware_version": st.get("fw") or state.firmware_version,
        "table_type": None,
        "health": _board_health(st),
    }


# ---------------------------------------------------------------------------
# Observer: single poll loop — edges, history, shims, broadcast
# ---------------------------------------------------------------------------

class BoardObserver:
    """Polls /sand_status and turns transitions into host behavior."""

    POLL_ACTIVE = 1.0
    POLL_IDLE = 2.0
    OFFLINE_GRACE = 3  # consecutive failures before a run is declared over
    RECONNECT_EVERY = 15.0  # seconds between reconnect/relocate attempts while offline

    def __init__(self):
        self.prev: Optional[dict] = None
        self.last_raw: Optional[dict] = None
        self.last_translated: dict = {}
        self.file_started_at: float = 0.0
        self.hold_started_at: Optional[float] = None
        self.hold_accumulated: float = 0.0
        self.last_progress: float = -1.0
        self.cached_history: Optional[dict] = None
        self._clear_speed_saved: Optional[float] = None
        self._was_quiet_wled_off = False
        self._fail_count = 0
        self._tick = 0
        self._last_reconnect = 0.0
        self._task: Optional[asyncio.Task] = None
        # True while a firmware OTA is in flight: the board's web server is
        # single-threaded, so concurrent polls would wedge the flash upload.
        self.suspended = False
        # Board log harvest cursor (see merge_board_log)
        self._log_last_uptime = -1.0
        self._log_last_count = 0
        self._last_log_harvest = 0.0
        self._log_cursor_loaded = False
        # Set by main.py to fan out to /ws/status clients (avoids circular import).
        self.on_status: Optional[Callable] = None

    def reset(self) -> None:
        self.prev = None
        self.file_started_at = 0.0
        self.hold_started_at = None
        self.hold_accumulated = 0.0
        self.last_progress = -1.0
        self.cached_history = None
        self._clear_speed_saved = None

    def on_run_started(self) -> None:
        """Called by the command layer so the first poll attributes time correctly."""
        self.file_started_at = time.time()
        self.hold_accumulated = 0.0
        self.hold_started_at = None
        self.last_progress = -1.0

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def astop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while True:
            interval = self.POLL_IDLE
            try:
                interval = await self._tick_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Status observer tick failed: {e}")
            await asyncio.sleep(interval)

    async def _tick_once(self) -> float:
        if self.suspended:
            return self.POLL_IDLE
        st = None
        if state.conn and state.conn.is_connected():
            try:
                st = await asyncio.to_thread(connection_manager.poll_status_once)
            except Exception as e:
                logger.debug(f"Status poll failed: {e}")
        await self.process(st)
        if st is None:
            await self._maybe_reconnect()
        active = bool(st and (st.get("running") or (st.get("playlist") or {}).get("active")
                              or _state(st) in ("Hold", "Home", "Jog")))
        return self.POLL_ACTIVE if active else self.POLL_IDLE

    # -- reconnect / DHCP relocate -------------------------------------------

    async def _maybe_reconnect(self) -> None:
        """While the board is unreachable, periodically retry the saved address
        and — when DHCP has moved the board — relocate to the mDNS entry with
        the same MAC (fallback: same hostname). Never homes; the board kept its
        own position, only its IP changed."""
        if state.user_disconnected or state.is_homing or state.board_locked:
            return
        if state.conn and state.conn.is_connected() and self._fail_count < self.OFFLINE_GRACE:
            return
        now = time.time()
        if now - self._last_reconnect < self.RECONNECT_EVERY:
            return
        self._last_reconnect = now
        try:
            await asyncio.to_thread(self._reconnect_sync)
        except Exception as e:
            logger.debug(f"Reconnect attempt failed: {e}")

    def _reconnect_sync(self) -> None:
        from modules.connection.fluidnc_client import FluidNCClient
        from modules.core.mdns_discovery import discovery

        url = connection_manager.board_url()
        probe = FluidNCClient(url, api_key=state.board_api_key)
        if probe.reachable():
            logger.info(f"Board back online at {url} — reconnecting")
            state.conn = probe
            state.board_locked = False
            state.port = url
            connection_manager.device_init(False)
            return
        if probe.locked:
            state.board_locked = True
            logger.warning(f"Board at {url} now rejects us (401) — password required")
            return

        # Saved address is dead: look for the same hardware elsewhere on the LAN.
        target = None
        boards = discovery.get_boards()
        if state.board_mac:
            target = next((b for b in boards if b.get("mac") == state.board_mac), None)
        if target is None and state.board_hostname:
            hn = state.board_hostname.lower()
            target = next(
                (b for b in boards if (b.get("hostname") or "").lower() == hn), None)
        if target is None or target["url"] == url:
            return
        probe = FluidNCClient(target["url"], api_key=state.board_api_key)
        if not probe.reachable():
            return
        logger.info(f"Board moved (DHCP): relocating from {url} to {target['url']} "
                    f"(matched by {'mac' if state.board_mac else 'hostname'})")
        state.board_url = target["url"]
        state.port = target["url"]
        state.conn = probe
        state.board_locked = False
        state.save()
        connection_manager.device_init(False)

    # -- core (sync-friendly for tests; only I/O bits are awaited) ----------

    async def process(self, st: Optional[dict], now: Optional[float] = None) -> dict:
        """One observation step: edge detection + translation + broadcast."""
        now = now if now is not None else time.time()

        if st is None:
            self._fail_count += 1
            if self._fail_count == self.OFFLINE_GRACE and self.prev is not None:
                # Board gone: close out the run without claiming completion.
                logger.warning("Board unreachable — closing out the observed run")
                self._close_file(self.prev, now, aborted=True)
                _reset_run_state()
                self.reset()
        else:
            if self._fail_count >= self.OFFLINE_GRACE:
                # Just recovered: pull the board log promptly (it may hold the
                # reboot/crash story we missed while offline).
                self._last_log_harvest = 0.0
            self._fail_count = 0
            if self.prev is not None and st.get("uptime", 0) < self.prev.get("uptime", 0):
                logger.warning("Board rebooted mid-observation — resetting run context")
                _reset_run_state()
                self.reset()
            self._detect_edges(st, now)
            self.prev = st
            self.last_raw = st

        await self._quiet_hours_wled(now)

        if (st is not None and state.conn and state.conn.is_connected()
                and now - self._last_log_harvest > BOARD_LOG_HARVEST_EVERY):
            self._last_log_harvest = now
            asyncio.ensure_future(asyncio.to_thread(self._harvest_board_log_sync))

        self._tick += 1
        if self._tick % 30 == 0 and state.conn and state.conn.is_connected():
            from modules.core import board_settings
            try:
                settings_map = await asyncio.to_thread(state.conn.get_settings)
                board_settings.adopt_still_sands(settings_map)
                board_settings.adopt_auto_home(settings_map)
            except Exception as e:
                logger.debug(f"Board settings adopt failed: {e}")
            # Playlists change rarely and adopting reads every file — slower cadence.
            if self._tick % 300 == 0:
                asyncio.ensure_future(asyncio.to_thread(board_settings.adopt_board_playlists))

        self.last_translated = translate_status(st, self, now)
        # Mirror the progress 4-tuple for the MQTT handler, which unpacks it.
        prog = self.last_translated.get("progress")
        state.execution_progress = (
            (prog["current"], prog["total"], prog["remaining_time"], prog["elapsed_time"])
            if prog else None
        )
        if self.on_status:
            try:
                await self.on_status(self.last_translated)
            except Exception as e:
                logger.debug(f"Status broadcast failed: {e}")
        return self.last_translated

    # -- board log harvest ---------------------------------------------------

    def _load_log_cursor(self) -> None:
        """Recover the merge cursor from the stored file after a backend
        restart, so we don't re-append the board's whole ring buffer."""
        self._log_cursor_loaded = True
        try:
            with open(BOARD_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                tail = f.readlines()[-200:]
        except FileNotFoundError:
            return
        last_uptime, count = -1.0, 0
        for line in tail:
            # Stored lines look like "2026-07-12 17:00:03 [+1104] [MSG:...]"
            idx = line.find("[+")
            u = _log_uptime(line[idx:]) if idx >= 0 else None
            if u is None:
                continue
            if u == last_uptime:
                count += 1
            else:
                # Any change (up OR down — the tail may span a board reboot)
                # moves the cursor: later lines are newer.
                last_uptime, count = u, 1
        self._log_last_uptime, self._log_last_count = last_uptime, count

    def _harvest_board_log_sync(self) -> None:
        try:
            if not self._log_cursor_loaded:
                self._load_log_cursor()
            text = state.conn._get("/sand_log", timeout=5.0).text
            new, self._log_last_uptime, self._log_last_count, restarted = merge_board_log(
                text.splitlines(), self._log_last_uptime, self._log_last_count)
            if not new:
                return
            now = time.time()
            max_uptime = self._log_last_uptime
            out = []
            if restarted:
                out.append(f"--- table restarted ({time.strftime('%Y-%m-%d %H:%M:%S')}) ---")
            for ln in new:
                # Estimated wall-clock time: now minus how long ago the line was
                # logged (per its uptime prefix).
                u = _log_uptime(ln) or max_uptime
                stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - (max_uptime - u)))
                out.append(f"{stamp} {ln}")
            try:
                with open(BOARD_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                    existing = f.read().splitlines()
            except FileNotFoundError:
                existing = []
            merged = (existing + out)[-BOARD_LOG_MAX_LINES:]
            with open(BOARD_LOG_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(merged) + "\n")
        except Exception as e:
            logger.debug(f"Board log harvest failed: {e}")

    def _detect_edges(self, st: dict, now: float) -> None:
        prev = self.prev or {}
        prev_pl = prev.get("playlist") or {}
        pl = st.get("playlist") or {}
        prev_file = prev.get("file") or ""
        cur_file = st.get("file") or ""
        prev_running = bool(prev.get("running"))
        running = bool(st.get("running"))

        # File end: the file changed while running, or playback stopped.
        if prev_running and prev_file and (cur_file != prev_file or not running):
            self._close_file(prev, now, aborted=False)

        # File start.
        if running and cur_file and (not prev_running or cur_file != prev_file):
            self.file_started_at = now
            self.hold_accumulated = 0.0
            self.hold_started_at = None
            self.last_progress = -1.0
            host_path = _from_sd_path(cur_file)
            state.current_playing_file = host_path
            self._cache_history(host_path)
            self._on_playing_leds()

        if running and isinstance(st.get("progress"), (int, float)) and st["progress"] >= 0:
            self.last_progress = st["progress"]

        # Hold (pause) edges — for pause accounting and the MQTT mirror.
        prev_hold = _state(prev) == "Hold"
        hold = _state(st) == "Hold"
        if hold and not prev_hold:
            self.hold_started_at = now
            state.pause_requested = True
        elif prev_hold and not hold:
            if self.hold_started_at:
                self.hold_accumulated += now - self.hold_started_at
            self.hold_started_at = None
            state.pause_requested = False

        # Clearing edges — clear-speed shim.
        prev_clearing = bool(prev_pl.get("clearing"))
        clearing = bool(pl.get("clearing"))
        if clearing and not prev_clearing and state.clear_pattern_speed:
            self._clear_speed_saved = state.speed
            self._set_feed_safe(state.clear_pattern_speed)
        elif prev_clearing and not clearing and self._clear_speed_saved:
            self._set_feed_safe(self._clear_speed_saved)
            self._clear_speed_saved = None

        # Run end: nothing running, no active playlist, machine idle.
        was_active = prev_running or bool(prev_pl.get("active"))
        is_active = running or bool(pl.get("active"))
        if was_active and not is_active and _state(st) in ("Idle", "Alarm"):
            logger.info("Observed run end on the board")
            _reset_run_state()
            state.save()
            self._on_idle_leds()

    def _close_file(self, prev_st: dict, now: float, aborted: bool) -> None:
        """Log history for the file that just finished/stopped."""
        prev_pl = prev_st.get("playlist") or {}
        prev_file = prev_st.get("file") or ""
        if not prev_file or prev_pl.get("clearing"):
            return  # clears are not history-worthy (matches old semantics)
        from modules.core.pattern_manager import log_execution_time
        hold_extra = (now - self.hold_started_at) if self.hold_started_at else 0.0
        actual = max(0.0, now - self.file_started_at - self.hold_accumulated - hold_extra)
        completed = (not aborted) and self.last_progress >= 0.98
        try:
            log_execution_time(
                pattern_name=os.path.basename(prev_file),
                table_type="fluidnc",
                speed=int(state.speed or 0),
                actual_time=actual,
                total_coordinates=0,
                was_completed=completed,
            )
        except Exception as e:
            logger.warning(f"Could not log execution history: {e}")

    def _cache_history(self, host_path: Optional[str]) -> None:
        self.cached_history = None
        if not host_path:
            return
        try:
            from modules.core.pattern_manager import get_last_completed_execution_time
            self.cached_history = get_last_completed_execution_time(
                os.path.basename(host_path), state.speed)
        except Exception as e:
            logger.debug(f"History lookup failed: {e}")

    def _set_feed_safe(self, mm: float) -> None:
        try:
            if state.conn:
                state.conn.set_feed(int(mm))
        except Exception as e:
            logger.warning(f"Clear-speed feed change failed: {e}")

    def _on_playing_leds(self) -> None:
        if state.led_controller and state.led_automation_enabled:
            try:
                asyncio.get_running_loop().create_task(
                    state.led_controller.effect_playing_async(None))
            except RuntimeError:
                pass

    def _on_idle_leds(self) -> None:
        if state.led_controller and state.led_automation_enabled:
            try:
                asyncio.get_running_loop().create_task(
                    state.led_controller.effect_idle_async(None))
            except RuntimeError:
                pass

    async def _quiet_hours_wled(self, now: float) -> None:
        """The one surviving host Still Sands behavior: switch WLED off during
        quiet hours (the board handles its own ring via $Sands/LedOff)."""
        if state.led_provider != "wled" or not state.led_controller:
            return
        from modules.core.pattern_manager import is_in_scheduled_pause_period
        in_quiet = bool(state.scheduled_pause_control_wled and is_in_scheduled_pause_period())
        if in_quiet and not self._was_quiet_wled_off:
            self._was_quiet_wled_off = True
            await state.led_controller.set_power_async(0)
            logger.info("Still Sands: WLED off")
        elif not in_quiet and self._was_quiet_wled_off:
            self._was_quiet_wled_off = False
            await state.led_controller.set_power_async(1)
            await state.led_controller.effect_idle_async(None)
            logger.info("Still Sands: WLED restored")


observer = BoardObserver()


def get_cached_status() -> dict:
    """Last translated status (what /ws/status clients get on connect)."""
    if observer.last_translated:
        return observer.last_translated
    return translate_status(observer.last_raw, observer)
