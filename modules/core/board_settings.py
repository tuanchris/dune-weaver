"""
Board-owned settings sync — the host side of the "board NVS is canonical" rule.

The FluidNC firmware persists table behavior settings in NVS ($Playlist/*,
$Sands/*, $Sand/*) and the native mobile apps edit them directly on the board.
This module keeps the web backend in agreement:

  - Auto-play on boot ($Playlist/Autostart*) lives ONLY on the board — it fires
    when the *table* powers on, whether or not this backend is running. The
    backend proxies reads/writes for the web UI and mirrors host playlists to
    the board SD so autostart has something to run.
  - Still Sands quiet hours ($Sands/*) are stored on the board, but the firmware
    only enforces them for its own playlist sequencing — an explicit $Sand/Run
    (how this backend plays each pattern) deliberately bypasses them. So the
    host keeps enforcing quiet hours itself via state.scheduled_pause_* in
    pattern_manager; this module pushes UI edits to the board and adopts board
    values (mobile app edits) back into host state.
  - The board clock must be set for quiet hours / autostart schedules; the host
    pushes its epoch + POSIX timezone on connect and whenever the tz changes.

All pushes are best-effort: the board being unreachable never blocks a host-side
settings save (host enforcement still works without the board's copy).
"""

import logging
import os
import threading
import time

from modules.core.state import state

logger = logging.getLogger(__name__)

# Host slot day names (state.scheduled_pause_time_slots) <-> firmware 3-letter codes.
_DAY_TO_BOARD = {
    "sunday": "sun", "monday": "mon", "tuesday": "tue", "wednesday": "wed",
    "thursday": "thu", "friday": "fri", "saturday": "sat",
}
_BOARD_TO_DAY = {v: k for k, v in _DAY_TO_BOARD.items()}
_BOARD_DAY_ORDER = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]

CLEAR_MODES = ("none", "adaptive", "in", "out", "sideway", "random")


def _is_on(value) -> bool:
    return str(value or "").upper() in ("ON", "1", "TRUE")


# ---------------------------------------------------------------------------
# Still Sands slot conversion: host dicts <-> "$Sands/Slots" spec string
# ---------------------------------------------------------------------------

def slots_to_board(time_slots: list) -> str:
    """Host slot dicts -> 'HH:MM-HH:MM@days,...' ($Sands/Slots syntax)."""
    parts = []
    for slot in time_slots or []:
        start = slot.get("start_time")
        end = slot.get("end_time")
        if not start or not end:
            continue
        days = slot.get("days", "daily")
        if days == "custom":
            codes = sorted(
                {_DAY_TO_BOARD[d] for d in slot.get("custom_days", []) if d in _DAY_TO_BOARD},
                key=_BOARD_DAY_ORDER.index,
            )
            days = "+".join(codes) if codes else "daily"
        parts.append(f"{start}-{end}@{days}")
    return ",".join(parts)


def _normalize_time(value: str) -> str | None:
    """'9:5' -> '09:05'; None when not a valid HH:MM."""
    hours, sep, minutes = value.strip().partition(":")
    if not sep or not hours.isdigit() or not minutes.isdigit():
        return None
    h, m = int(hours), int(minutes)
    if h > 23 or m > 59:
        return None
    return f"{h:02d}:{m:02d}"


def board_to_slots(spec: str) -> list:
    """'$Sands/Slots' spec string -> host slot dicts (invalid entries dropped)."""
    slots = []
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        times, _, days_spec = part.partition("@")
        start, dash, end = times.strip().partition("-")
        start, end = _normalize_time(start), _normalize_time(end or "")
        if not dash or not start or not end:
            continue
        days_spec = (days_spec or "daily").strip().lower()
        if days_spec in ("", "daily", "weekdays", "weekends"):
            days, custom_days = (days_spec or "daily"), []
        else:
            custom_days = [_BOARD_TO_DAY[c.strip()] for c in days_spec.split("+") if c.strip() in _BOARD_TO_DAY]
            days = "custom" if custom_days else "daily"
        slots.append({
            "start_time": start,
            "end_time": end,
            "days": days,
            "custom_days": custom_days,
        })
    return slots


# ---------------------------------------------------------------------------
# Clock sync
# ---------------------------------------------------------------------------

def posix_tz(iana_name: str | None = None) -> str | None:
    """POSIX TZ rule string for an IANA zone (or the system zone when None).

    Modern TZif files (v2+) end with a footer line holding exactly this string
    (e.g. 'EST5EDT,M3.2.0,M11.1.0'), which is what the firmware's $Time/Zone
    wants. Returns None when the zone file can't be read.
    """
    path = f"/usr/share/zoneinfo/{iana_name}" if iana_name else "/etc/localtime"
    try:
        with open(path, "rb") as f:
            data = f.read()
        if not data.startswith(b"TZif"):
            return None
        # Footer = text between the last two newlines of the file.
        end = data.rfind(b"\n")
        if end <= 0:
            return None
        begin = data.rfind(b"\n", 0, end)
        footer = data[begin + 1:end].decode("ascii").strip()
        return footer or None
    except Exception as e:
        logger.debug(f"Could not derive POSIX tz for {iana_name or 'system'}: {e}")
        return None


def sync_board_time(conn=None) -> dict:
    """Push the host's clock (and effective quiet-hours timezone) to the board.

    Quiet hours are computed host-side in state.scheduled_pause_timezone (or the
    system zone); pushing the same zone keeps board-side schedules (autostart,
    firmware playlists) aligned with what the user sees in the UI.
    """
    conn = conn or state.conn
    if not conn:
        raise RuntimeError("No board connection")
    tz = posix_tz(state.scheduled_pause_timezone)
    result = conn.set_time(epoch=int(time.time()), tz=tz)
    logger.info(f"Synced board clock (tz={tz or 'unchanged'}): {result}")
    return result


# ---------------------------------------------------------------------------
# Still Sands push / adopt
# ---------------------------------------------------------------------------

def push_still_sands(conn=None) -> None:
    """Write the host's Still Sands settings to the board's $Sands/* NVS keys."""
    conn = conn or state.conn
    if not conn:
        return
    conn.set_setting("Sands/Enabled", "ON" if state.scheduled_pause_enabled else "OFF")
    slots = slots_to_board(state.scheduled_pause_time_slots)
    if slots:
        conn.set_setting("Sands/Slots", slots)
    conn.set_setting("Sands/FinishPattern", "ON" if state.scheduled_pause_finish_pattern else "OFF")
    # One UI toggle drives both LED systems: host WLED and the board's own ring.
    conn.set_setting("Sands/LedOff", "ON" if state.scheduled_pause_control_wled else "OFF")
    logger.info("Pushed Still Sands settings to board")


def adopt_still_sands(settings_map: dict) -> bool:
    """Adopt the board's $Sands/* values into host state (mobile-app edits win).

    Returns True when anything changed. The timezone is not adopted: the board
    stores a POSIX rule derived from the host's IANA zone, which isn't
    reversible — the host zone selection stays authoritative.
    """
    enabled = _is_on(settings_map.get("Sands/Enabled"))
    finish = _is_on(settings_map.get("Sands/FinishPattern", "ON"))
    led_off = _is_on(settings_map.get("Sands/LedOff"))
    slots = board_to_slots(settings_map.get("Sands/Slots", ""))

    changed = (
        enabled != state.scheduled_pause_enabled
        or finish != state.scheduled_pause_finish_pattern
        or led_off != state.scheduled_pause_control_wled
        or slots != state.scheduled_pause_time_slots
    )
    if changed:
        state.scheduled_pause_enabled = enabled
        state.scheduled_pause_finish_pattern = finish
        state.scheduled_pause_control_wled = led_off
        state.scheduled_pause_time_slots = slots
        state.save()
        logger.info("Adopted Still Sands settings from board")
    return changed


# ---------------------------------------------------------------------------
# Auto-home cadence ($Playlist/AutoHome) — mirrors the host auto_home settings
# so firmware-sequenced playlists (autostart) drift-correct the same way.
# ---------------------------------------------------------------------------

def push_auto_home(conn=None) -> None:
    conn = conn or state.conn
    if not conn:
        return
    every = state.auto_home_after_patterns if state.auto_home_enabled else 0
    conn.set_setting("Playlist/AutoHome", max(0, int(every or 0)))


# ---------------------------------------------------------------------------
# Auto-play on boot ($Playlist/Autostart*) — board-only, proxied for the web UI
# ---------------------------------------------------------------------------

def get_board_settings(conn=None) -> dict:
    """Shape the board's /sand_settings + clock into the web UI's structure."""
    conn = conn or state.conn
    if not conn:
        raise RuntimeError("No board connection")
    s = conn.get_settings()
    status = conn.get_status()
    return {
        "reachable": True,
        "firmware_version": status.get("fw"),
        "state": status.get("state"),
        "time": status.get("time") or conn.get_time(),
        "autostart": {
            "playlist": s.get("Playlist/Autostart", ""),
            "run_mode": "single" if (s.get("Playlist/AutostartMode", "loop").lower() == "single") else "loop",
            "shuffle": _is_on(s.get("Playlist/AutostartShuffle")),
            "pause_seconds": int(float(s.get("Playlist/AutostartPause", 0) or 0)),
            "pause_from_start": _is_on(s.get("Playlist/AutostartPauseFromStart")),
            "clear_pattern": s.get("Playlist/AutostartClear", "none") or "none",
        },
        "homing_mode": (s.get("Sand/HomingMode") or "sensor").lower(),
        "theta_offset": float(s.get("Sand/ThetaOffset", 0) or 0),
        "auto_home_every": int(float(s.get("Playlist/AutoHome", 0) or 0)),
    }


def apply_autostart(update: dict, conn=None) -> None:
    """Write autostart fields to the board. `update` uses the UI field names."""
    conn = conn or state.conn
    if not conn:
        raise RuntimeError("No board connection")
    if "playlist" in update:
        # Empty value disables auto-play on boot.
        conn.set_setting("Playlist/Autostart", update["playlist"] or "")
    if "run_mode" in update:
        mode = "single" if update["run_mode"] == "single" else "loop"
        conn.set_setting("Playlist/AutostartMode", mode)
    if "shuffle" in update:
        conn.set_setting("Playlist/AutostartShuffle", "ON" if update["shuffle"] else "OFF")
    if "pause_seconds" in update:
        conn.set_setting("Playlist/AutostartPause", max(0, int(update["pause_seconds"] or 0)))
    if "pause_from_start" in update:
        conn.set_setting("Playlist/AutostartPauseFromStart", "ON" if update["pause_from_start"] else "OFF")
    if "clear_pattern" in update:
        clear = update["clear_pattern"] if update["clear_pattern"] in CLEAR_MODES else "none"
        conn.set_setting("Playlist/AutostartClear", clear)


# ---------------------------------------------------------------------------
# Playlist mirroring — firmware playlists are /playlists/<name>.txt on the SD,
# one SD pattern path per line. Autostart runs these, so host playlist CRUD is
# mirrored (and the selected playlist's patterns are ensured on the board).
# ---------------------------------------------------------------------------

def _playlist_sd_content(files: list, resolve) -> str:
    lines = [resolve(f) for f in files or []]
    return "\n".join(lines) + "\n"


def mirror_playlist(name: str, files: list, conn=None, ensure_patterns: bool = False,
                    resolve=None) -> None:
    """Write a host playlist to the board as /playlists/<name>.txt (best-effort).

    `resolve` maps host entries to SD paths (make_sd_path_resolver); pass the
    caller's resolver when patterns are ensured separately so the playlist
    lines and the uploads land on the same paths."""
    from modules.core.pattern_manager import _ensure_on_board, make_sd_path_resolver
    conn = conn or state.conn
    if not conn:
        return
    resolve = resolve or make_sd_path_resolver(conn)
    try:
        sd_path = f"/playlists/{name}.txt"
        data = _playlist_sd_content(files, resolve).encode("utf-8")
        conn.upload_file(sd_path, data, "/playlists")
        logger.info(f"Mirrored playlist '{name}' to board ({len(files or [])} patterns)")
    except Exception as e:
        logger.warning(f"Could not mirror playlist '{name}' to board: {e}")
        return
    if ensure_patterns:
        for f in files or []:
            _ensure_on_board(f, resolve(f))


def mirror_playlist_async(name: str, files: list) -> None:
    """Fire-and-forget mirror from sync code paths (never blocks the caller)."""
    threading.Thread(target=mirror_playlist, args=(name, files), daemon=True).start()


def unmirror_playlist_async(name: str) -> None:
    threading.Thread(target=unmirror_playlist, args=(name,), daemon=True).start()


def unmirror_playlist(name: str, conn=None) -> None:
    """Delete a playlist's mirror from the board SD (best-effort)."""
    conn = conn or state.conn
    if not conn:
        return
    try:
        conn.delete_file("/playlists", f"{name}.txt")
        logger.info(f"Removed playlist '{name}' from board")
    except Exception as e:
        logger.debug(f"Could not remove playlist '{name}' from board: {e}")


def _from_playlist_sd_line(line: str) -> str:
    """Invert _to_sd_path for playlist lines: '/patterns/x.thr' -> 'x.thr'
    (host playlist entries are relative to the patterns/ dir)."""
    p = line.replace("\\", "/").strip()
    if p.startswith("/sd/"):
        p = p[3:]
    if p.startswith("/patterns/"):
        return p[len("/patterns/"):]
    return p.rsplit("/", 1)[-1]


def _make_host_path_resolver():
    """Board SD paths don't always mirror the host patterns/ tree: files can
    reach the board via the mobile app or a copied SD card while the host holds
    the same pattern elsewhere (e.g. under custom_patterns/). Adopted playlist
    entries must point at real host files or previews and play both 404.

    Returns a resolve(rel) -> rel function: exact path if it exists, else a
    unique catalog suffix match, else a unique basename match, else the raw
    path unchanged (the pattern genuinely isn't on the host). The catalog is
    scanned lazily once per adoption pass and results are memoized, so the
    resolution is deterministic and repeat adoptions stay stable."""
    from modules.core import pattern_manager
    cache: dict = {}
    catalog: list = []
    scanned = False

    def resolve(rel: str) -> str:
        nonlocal catalog, scanned
        if rel in cache:
            return cache[rel]
        result = rel
        if not os.path.exists(os.path.join(pattern_manager.THETA_RHO_DIR, rel)):
            if not scanned:
                scanned = True
                try:
                    catalog = pattern_manager.list_theta_rho_files()
                except Exception as e:
                    logger.warning(f"Could not scan pattern catalog: {e}")
            suffix = "/" + rel
            matches = [f for f in catalog if f.endswith(suffix)]
            if not matches:
                basename = rel.rsplit("/", 1)[-1]
                matches = [f for f in catalog if f.rsplit("/", 1)[-1] == basename]
            if len(matches) == 1:
                result = matches[0]
        cache[rel] = result
        return result

    return resolve


def adopt_board_playlists(conn=None) -> None:
    """Read the board's /playlists/*.txt into the host catalog.

    The board is the source of truth for playlists (mobile apps edit it
    directly); the host only WRITES on deliberate user actions (playlist CRUD,
    pressing play, selecting an autostart playlist) — never automatically.
    Board copies win for names that exist on the board; host-only playlists
    are kept (they reach the board the next time the user edits or plays
    them). Reads only — no SD writes, no flash wear.
    """
    from modules.core import playlist_manager
    conn = conn or state.conn
    if not conn:
        return
    try:
        names = conn.list_playlists()
    except Exception as e:
        logger.warning(f"Could not list board playlists: {e}")
        return
    if not isinstance(names, list):
        return
    try:
        playlists = playlist_manager.load_playlists()
    except Exception:
        playlists = {}
    changed = []
    resolve_host_path = _make_host_path_resolver()
    for board_name in names:
        fname = board_name if board_name.endswith(".txt") else f"{board_name}.txt"
        name = fname[:-4]
        if not name:
            continue
        try:
            data = conn.fetch_file(f"/playlists/{fname}")
        except Exception:
            continue  # listed but unreadable (e.g. deleted mid-scan) — skip
        files = [resolve_host_path(_from_playlist_sd_line(l))
                 for l in data.decode("utf-8", "replace").splitlines() if l.strip()]
        entry = playlists.get(name)
        current = entry.get("files", entry) if isinstance(entry, dict) else entry
        if current != files:
            playlists[name] = {**entry, "files": files} if isinstance(entry, dict) else files
            changed.append(name)
    if changed:
        playlist_manager.save_playlists(playlists)
        logger.info(f"Adopted board playlists: {', '.join(changed)}")


def adopt_auto_home(settings_map: dict) -> None:
    """Adopt the board's $Playlist/AutoHome cadence (0 = disabled). The host
    pushes it only when the user edits the setting in the web UI."""
    raw = settings_map.get("Playlist/AutoHome")
    if raw is None:
        return
    try:
        every = int(float(raw))
    except (TypeError, ValueError):
        return
    enabled = every > 0
    if enabled == state.auto_home_enabled and (
            not enabled or every == state.auto_home_after_patterns):
        return
    state.auto_home_enabled = enabled
    if enabled:
        state.auto_home_after_patterns = every
    state.save_debounced()
    logger.info(f"Adopted board auto-home cadence: {every or 'disabled'}")


# ---------------------------------------------------------------------------
# Custom clear patterns — the firmware picks and runs its own clear files
# (/patterns/clear_from_in.thr, clear_from_out.thr per its playlist: config).
# A "custom" clear is implemented by uploading the chosen pattern's content
# over those fixed paths (and restoring the stock file when cleared).
# ---------------------------------------------------------------------------

def push_custom_clears(conn=None) -> None:
    """Upload the effective clear files to the board (best effort)."""
    conn = conn or state.conn
    if not conn:
        return
    from modules.core.pattern_manager import THETA_RHO_DIR
    import os
    for board_name, custom in (
        ("clear_from_in.thr", state.custom_clear_from_in),
        ("clear_from_out.thr", state.custom_clear_from_out),
    ):
        source = os.path.join(THETA_RHO_DIR, custom) if custom \
            else os.path.join(THETA_RHO_DIR, board_name)
        if not os.path.exists(source):
            logger.warning(f"Clear source missing, not mirrored: {source}")
            continue
        try:
            with open(source, "rb") as f:
                conn.upload_file(f"/patterns/{board_name}", f.read(), "/patterns")
            logger.info(f"Board clear file {board_name} <- {os.path.basename(source)}")
        except Exception as e:
            logger.warning(f"Could not push clear file {board_name}: {e}")


def push_custom_clears_async() -> None:
    threading.Thread(target=push_custom_clears, daemon=True).start()


# ---------------------------------------------------------------------------
# Connect-time reconciliation, called after the board connection is up.
# ---------------------------------------------------------------------------

def sync_on_connect(conn=None) -> None:
    """Connect-time reconciliation: clock push + adopt board-owned state.

    Read-only toward the board's SD/NVS (except the clock, which is RAM/RTC):
    Still Sands, auto-home cadence and playlists are ADOPTED from the board.
    The host never auto-pushes content — uploads happen only on deliberate
    user actions (play, playlist CRUD, autostart selection, settings edits).
    """
    conn = conn or state.conn
    if not conn:
        return
    try:
        sync_board_time(conn)
    except Exception as e:
        logger.warning(f"Board clock sync failed: {e}")
    try:
        settings_map = conn.get_settings()
        adopt_still_sands(settings_map)
        adopt_auto_home(settings_map)
    except Exception as e:
        logger.warning(f"Could not adopt board settings: {e}")
    adopt_board_playlists(conn)
