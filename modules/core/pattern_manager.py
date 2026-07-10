"""
Pattern-file and history utilities.

Execution is firmware-delegated (see modules/core/execution.py): the board
runs patterns and playlists itself; this module only keeps the host-side
pattern catalog, the board-SD mirroring helpers, the play-history log, and
the Still Sands time-window math used by the WLED quiet-hours watcher.
"""
import os
from zoneinfo import ZoneInfo
import time
import logging
from datetime import datetime, time as datetime_time
from modules.connection import connection_manager
from modules.core.state import state
from math import pi
import asyncio
import json
from modules.led.idle_timeout_manager import idle_timeout_manager
from typing import Optional

# Configure logging
logger = logging.getLogger(__name__)

# Global state
THETA_RHO_DIR = './patterns'
os.makedirs(THETA_RHO_DIR, exist_ok=True)

# Execution time log file (JSON Lines format - one JSON object per line)
EXECUTION_LOG_FILE = './execution_times.jsonl'

def log_execution_time(pattern_name: str, table_type: str, speed: int, actual_time: float,
                       total_coordinates: int, was_completed: bool):
    """Log pattern execution time to JSON Lines file for analysis.

    Args:
        pattern_name: Name of the pattern file
        table_type: Type of table (e.g., 'dune_weaver', 'dune_weaver_mini')
        speed: Speed setting used (0-255)
        actual_time: Actual execution time in seconds (excluding pauses)
        total_coordinates: Total number of coordinates in the pattern
        was_completed: Whether the pattern completed normally (not stopped/skipped)
    """
    # Format time as HH:MM:SS
    hours, remainder = divmod(int(actual_time), 3600)
    minutes, seconds = divmod(remainder, 60)
    time_formatted = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "pattern_name": pattern_name,
        "table_type": table_type or "unknown",
        "speed": speed,
        "actual_time_seconds": round(actual_time, 2),
        "actual_time_formatted": time_formatted,
        "total_coordinates": total_coordinates,
        "completed": was_completed
    }

    try:
        with open(EXECUTION_LOG_FILE, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')

        logger.info(f"Execution time logged: {pattern_name} - {time_formatted} (speed: {speed}, table: {table_type})")
    except Exception as e:
        logger.error(f"Failed to log execution time: {e}")

def get_last_completed_execution_time(pattern_name: str, speed: float) -> Optional[dict]:
    """Get the last completed execution time for a pattern at a specific speed.

    Args:
        pattern_name: Name of the pattern file (e.g., 'circle.thr')
        speed: Speed setting to match

    Returns:
        Dict with execution time info if found, None otherwise.
        Format: {"actual_time_seconds": float, "actual_time_formatted": str, "timestamp": str}
    """
    if not os.path.exists(EXECUTION_LOG_FILE):
        return None

    try:
        matching_entry = None
        with open(EXECUTION_LOG_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    # Only consider fully completed patterns (100% finished)
                    if (entry.get('completed', False) and
                        entry.get('pattern_name') == pattern_name and
                        entry.get('speed') == speed):
                        # Keep the most recent match (last one in file)
                        matching_entry = entry
                except json.JSONDecodeError:
                    continue

        if matching_entry:
            return {
                "actual_time_seconds": matching_entry.get('actual_time_seconds'),
                "actual_time_formatted": matching_entry.get('actual_time_formatted'),
                "timestamp": matching_entry.get('timestamp')
            }
        return None
    except Exception as e:
        logger.error(f"Failed to read execution time log: {e}")
        return None

def get_pattern_execution_history(pattern_name: str) -> Optional[dict]:
    """Get the most recent completed execution for a pattern (any speed).

    Args:
        pattern_name: Name of the pattern file (e.g., 'circle.thr')

    Returns:
        Dict with execution time info if found, None otherwise.
        Format: {"actual_time_seconds": float, "actual_time_formatted": str,
                 "speed": int, "timestamp": str}
    """
    if not os.path.exists(EXECUTION_LOG_FILE):
        return None

    try:
        matching_entry = None
        with open(EXECUTION_LOG_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    # Only consider fully completed patterns
                    if (entry.get('completed', False) and
                        entry.get('pattern_name') == pattern_name):
                        # Keep the most recent match (last one in file)
                        matching_entry = entry
                except json.JSONDecodeError:
                    continue

        if matching_entry:
            return {
                "actual_time_seconds": matching_entry.get('actual_time_seconds'),
                "actual_time_formatted": matching_entry.get('actual_time_formatted'),
                "speed": matching_entry.get('speed'),
                "timestamp": matching_entry.get('timestamp')
            }
        return None
    except Exception as e:
        logger.error(f"Failed to read execution time log: {e}")
        return None


_cached_timezone = None
_cached_zoneinfo = None

def _get_timezone():
    """Get and cache the timezone for Still Sands. Uses user-selected timezone if set, otherwise system timezone."""
    global _cached_timezone, _cached_zoneinfo

    if _cached_timezone is not None:
        return _cached_zoneinfo

    user_tz = 'UTC'  # Default fallback

    # First, check if user has selected a specific timezone in settings
    if state.scheduled_pause_timezone:
        user_tz = state.scheduled_pause_timezone
        logger.info(f"Still Sands using timezone: {user_tz} (user-selected)")
    else:
        # Fall back to system timezone detection
        try:
            if os.path.exists('/etc/timezone'):
                with open('/etc/timezone', 'r') as f:
                    user_tz = f.read().strip()
                    logger.info(f"Still Sands using timezone: {user_tz} (from system)")
            # Fallback to TZ environment variable
            elif os.environ.get('TZ'):
                user_tz = os.environ.get('TZ')
                logger.info(f"Still Sands using timezone: {user_tz} (from environment)")
            else:
                logger.info("Still Sands using timezone: UTC (system default)")
        except Exception as e:
            logger.debug(f"Could not read timezone: {e}")

    # Cache the timezone
    _cached_timezone = user_tz
    try:
        _cached_zoneinfo = ZoneInfo(user_tz)
    except Exception as e:
        logger.warning(f"Invalid timezone '{user_tz}', falling back to system time: {e}")
        _cached_zoneinfo = None

    return _cached_zoneinfo

def is_in_scheduled_pause_period():
    """Check if current time falls within any scheduled pause period."""
    if not state.scheduled_pause_enabled or not state.scheduled_pause_time_slots:
        return False

    # Get cached timezone (user-selected or system default)
    tz_info = _get_timezone()

    try:
        # Get current time in user's timezone
        if tz_info:
            now = datetime.now(tz_info)
        else:
            now = datetime.now()
    except Exception as e:
        logger.warning(f"Error getting current time: {e}")
        now = datetime.now()

    current_time = now.time()
    current_weekday = now.strftime("%A").lower()  # monday, tuesday, etc.

    for slot in state.scheduled_pause_time_slots:
        # Parse start and end times
        try:
            start_time = datetime_time.fromisoformat(slot['start_time'])
            end_time = datetime_time.fromisoformat(slot['end_time'])
        except (ValueError, KeyError):
            logger.warning(f"Invalid time format in scheduled pause slot: {slot}")
            continue

        # Check if this slot applies to today
        slot_applies_today = False
        days_setting = slot.get('days', 'daily')

        if days_setting == 'daily':
            slot_applies_today = True
        elif days_setting == 'weekdays':
            slot_applies_today = current_weekday in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
        elif days_setting == 'weekends':
            slot_applies_today = current_weekday in ['saturday', 'sunday']
        elif days_setting == 'custom':
            custom_days = slot.get('custom_days', [])
            slot_applies_today = current_weekday in custom_days

        if not slot_applies_today:
            continue

        # Check if current time is within the pause period
        if start_time <= end_time:
            # Normal case: start and end are on the same day
            if start_time <= current_time <= end_time:
                return True
        else:
            # Time spans midnight: start is before midnight, end is after midnight
            if current_time >= start_time or current_time <= end_time:
                return True

    return False


async def check_table_is_idle() -> bool:
    """
    Check if the table is currently idle by querying actual machine status.
    Returns True if idle, False if playing/moving.

    This checks the real machine state rather than relying on state variables,
    making it more reliable for detecting when table is truly idle.
    """
    # Use the connection_manager's is_machine_idle() function
    # Run it in a thread since it's a synchronous function
    return await asyncio.to_thread(connection_manager.is_machine_idle)


async def start_idle_led_timeout(check_still_sands: bool = True):
    """
    Set LED to idle state and start timeout if enabled.
    Handles Still Sands: if in scheduled pause period with LED control enabled,
    turns off LEDs instead of showing idle effect.
    Should be called whenever the table goes idle.

    Args:
        check_still_sands: If True, checks Still Sands period and turns off LEDs if applicable.
                          Set to False when caller already handles Still Sands logic
                          (e.g., during pause with "finish pattern first" mode).
    """
    if not state.led_controller:
        return

    if not state.led_automation_enabled:
        # Manual mode: Still Sands can still turn OFF, but skip idle effect + timeout
        if check_still_sands and is_in_scheduled_pause_period() and state.scheduled_pause_control_wled:
            logger.info("Manual mode: Turning off LEDs during Still Sands period")
            await state.led_controller.set_power_async(0)
        return

    # Still Sands with LED control: turn off instead of idle effect
    if check_still_sands and is_in_scheduled_pause_period() and state.scheduled_pause_control_wled:
        logger.info("Turning off LED lights during Still Sands period")
        await state.led_controller.set_power_async(0)
        return

    # Normal flow: show the idle effect. WLED uses its hardcoded preset; the
    # board provider is a deliberate no-op (the firmware's $LED/IdleEffect
    # switches by itself).
    await state.led_controller.effect_idle_async(None)

    # Start timeout if enabled
    if not state.dw_led_idle_timeout_enabled:
        logger.debug("Idle LED timeout not enabled")
        return

    timeout_minutes = state.dw_led_idle_timeout_minutes
    if timeout_minutes <= 0:
        logger.debug("Idle LED timeout not configured (timeout <= 0)")
        return

    logger.debug(f"Starting idle LED timeout: {timeout_minutes} minutes")
    idle_timeout_manager.start_idle_timeout(
        timeout_minutes=timeout_minutes,
        state=state,
        check_idle_callback=check_table_is_idle
    )


def list_theta_rho_files():
    files = []
    for root, dirs, filenames in os.walk(THETA_RHO_DIR):
        # Skip cached_images directories to avoid scanning thousands of WebP files
        if 'cached_images' in dirs:
            dirs.remove('cached_images')

        # Filter .thr files during traversal for better performance
        thr_files = [f for f in filenames if f.endswith('.thr')]

        for file in thr_files:
            relative_path = os.path.relpath(os.path.join(root, file), THETA_RHO_DIR)
            # Normalize path separators to always use forward slashes for consistency across platforms
            relative_path = relative_path.replace(os.sep, '/')
            files.append(relative_path)

    logger.debug(f"Found {len(files)} theta-rho files")
    return files

def parse_theta_rho_file(file_path):
    """Parse a theta-rho file and return a list of (theta, rho) pairs."""
    coordinates = []
    try:
        logger.debug(f"Parsing theta-rho file: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    theta, rho = map(float, line.split())
                    coordinates.append((theta, rho))
                except ValueError:
                    logger.warning(f"Skipping invalid line: {line}")
                    continue
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        return coordinates

        logger.debug(f"Parsed {len(coordinates)} coordinates from {file_path}")
    return coordinates


def _to_sd_path(file_path):
    """Map a host pattern path (e.g. './patterns/star.thr') to its board SD path
    ('/patterns/star.thr'). The board SD mirrors the host's patterns/ tree."""
    p = file_path.replace("\\", "/").lstrip(".").lstrip("/")
    idx = p.find("patterns/")
    rel = p[idx:] if idx >= 0 else ("patterns/" + os.path.basename(p))
    return "/" + rel


def _ensure_on_board(file_path, sd_path):
    """Upload the pattern to the board's SD card if it isn't already there."""
    try:
        if not state.conn:
            return
        if state.conn.file_exists(sd_path):
            return
        with open(file_path, "rb") as f:
            data = f.read()
        directory = sd_path.rsplit("/", 1)[0] or "/patterns"
        state.conn.upload_file(sd_path, data, directory)
        logger.info(f"Mirrored {file_path} to board at {sd_path}")
    except Exception as e:
        logger.warning(f"Could not mirror {file_path} to board: {e}")


async def move_polar(theta, rho, speed=None):
    """
    Jog to an absolute (theta, rho) by delegating to the board's /sand_goto.
    Used by the manual move endpoints (center / perimeter / send_coordinate).

    Args:
        theta (float): Target theta in radians
        rho (float): Target rho (0..1)
        speed (int, optional): Feed override. If None, uses the board's current feed.
    """
    if not state.conn or not state.conn.is_connected():
        logger.warning("Cannot move: no board connection")
        return
    if speed is not None:
        try:
            await asyncio.to_thread(state.conn.set_feed, int(speed))
        except Exception as e:
            logger.warning(f"Could not set feed before jog: {e}")
    await asyncio.to_thread(state.conn.goto, theta, rho)

async def reset_theta():
    """
    Normalize the host's tracked theta to [0, 2π).

    The board now owns machine position and theta accumulation, so this only keeps
    the host-side ``current_theta`` tidy for display. (The old $Bye hard-reset path
    was removed — rebooting the controller on a manual move is never what we want.)
    """
    state.current_theta = state.current_theta % (2 * pi)
    logger.info(f'Theta normalized to {state.current_theta:.4f} radians')

def set_speed(new_speed):
    state.speed = new_speed
    logger.info(f'Set new state.speed {new_speed}')

