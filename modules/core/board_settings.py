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

def _playlist_sd_content(files: list) -> str:
    from modules.core.pattern_manager import _to_sd_path
    lines = [_to_sd_path(f) for f in files or []]
    return "\n".join(lines) + "\n"


def mirror_playlist(name: str, files: list, conn=None, ensure_patterns: bool = False) -> None:
    """Write a host playlist to the board as /playlists/<name>.txt (best-effort)."""
    conn = conn or state.conn
    if not conn:
        return
    try:
        sd_path = f"/playlists/{name}.txt"
        data = _playlist_sd_content(files).encode("utf-8")
        conn.upload_file(sd_path, data, "/playlists")
        logger.info(f"Mirrored playlist '{name}' to board ({len(files or [])} patterns)")
    except Exception as e:
        logger.warning(f"Could not mirror playlist '{name}' to board: {e}")
        return
    if ensure_patterns:
        from modules.core.pattern_manager import _ensure_on_board, _to_sd_path
        for f in files or []:
            _ensure_on_board(f, _to_sd_path(f))


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


def mirror_all_playlists(conn=None) -> None:
    """Mirror every host playlist to the board (run on connect, best-effort)."""
    from modules.core import playlist_manager
    conn = conn or state.conn
    if not conn:
        return
    try:
        playlists = playlist_manager.load_playlists()
    except Exception as e:
        logger.warning(f"Could not load playlists for mirroring: {e}")
        return
    for name, entry in playlists.items():
        files = entry.get("files", entry) if isinstance(entry, dict) else entry
        mirror_playlist(name, files, conn=conn)


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
    """Clock push + Still Sands adopt + AutoHome push + playlist mirror."""
    conn = conn or state.conn
    if not conn:
        return
    try:
        sync_board_time(conn)
    except Exception as e:
        logger.warning(f"Board clock sync failed: {e}")
    try:
        adopt_still_sands(conn.get_settings())
    except Exception as e:
        logger.warning(f"Could not adopt Still Sands settings from board: {e}")
    try:
        push_auto_home(conn)
    except Exception as e:
        logger.warning(f"Could not push auto-home cadence to board: {e}")
    mirror_all_playlists(conn)
