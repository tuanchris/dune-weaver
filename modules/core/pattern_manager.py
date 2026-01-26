import os
from zoneinfo import ZoneInfo
import threading
import time
import random
import logging
from datetime import datetime, time as datetime_time
from tqdm import tqdm
from modules.connection import connection_manager
from modules.core.state import state
from math import pi, isnan, isinf
import asyncio
import json
# Import for legacy support, but we'll use LED interface through state
from modules.led.led_controller import effect_playing, effect_idle
from modules.led.idle_timeout_manager import idle_timeout_manager
import queue
from dataclasses import dataclass
from typing import Optional, Callable, Literal

# Configure logging
logger = logging.getLogger(__name__)

# Global state
THETA_RHO_DIR = './patterns'
os.makedirs(THETA_RHO_DIR, exist_ok=True)

# Execution time log file (JSON Lines format - one JSON object per line)
EXECUTION_LOG_FILE = './execution_times.jsonl'


async def wait_with_interrupt(
    condition_fn: Callable[[], bool],
    check_stop: bool = True,
    check_skip: bool = True,
    interval: float = 1.0,
) -> Literal['completed', 'stopped', 'skipped']:
    """
    Wait while condition_fn() returns True, with instant interrupt support.

    Uses asyncio.Event for instant response to stop/skip requests rather than
    polling at fixed intervals. This ensures users get immediate feedback when
    pressing stop or skip buttons.

    Args:
        condition_fn: Function that returns True while waiting should continue
        check_stop: Whether to respond to stop requests (default True)
        check_skip: Whether to respond to skip requests (default True)
        interval: How often to re-check condition_fn in seconds (default 1.0)

    Returns:
        'completed' - condition_fn() returned False (normal completion)
        'stopped' - stop was requested
        'skipped' - skip was requested

    Example:
        result = await wait_with_interrupt(
            lambda: state.pause_requested or is_in_scheduled_pause_period()
        )
        if result == 'stopped':
            return  # Exit pattern execution
        if result == 'skipped':
            break  # Skip to next pattern
    """
    while condition_fn():
        result = await state.wait_for_interrupt(
            timeout=interval,
            check_stop=check_stop,
            check_skip=check_skip,
        )
        if result == 'stopped':
            return 'stopped'
        if result == 'skipped':
            return 'skipped'
        # 'timeout' means we should re-check condition_fn
    return 'completed'


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

# Asyncio primitives - initialized lazily to avoid event loop issues
# These must be created in the context of the running event loop
pause_event: Optional[asyncio.Event] = None
pattern_lock: Optional[asyncio.Lock] = None
progress_update_task = None

def get_pause_event() -> asyncio.Event:
    """Get or create the pause event in the current event loop."""
    global pause_event
    if pause_event is None:
        pause_event = asyncio.Event()
        pause_event.set()  # Initially not paused
    return pause_event

def get_pattern_lock() -> asyncio.Lock:
    """Get or create the pattern lock in the current event loop."""
    global pattern_lock
    if pattern_lock is None:
        pattern_lock = asyncio.Lock()
    return pattern_lock

# Cache timezone at module level - read once per session (cleared when user changes timezone)
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
            if os.path.exists('/etc/host-timezone'):
                with open('/etc/host-timezone', 'r') as f:
                    user_tz = f.read().strip()
                    logger.info(f"Still Sands using timezone: {user_tz} (from host system)")
            # Fallback to /etc/timezone if host-timezone doesn't exist
            elif os.path.exists('/etc/timezone'):
                with open('/etc/timezone', 'r') as f:
                    user_tz = f.read().strip()
                    logger.info(f"Still Sands using timezone: {user_tz} (from container)")
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


def start_idle_led_timeout():
    """
    Start the idle LED timeout if enabled.
    Should be called whenever the idle effect is activated.
    """
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


# Motion Control Thread Infrastructure
@dataclass
class MotionCommand:
    """Represents a motion command for the motion control thread."""
    command_type: str  # 'move', 'stop', 'pause', 'resume', 'shutdown'
    theta: Optional[float] = None
    rho: Optional[float] = None
    speed: Optional[float] = None
    callback: Optional[Callable] = None
    future: Optional[asyncio.Future] = None

class MotionControlThread:
    """Dedicated thread for hardware motion control operations."""

    def __init__(self):
        self.command_queue = queue.Queue()
        self.thread = None
        self.running = False
        self.paused = False

    def start(self):
        """Start the motion control thread with elevated priority."""
        if self.thread and self.thread.is_alive():
            return

        self.running = True
        self.thread = threading.Thread(target=self._motion_loop, daemon=True)
        self.thread.start()
        logger.info("Motion control thread started")

    def stop(self):
        """Stop the motion control thread."""
        if not self.running:
            return

        self.running = False
        # Send shutdown command
        self.command_queue.put(MotionCommand('shutdown'))

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5.0)
        logger.info("Motion control thread stopped")

    def _motion_loop(self):
        """Main loop for the motion control thread."""
        logger.info("Motion control thread loop started")

        while self.running:
            try:
                # Get command with timeout to allow periodic checks
                command = self.command_queue.get(timeout=1.0)

                if command.command_type == 'shutdown':
                    break

                elif command.command_type == 'move':
                    self._execute_move(command)

                elif command.command_type == 'pause':
                    self.paused = True

                elif command.command_type == 'resume':
                    self.paused = False

                elif command.command_type == 'stop':
                    # Clear any pending commands
                    while not self.command_queue.empty():
                        try:
                            self.command_queue.get_nowait()
                        except queue.Empty:
                            break

                self.command_queue.task_done()

            except queue.Empty:
                # Timeout - continue loop for shutdown check
                continue
            except Exception as e:
                logger.error(f"Error in motion control thread: {e}")

        logger.info("Motion control thread loop ended")

    def _execute_move(self, command: MotionCommand):
        """Execute a move command in the motion thread."""
        try:
            # Wait if paused
            while self.paused and self.running:
                time.sleep(0.1)

            if not self.running:
                return

            # Execute the actual motion using sync version
            self._move_polar_sync(command.theta, command.rho, command.speed)

            # Signal completion if future provided
            if command.future and not command.future.done():
                command.future.get_loop().call_soon_threadsafe(
                    command.future.set_result, None
                )

        except Exception as e:
            logger.error(f"Error executing move command: {e}")
            if command.future and not command.future.done():
                command.future.get_loop().call_soon_threadsafe(
                    command.future.set_exception, e
                )

    def _move_polar_sync(self, theta: float, rho: float, speed: Optional[float] = None):
        """Synchronous version of move_polar for use in motion thread."""
        # Check for valid machine position (can be None if homing failed)
        if state.machine_x is None or state.machine_y is None:
            logger.error("Cannot execute move: machine position unknown (homing may have failed)")
            logger.error("Please home the machine before running patterns")
            state.stop_requested = True
            return

        # This is the original sync logic but running in dedicated thread
        if state.table_type == 'dune_weaver_mini':
            x_scaling_factor = 2
            y_scaling_factor = 3.7
        else:
            x_scaling_factor = 2
            y_scaling_factor = 5

        delta_theta = theta - state.current_theta
        delta_rho = rho - state.current_rho
        x_increment = delta_theta * 100 / (2 * pi * x_scaling_factor)
        y_increment = delta_rho * 100 / y_scaling_factor

        x_total_steps = state.x_steps_per_mm * (100/x_scaling_factor)
        y_total_steps = state.y_steps_per_mm * (100/y_scaling_factor)

        offset = x_increment * (x_total_steps * x_scaling_factor / (state.gear_ratio * y_total_steps * y_scaling_factor))

        if state.table_type == 'dune_weaver_mini' or state.y_steps_per_mm == 546:
            y_increment -= offset
        else:
            y_increment += offset

        new_x_abs = state.machine_x + x_increment
        new_y_abs = state.machine_y + y_increment

        # Use provided speed or fall back to state.speed
        actual_speed = speed if speed is not None else state.speed

        # Validate coordinates before sending to prevent GRBL error:2
        if isnan(new_x_abs) or isnan(new_y_abs) or isinf(new_x_abs) or isinf(new_y_abs):
            logger.error(f"Motion thread: Invalid coordinates detected - X:{new_x_abs}, Y:{new_y_abs}")
            logger.error(f"  theta:{theta}, rho:{rho}, current_theta:{state.current_theta}, current_rho:{state.current_rho}")
            logger.error(f"  x_steps_per_mm:{state.x_steps_per_mm}, y_steps_per_mm:{state.y_steps_per_mm}, gear_ratio:{state.gear_ratio}")
            state.stop_requested = True
            return

        # Call sync version of send_grbl_coordinates in this thread
        # Use 2 decimal precision to reduce GRBL parsing overhead
        self._send_grbl_coordinates_sync(round(new_x_abs, 2), round(new_y_abs, 2), actual_speed)

        # Update state
        state.current_theta = theta
        state.current_rho = rho
        state.machine_x = new_x_abs
        state.machine_y = new_y_abs

    def _send_grbl_coordinates_sync(self, x: float, y: float, speed: int = 600, timeout: int = 2, home: bool = False):
        """Synchronous version of send_grbl_coordinates for motion thread.

        Waits for 'ok' with a timeout. GRBL sends 'ok' after the move completes,
        which can take many seconds at slow speeds. We use a generous timeout
        (120 seconds) to handle slow movements, but prevent indefinite hangs.

        Includes retry logic for serial corruption errors (common on Pi 3B+).
        """
        gcode = f"$J=G91 G21 Y{y:.2f} F{speed}" if home else f"G1 X{x:.2f} Y{y:.2f} F{speed}"
        max_wait_time = 120  # Maximum seconds to wait for 'ok' response
        max_corruption_retries = 10  # Max retries for corruption-type errors
        max_timeout_retries = 10  # Max retries for timeout (lost 'ok' response)
        corruption_retry_count = 0
        timeout_retry_count = 0

        # GRBL error codes that indicate likely serial corruption (syntax errors)
        # These are recoverable by resending the command
        corruption_error_codes = {
            'error:1',   # Expected command letter
            'error:2',   # Bad number format
            'error:20',  # Invalid gcode ID (e.g., G5s instead of G53)
            'error:21',  # Invalid gcode command value
            'error:22',  # Invalid gcode command value in negative
            'error:23',  # Invalid gcode command value in decimal
        }

        while True:
            # Check stop_requested at the start of each iteration
            if state.stop_requested:
                logger.debug("Motion thread: Stop requested, aborting command")
                return False

            try:
                # Clear any stale input data before sending to prevent interleaving
                # This helps with timing issues on slower UARTs like Pi 3B+
                if hasattr(state.conn, 'reset_input_buffer'):
                    state.conn.reset_input_buffer()

                logger.debug(f"Motion thread sending G-code: {gcode}")
                state.conn.send(gcode + "\n")

                # Small delay for serial buffer to stabilize on slower UARTs
                # Prevents timing-related corruption on Pi 3B+
                time.sleep(0.005)

                # Wait for 'ok' with timeout
                wait_start = time.time()
                while True:
                    # Check stop_requested while waiting
                    if state.stop_requested:
                        logger.debug("Motion thread: Stop requested while waiting for response")
                        return False

                    # Check for timeout
                    elapsed = time.time() - wait_start
                    if elapsed > max_wait_time:
                        logger.warning(f"Motion thread: Timeout ({max_wait_time}s) waiting for 'ok' response")
                        logger.warning(f"Motion thread: Failed command was: {gcode}")

                        # Attempt to recover by checking machine status
                        # The 'ok' might have been lost but command may have executed
                        logger.info("Motion thread: Attempting timeout recovery - checking machine status")
                        logger.info(f"Motion thread: Current retry counts - timeout: {timeout_retry_count}/{max_timeout_retries}, corruption: {corruption_retry_count}/{max_corruption_retries}")

                        try:
                            # Check connection state first
                            conn_type = type(state.conn).__name__ if state.conn else "None"
                            logger.info(f"Motion thread: Connection type: {conn_type}")

                            if not state.conn:
                                logger.error("Motion thread: Connection object is None!")
                                raise Exception("Connection is None")

                            # Clear buffer first
                            if hasattr(state.conn, 'reset_input_buffer'):
                                state.conn.reset_input_buffer()
                                logger.info("Motion thread: Input buffer cleared")
                            else:
                                logger.warning("Motion thread: Connection has no reset_input_buffer method")

                            # Check if there's data waiting before we send
                            if hasattr(state.conn, 'in_waiting'):
                                waiting = state.conn.in_waiting()
                                logger.info(f"Motion thread: Bytes waiting in buffer after clear: {waiting}")

                            # Send status query
                            logger.info("Motion thread: Sending status query '?'...")
                            state.conn.send("?\n")
                            time.sleep(0.2)
                            logger.info("Motion thread: Status query sent, reading responses...")

                            # Try to read status response
                            status_response = None
                            responses_received = []
                            for i in range(10):
                                resp = state.conn.readline()
                                if resp:
                                    responses_received.append(resp)
                                    logger.info(f"Motion thread: Recovery response [{i+1}/10]: '{resp}'")
                                    if '<' in resp or 'Idle' in resp or 'Run' in resp or 'Hold' in resp or 'Alarm' in resp:
                                        status_response = resp
                                        logger.info(f"Motion thread: Found valid status response: '{resp}'")
                                        break
                                    # Also check for 'ok' that might have been delayed
                                    if resp.lower() == 'ok':
                                        logger.info("Motion thread: Received delayed 'ok' during recovery - SUCCESS")
                                        return True
                                else:
                                    logger.debug(f"Motion thread: Recovery read [{i+1}/10]: no data (timeout)")
                                time.sleep(0.05)

                            # Log summary of what we received
                            if responses_received:
                                logger.info(f"Motion thread: Total responses received during recovery: {len(responses_received)}")
                                logger.info(f"Motion thread: All responses: {responses_received}")
                            else:
                                logger.warning("Motion thread: No responses received during recovery - connection may be dead")

                            if status_response:
                                if 'Idle' in status_response:
                                    # Machine is idle - command likely completed, 'ok' was lost
                                    logger.info("Motion thread: Machine is Idle - assuming command completed (ok was lost) - SUCCESS")
                                    return True
                                elif 'Run' in status_response:
                                    # Machine still running - extend timeout
                                    logger.info("Motion thread: Machine still running, extending wait time")
                                    wait_start = time.time()  # Reset timeout
                                    continue
                                elif 'Hold' in status_response:
                                    # Machine is in Hold state - attempt to resume
                                    logger.warning(f"Motion thread: Machine in Hold state: '{status_response}'")
                                    logger.info("Motion thread: Sending cycle start command '~' to resume from Hold...")

                                    # Send cycle start command to resume
                                    state.conn.send("~\n")
                                    time.sleep(0.3)  # Give time for resume to process

                                    # Re-check status after resume attempt
                                    state.conn.send("?\n")
                                    time.sleep(0.2)

                                    # Read new status
                                    resume_response = None
                                    for _ in range(5):
                                        resp = state.conn.readline()
                                        if resp:
                                            logger.info(f"Motion thread: Post-resume response: '{resp}'")
                                            if '<' in resp:
                                                resume_response = resp
                                                break
                                        time.sleep(0.05)

                                    if resume_response:
                                        if 'Idle' in resume_response:
                                            logger.info("Motion thread: Machine resumed and is now Idle - SUCCESS")
                                            return True
                                        elif 'Run' in resume_response:
                                            logger.info("Motion thread: Machine resumed and running, extending wait time")
                                            wait_start = time.time()
                                            continue
                                        elif 'Hold' in resume_response:
                                            # Still in Hold - may need user intervention
                                            logger.warning(f"Motion thread: Still in Hold after resume: '{resume_response}'")
                                    else:
                                        logger.warning("Motion thread: No response after resume attempt")
                                elif 'Alarm' in status_response:
                                    # Machine is in Alarm state - attempt to unlock
                                    logger.warning(f"Motion thread: Machine in ALARM state: '{status_response}'")
                                    logger.info("Motion thread: Sending $X to unlock from Alarm...")

                                    # Send unlock command
                                    state.conn.send("$X\n")
                                    time.sleep(0.5)  # Give time for unlock to process

                                    # Re-check status after unlock attempt
                                    state.conn.send("?\n")
                                    time.sleep(0.2)

                                    # Read new status
                                    unlock_response = None
                                    for _ in range(5):
                                        resp = state.conn.readline()
                                        if resp:
                                            logger.info(f"Motion thread: Post-unlock response: '{resp}'")
                                            if '<' in resp:
                                                unlock_response = resp
                                                break
                                        time.sleep(0.05)

                                    if unlock_response:
                                        if 'Idle' in unlock_response:
                                            logger.info("Motion thread: Machine unlocked and is now Idle - retrying command")
                                            # Don't return True - we need to resend the failed command
                                            break  # Break inner loop to retry the command
                                        elif 'Alarm' in unlock_response:
                                            # Still in Alarm - underlying issue persists (e.g., sensor triggered)
                                            logger.error(f"Motion thread: Still in ALARM after unlock: '{unlock_response}'")
                                            logger.error("Motion thread: Machine may need physical attention")
                                            state.stop_requested = True
                                            return False
                                    else:
                                        logger.warning("Motion thread: No response after unlock attempt")
                                else:
                                    logger.warning(f"Motion thread: Unrecognized status response: '{status_response}'")
                            else:
                                logger.warning("Motion thread: No valid status response found in any received data")

                            # No valid status response - connection may be dead
                            timeout_retry_count += 1
                            if timeout_retry_count <= max_timeout_retries:
                                logger.warning(f"Motion thread: Recovery failed, will retry command ({timeout_retry_count}/{max_timeout_retries})")
                                time.sleep(0.1)
                                break  # Break inner loop to resend command
                            else:
                                logger.error(f"Motion thread: Max timeout retries ({max_timeout_retries}) exceeded")

                        except Exception as e:
                            logger.error(f"Motion thread: Error during timeout recovery: {e}")
                            import traceback
                            logger.error(f"Motion thread: Traceback: {traceback.format_exc()}")

                        # Max retries exceeded or recovery failed
                        logger.error("=" * 60)
                        logger.error("Motion thread: TIMEOUT RECOVERY FAILED - STOPPING PATTERN")
                        logger.error(f"  Failed command: {gcode}")
                        logger.error(f"  Timeout retries used: {timeout_retry_count}/{max_timeout_retries}")
                        logger.error(f"  Corruption retries used: {corruption_retry_count}/{max_corruption_retries}")
                        logger.error("  Possible causes:")
                        logger.error("    - Serial connection lost or unstable")
                        logger.error("    - Hardware controller unresponsive")
                        logger.error("    - USB power issue (try powered hub)")
                        logger.error("=" * 60)
                        state.stop_requested = True
                        return False

                    response = state.conn.readline()
                    if response:
                        logger.debug(f"Motion thread response: {response}")
                        if response.lower() == "ok":
                            logger.debug("Motion thread: Command execution confirmed.")
                            # Reset corruption retry count on success
                            if corruption_retry_count > 0:
                                logger.info(f"Motion thread: Command succeeded after {corruption_retry_count} corruption retry(ies)")
                            return True

                        # Handle GRBL errors
                        if response.lower().startswith("error"):
                            error_code = response.lower().split()[0] if response else ""

                            # Check if this is a corruption-type error (recoverable)
                            if error_code in corruption_error_codes:
                                corruption_retry_count += 1
                                if corruption_retry_count <= max_corruption_retries:
                                    logger.warning(f"Motion thread: Likely serial corruption detected ({response})")
                                    logger.warning(f"Motion thread: Retrying command ({corruption_retry_count}/{max_corruption_retries}): {gcode}")
                                    # Clear buffer and wait longer before retry
                                    if hasattr(state.conn, 'reset_input_buffer'):
                                        state.conn.reset_input_buffer()
                                    time.sleep(0.02)  # 20ms delay before retry
                                    break  # Break inner loop to retry send
                                else:
                                    logger.error(f"Motion thread: Max corruption retries ({max_corruption_retries}) exceeded")
                                    logger.error(f"Motion thread: GRBL error received: {response}")
                                    logger.error(f"Failed command: {gcode}")
                                    logger.error("Stopping pattern due to persistent serial corruption")
                                    state.stop_requested = True
                                    return False
                            else:
                                # Non-corruption error - stop immediately
                                logger.error(f"Motion thread: GRBL error received: {response}")
                                logger.error(f"Failed command: {gcode}")
                                logger.error("Stopping pattern due to GRBL error")
                                state.stop_requested = True
                                return False

                        # Handle GRBL alarms - machine needs attention
                        if "alarm" in response.lower():
                            logger.error(f"Motion thread: GRBL ALARM: {response}")
                            logger.error("Machine alarm triggered - stopping pattern")
                            state.stop_requested = True
                            return False

                        # FluidNC may echo commands back before sending 'ok'
                        # Silently ignore echoed G-code commands (G0, G1, $J, etc.)
                        if response.startswith(('G0', 'G1', 'G2', 'G3', '$J', 'M')):
                            logger.debug(f"Motion thread: Ignoring echoed command: {response}")
                            continue  # Read next line to get 'ok'

                        # Check for corruption indicator in MSG:ERR responses
                        if 'MSG:ERR' in response and 'Bad GCode' in response:
                            corruption_retry_count += 1
                            if corruption_retry_count <= max_corruption_retries:
                                logger.warning(f"Motion thread: Corrupted command detected: {response}")
                                logger.warning(f"Motion thread: Retrying command ({corruption_retry_count}/{max_corruption_retries}): {gcode}")
                                # Don't break yet - wait for the error:XX that follows
                                continue
                            # If we've exceeded retries, the error:XX handler above will catch it

                        # Log truly unexpected responses
                        logger.warning(f"Motion thread: Unexpected response: '{response}'")
                    else:
                        # Log periodically when waiting for response (every 30s)
                        if int(elapsed) > 0 and int(elapsed) % 30 == 0 and elapsed - int(elapsed) < 0.1:
                            logger.warning(f"Motion thread: Still waiting for 'ok' after {int(elapsed)}s for command: {gcode}")
                else:
                    # Inner while loop completed without break - shouldn't happen normally
                    # This means we hit timeout, which is handled above
                    continue

            except Exception as e:
                error_str = str(e)
                logger.warning(f"Motion thread error sending command: {error_str}")

                # Immediately return for device not configured errors
                if "Device not configured" in error_str or "Errno 6" in error_str:
                    logger.error(f"Motion thread: Device configuration error detected: {error_str}")
                    state.stop_requested = True
                    state.conn = None
                    state.is_connected = False
                    logger.info("Connection marked as disconnected due to device error")
                    return False

            # Retry on exception or corruption error
            logger.warning(f"Motion thread: Retrying {gcode}...")
            time.sleep(0.1)

# Global motion control thread instance
motion_controller = MotionControlThread()

async def cleanup_pattern_manager():
    """Clean up pattern manager resources"""
    global progress_update_task, pattern_lock, pause_event

    try:
        # Signal stop to allow any running pattern to exit gracefully
        state.stop_requested = True

        # Stop motion control thread
        motion_controller.stop()

        # Cancel progress update task if running
        if progress_update_task and not progress_update_task.done():
            try:
                progress_update_task.cancel()
                # Wait for task to actually cancel
                try:
                    await progress_update_task
                except asyncio.CancelledError:
                    pass
            except Exception as e:
                logger.error(f"Error cancelling progress update task: {e}")

        # Clean up pattern lock - wait for it to be released naturally, don't force release
        # Force releasing an asyncio.Lock can corrupt internal state if held by another coroutine
        current_lock = pattern_lock
        if current_lock and current_lock.locked():
            logger.info("Pattern lock is held, waiting for release (max 5s)...")
            try:
                # Wait with timeout for the lock to become available
                # Use wait_for for Python 3.9 compatibility (asyncio.timeout is 3.11+)
                async def acquire_lock():
                    async with current_lock:
                        pass  # Lock acquired means previous holder released it
                await asyncio.wait_for(acquire_lock(), timeout=5.0)
                logger.info("Pattern lock released normally")
            except asyncio.TimeoutError:
                logger.warning("Timed out waiting for pattern lock - creating fresh lock")
            except Exception as e:
                logger.error(f"Error waiting for pattern lock: {e}")

        # Clean up pause event - wake up any waiting tasks, then create fresh event
        current_event = pause_event
        if current_event:
            try:
                current_event.set()  # Wake up any waiting tasks
            except Exception as e:
                logger.error(f"Error setting pause event: {e}")

        # Clean up pause condition from state
        if state.pause_condition:
            try:
                with state.pause_condition:
                    state.pause_condition.notify_all()
                state.pause_condition = threading.Condition()
            except Exception as e:
                logger.error(f"Error cleaning up pause condition: {e}")

        # Clear all state variables
        state.current_playing_file = None
        state.execution_progress = 0
        state.is_running = False
        state.pause_requested = False
        state.stop_requested = True
        state.is_clearing = False

        # Reset machine position
        await connection_manager.update_machine_position()

        logger.info("Pattern manager resources cleaned up")

    except Exception as e:
        logger.error(f"Error during pattern manager cleanup: {e}")
    finally:
        # Reset to fresh instances instead of None to allow continued operation
        progress_update_task = None
        pattern_lock = asyncio.Lock()  # Fresh lock instead of None
        pause_event = asyncio.Event()  # Fresh event instead of None
        pause_event.set()  # Initially not paused

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

def get_first_rho_from_cache(file_path, cache_data=None):
    """Get the first rho value from cached metadata, falling back to file parsing if needed.

    Args:
        file_path: Path to the pattern file
        cache_data: Optional pre-loaded cache data dict to avoid repeated disk I/O
    """
    try:
        # Import cache_manager locally to avoid circular import
        from modules.core import cache_manager

        # Try to get from metadata cache first
        # Use relative path from THETA_RHO_DIR to match cache keys (which include subdirectories)
        file_name = os.path.relpath(file_path, THETA_RHO_DIR)

        # Use provided cache_data if available, otherwise load from disk
        if cache_data is not None:
            # Extract metadata directly from provided cache
            data_section = cache_data.get('data', {})
            if file_name in data_section:
                cached_entry = data_section[file_name]
                metadata = cached_entry.get('metadata')
                # When cache_data is provided, trust it without checking mtime
                # This significantly speeds up bulk operations (playlists with 1000+ patterns)
                # by avoiding 1000+ os.path.getmtime() calls on slow storage (e.g., Pi SD cards)
                if metadata and 'first_coordinate' in metadata:
                    return metadata['first_coordinate']['y']
        else:
            # Fall back to loading cache from disk (original behavior)
            metadata = cache_manager.get_pattern_metadata(file_name)
            if metadata and 'first_coordinate' in metadata:
                # In the cache, 'x' is theta and 'y' is rho
                return metadata['first_coordinate']['y']

        # Fallback to parsing the file if not in cache
        logger.debug(f"Metadata not cached for {file_name}, parsing file")
        coordinates = parse_theta_rho_file(file_path)
        if coordinates:
            return coordinates[0][1]  # Return rho value

        return None
    except Exception as e:
        logger.warning(f"Error getting first rho from cache for {file_path}: {str(e)}")
        return None

def get_clear_pattern_file(clear_pattern_mode, path=None, cache_data=None):
    """Return a .thr file path based on pattern_name and table type.

    Args:
        clear_pattern_mode: The clear pattern mode to use
        path: Optional path to the pattern file for adaptive mode
        cache_data: Optional pre-loaded cache data dict to avoid repeated disk I/O
    """
    if not clear_pattern_mode or clear_pattern_mode == 'none':
        return

    # Define patterns for each table type
    clear_patterns = {
        'dune_weaver': {
            'clear_from_out': './patterns/clear_from_out.thr',
            'clear_from_in': './patterns/clear_from_in.thr',
            'clear_sideway': './patterns/clear_sideway.thr'
        },
        'dune_weaver_mini': {
            'clear_from_out': './patterns/clear_from_out_mini.thr',
            'clear_from_in': './patterns/clear_from_in_mini.thr',
            'clear_sideway': './patterns/clear_sideway_mini.thr'
        },
        'dune_weaver_mini_pro': {
            'clear_from_out': './patterns/clear_from_out_mini.thr',
            'clear_from_in': './patterns/clear_from_in_mini.thr',
            'clear_sideway': './patterns/clear_sideway_mini.thr'
        },
        'dune_weaver_pro': {
            'clear_from_out': './patterns/clear_from_out_pro.thr',
            'clear_from_out_Ultra': './patterns/clear_from_out_Ultra.thr',
            'clear_from_in': './patterns/clear_from_in_pro.thr',
            'clear_from_in_Ultra': './patterns/clear_from_in_Ultra.thr',
            'clear_sideway': './patterns/clear_sideway_pro.thr'
        }
    }

    # Get patterns for current table type, fallback to standard patterns if type not found
    table_patterns = clear_patterns.get(state.table_type, clear_patterns['dune_weaver'])

    # Check for custom patterns first
    if state.custom_clear_from_out and clear_pattern_mode in ['clear_from_out', 'adaptive']:
        if clear_pattern_mode == 'adaptive':
            # For adaptive mode, use cached metadata to check first rho
            if path:
                first_rho = get_first_rho_from_cache(path, cache_data)
                if first_rho is not None and first_rho < 0.5:
                    # Use custom clear_from_out if set
                    custom_path = os.path.join('./patterns', state.custom_clear_from_out)
                    if os.path.exists(custom_path):
                        logger.debug(f"Using custom clear_from_out: {custom_path}")
                        return custom_path
        elif clear_pattern_mode == 'clear_from_out':
            custom_path = os.path.join('./patterns', state.custom_clear_from_out)
            if os.path.exists(custom_path):
                logger.debug(f"Using custom clear_from_out: {custom_path}")
                return custom_path

    if state.custom_clear_from_in and clear_pattern_mode in ['clear_from_in', 'adaptive']:
        if clear_pattern_mode == 'adaptive':
            # For adaptive mode, use cached metadata to check first rho
            if path:
                first_rho = get_first_rho_from_cache(path, cache_data)
                if first_rho is not None and first_rho >= 0.5:
                    # Use custom clear_from_in if set
                    custom_path = os.path.join('./patterns', state.custom_clear_from_in)
                    if os.path.exists(custom_path):
                        logger.debug(f"Using custom clear_from_in: {custom_path}")
                        return custom_path
        elif clear_pattern_mode == 'clear_from_in':
            custom_path = os.path.join('./patterns', state.custom_clear_from_in)
            if os.path.exists(custom_path):
                logger.debug(f"Using custom clear_from_in: {custom_path}")
                return custom_path

    logger.debug(f"Clear pattern mode: {clear_pattern_mode} for table type: {state.table_type}")

    if clear_pattern_mode == "random":
        return random.choice(list(table_patterns.values()))

    if clear_pattern_mode == 'adaptive':
        if not path:
            logger.warning("No path provided for adaptive clear pattern")
            return random.choice(list(table_patterns.values()))

        # Use cached metadata to get first rho value
        first_rho = get_first_rho_from_cache(path, cache_data)
        if first_rho is None:
            logger.warning("Could not determine first rho value for adaptive clear pattern")
            return random.choice(list(table_patterns.values()))

        if first_rho < 0.5:
            return table_patterns['clear_from_out']
        else:
            return table_patterns['clear_from_in']
    else:
        if clear_pattern_mode not in table_patterns:
            return False
        return table_patterns[clear_pattern_mode]

def is_clear_pattern(file_path):
    """Check if a file path is a clear pattern file."""
    # Get all possible clear pattern files for all table types
    clear_patterns = []
    for table_type in ['dune_weaver', 'dune_weaver_mini', 'dune_weaver_pro']:
        clear_patterns.extend([
            f'./patterns/clear_from_out{("_" + table_type.split("_")[-1]) if table_type != "dune_weaver" else ""}.thr',
            f'./patterns/clear_from_in{("_" + table_type.split("_")[-1]) if table_type != "dune_weaver" else ""}.thr',
            f'./patterns/clear_sideway{("_" + table_type.split("_")[-1]) if table_type != "dune_weaver" else ""}.thr'
        ])
    
    # Normalize paths for comparison
    normalized_path = os.path.normpath(file_path)
    normalized_clear_patterns = [os.path.normpath(p) for p in clear_patterns]
    
    # Check if the file path matches any clear pattern path
    return normalized_path in normalized_clear_patterns

async def _execute_pattern_internal(file_path):
    """Internal function to execute a pattern file. Must be called with lock already held.

    Args:
        file_path: Path to the .thr file to execute

    Returns:
        True if pattern completed successfully, False if stopped/skipped
    """
    # Run file parsing in thread to avoid blocking the event loop
    coordinates = await asyncio.to_thread(parse_theta_rho_file, file_path)
    total_coordinates = len(coordinates)

    # Cache coordinates in state for frontend preview (avoids re-parsing large files)
    state._current_coordinates = coordinates

    if total_coordinates < 2:
        logger.warning("Not enough coordinates for interpolation")
        return False

    # Determine if this is a clearing pattern
    is_clear_file = is_clear_pattern(file_path)

    if is_clear_file:
        initial_speed = state.clear_pattern_speed if state.clear_pattern_speed is not None else state.speed
        logger.info(f"Running clearing pattern at initial speed {initial_speed}")
    else:
        logger.info(f"Running normal pattern at initial speed {state.speed}")

    state.execution_progress = (0, total_coordinates, None, 0)

    # stop actions without resetting the playlist, and don't wait for lock (we already have it)
    # Preserve is_clearing flag since stop_actions resets it
    was_clearing = state.is_clearing
    await stop_actions(clear_playlist=False, wait_for_lock=False)
    state.is_clearing = was_clearing

    state.current_playing_file = file_path
    state.stop_requested = False

    # Reset LED idle timeout activity time when pattern starts
    import time as time_module
    state.dw_led_last_activity_time = time_module.time()

    logger.info(f"Starting pattern execution: {file_path}")
    logger.info(f"t: {state.current_theta}, r: {state.current_rho}")
    await reset_theta()

    start_time = time.time()
    total_pause_time = 0  # Track total time spent paused (manual + scheduled)
    if state.led_controller:
        logger.info(f"Setting LED to playing effect: {state.dw_led_playing_effect}")
        await state.led_controller.effect_playing_async(state.dw_led_playing_effect)
        # Cancel idle timeout when playing starts
        idle_timeout_manager.cancel_timeout()

    with tqdm(
        total=total_coordinates,
        unit="coords",
        desc=f"Executing Pattern {file_path}",
        dynamic_ncols=True,
        disable=False,
        mininterval=1.0
    ) as pbar:
        for i, coordinate in enumerate(coordinates):
            theta, rho = coordinate
            if state.stop_requested:
                logger.info("Execution stopped by user")
                if state.led_controller:
                    await state.led_controller.effect_idle_async(state.dw_led_idle_effect)
                    start_idle_led_timeout()
                break

            if state.skip_requested:
                logger.info("Skipping pattern...")
                await connection_manager.check_idle_async()
                if state.led_controller:
                    await state.led_controller.effect_idle_async(state.dw_led_idle_effect)
                    start_idle_led_timeout()
                break

            # Wait for resume if paused (manual or scheduled)
            manual_pause = state.pause_requested
            # Only check scheduled pause during pattern if "finish pattern first" is NOT enabled
            scheduled_pause = is_in_scheduled_pause_period() if not state.scheduled_pause_finish_pattern else False

            if manual_pause or scheduled_pause:
                pause_start = time.time()  # Track when pause started
                if manual_pause and scheduled_pause:
                    logger.info("Execution paused (manual + scheduled pause active)...")
                elif manual_pause:
                    logger.info("Execution paused (manual)...")
                else:
                    logger.info("Execution paused (scheduled pause period)...")
                    # Turn off LED controller if scheduled pause and control_wled is enabled
                    if state.scheduled_pause_control_wled and state.led_controller:
                        logger.info("Turning off LED lights during Still Sands period")
                        await state.led_controller.set_power_async(0)

                # Only show idle effect if NOT in scheduled pause with LED control
                # (manual pause always shows idle effect)
                if state.led_controller and not (scheduled_pause and state.scheduled_pause_control_wled):
                    await state.led_controller.effect_idle_async(state.dw_led_idle_effect)
                    start_idle_led_timeout()

                # Remember if we turned off LED controller for scheduled pause
                wled_was_off_for_scheduled = scheduled_pause and state.scheduled_pause_control_wled and not manual_pause

                # Wait until both manual pause is released AND we're outside scheduled pause period
                # Also check for stop/skip requests to allow immediate interruption
                interrupted = False
                while state.pause_requested or is_in_scheduled_pause_period():
                    # Check for stop/skip first
                    if state.stop_requested:
                        logger.info("Stop requested during pause, exiting")
                        interrupted = True
                        break
                    if state.skip_requested:
                        logger.info("Skip requested during pause, skipping pattern")
                        interrupted = True
                        break

                    if state.pause_requested:
                        # For manual pause, wait on multiple events for immediate response
                        # Wake on: resume, stop, skip, or timeout (for flag polling fallback)
                        pause_event = get_pause_event()
                        stop_event = state.get_stop_event()
                        skip_event = state.get_skip_event()

                        wait_tasks = [asyncio.create_task(pause_event.wait(), name='pause')]
                        if stop_event:
                            wait_tasks.append(asyncio.create_task(stop_event.wait(), name='stop'))
                        if skip_event:
                            wait_tasks.append(asyncio.create_task(skip_event.wait(), name='skip'))
                        # Add timeout to ensure we periodically check flags even if events aren't set
                        # This handles the case where stop is called from sync context (no event loop)
                        timeout_task = asyncio.create_task(asyncio.sleep(1.0), name='timeout')
                        wait_tasks.append(timeout_task)

                        try:
                            done, pending = await asyncio.wait(
                                wait_tasks, return_when=asyncio.FIRST_COMPLETED
                            )
                        finally:
                            for task in pending:
                                task.cancel()
                            for task in pending:
                                try:
                                    await task
                                except asyncio.CancelledError:
                                    pass
                    else:
                        # For scheduled pause, use wait_for_interrupt for instant response
                        result = await state.wait_for_interrupt(timeout=1.0)
                        if result in ('stopped', 'skipped'):
                            interrupted = True
                            break

                total_pause_time += time.time() - pause_start  # Add pause duration

                if interrupted:
                    # Exit the coordinate loop if we were interrupted
                    break

                logger.info("Execution resumed...")
                if state.led_controller:
                    # Turn LED controller back on if it was turned off for scheduled pause
                    if wled_was_off_for_scheduled:
                        logger.info("Turning LED lights back on as Still Sands period ended")
                        await state.led_controller.set_power_async(1)
                        # CRITICAL: Give LED controller time to fully power on before sending more commands
                        # Without this delay, rapid-fire requests can crash controllers on resource-constrained Pis
                        await asyncio.sleep(0.5)
                    await state.led_controller.effect_playing_async(state.dw_led_playing_effect)
                    # Cancel idle timeout when resuming from pause
                    idle_timeout_manager.cancel_timeout()

            # Dynamically determine the speed for each movement
            # Use clear_pattern_speed if it's set and this is a clear file, otherwise use state.speed
            if is_clear_file and state.clear_pattern_speed is not None:
                current_speed = state.clear_pattern_speed
            else:
                current_speed = state.speed

            await move_polar(theta, rho, current_speed)

            # Update progress for all coordinates including the first one
            pbar.update(1)
            elapsed_time = time.time() - start_time
            estimated_remaining_time = (total_coordinates - (i + 1)) / pbar.format_dict['rate'] if pbar.format_dict['rate'] and total_coordinates else 0
            state.execution_progress = (i + 1, total_coordinates, estimated_remaining_time, elapsed_time)

            # Add a small delay to allow other async operations
            await asyncio.sleep(0.001)

    # Update progress one last time to show 100%
    elapsed_time = time.time() - start_time
    actual_execution_time = elapsed_time - total_pause_time
    state.execution_progress = (total_coordinates, total_coordinates, 0, elapsed_time)
    # Give WebSocket a chance to send the final update
    await asyncio.sleep(0.1)

    # Log execution time (only for completed patterns, not stopped/skipped)
    was_completed = not state.stop_requested and not state.skip_requested
    pattern_name = os.path.basename(file_path)
    effective_speed = state.clear_pattern_speed if (is_clear_file and state.clear_pattern_speed is not None) else state.speed
    log_execution_time(
        pattern_name=pattern_name,
        table_type=state.table_type,
        speed=effective_speed,
        actual_time=actual_execution_time,
        total_coordinates=total_coordinates,
        was_completed=was_completed
    )

    if not state.conn:
        logger.error("Device is not connected. Stopping pattern execution.")
        return False

    await connection_manager.check_idle_async()

    # Set LED back to idle when pattern completes normally (not stopped early)
    if state.led_controller and not state.stop_requested:
        logger.info(f"Setting LED to idle effect: {state.dw_led_idle_effect}")
        await state.led_controller.effect_idle_async(state.dw_led_idle_effect)
        start_idle_led_timeout()
        logger.debug("LED effect set to idle after pattern completion")

    return was_completed


async def run_theta_rho_file(file_path, is_playlist=False, clear_pattern=None, cache_data=None):
    """Run a theta-rho file with optional pre-execution clear pattern.

    Args:
        file_path: Path to the main .thr file to execute
        is_playlist: True if running as part of a playlist
        clear_pattern: Clear pattern mode ('adaptive', 'clear_from_in', 'clear_from_out', 'none', or None)
        cache_data: Pre-loaded metadata cache for adaptive clear pattern selection
    """
    lock = get_pattern_lock()
    if lock.locked():
        logger.warning("Another pattern is already running. Cannot start a new one.")
        return

    async with lock:  # This ensures only one pattern can run at a time
        # Clear any stale pause state from previous playlist
        state.pause_time_remaining = 0
        state.original_pause_time = None

        # Start progress update task only if not part of a playlist
        global progress_update_task
        if not is_playlist and not progress_update_task:
            progress_update_task = asyncio.create_task(broadcast_progress())

        # Run clear pattern first if specified
        if clear_pattern and clear_pattern != 'none':
            clear_file_path = get_clear_pattern_file(clear_pattern, file_path, cache_data)
            if clear_file_path:
                logger.info(f"Running pre-execution clear pattern: {clear_file_path}")
                state.is_clearing = True
                await _execute_pattern_internal(clear_file_path)
                state.is_clearing = False
                # Reset skip flag after clear pattern (if user skipped clear, continue to main)
                state.skip_requested = False

        # Check if stopped during clear pattern
        if state.stop_requested:
            logger.info("Execution stopped during clear pattern")
            if not is_playlist:
                state.current_playing_file = None
                state.execution_progress = None
            return

        # Run the main pattern
        completed = await _execute_pattern_internal(file_path)

        # Only clear state if not part of a playlist
        if not is_playlist:
            state.current_playing_file = None
            state.execution_progress = None
            logger.info("Pattern execution completed and state cleared")
            # Only cancel progress update task if not part of a playlist
            if progress_update_task:
                progress_update_task.cancel()
                try:
                    await progress_update_task
                except asyncio.CancelledError:
                    pass
                progress_update_task = None
        else:
            logger.info("Pattern execution completed, maintaining state for playlist")
            

async def run_theta_rho_files(file_paths, pause_time=0, clear_pattern=None, run_mode="single", shuffle=False):
    """Run multiple .thr files in sequence with options.

    The playlist now stores only main patterns. Clear patterns are executed dynamically
    before each main pattern based on the clear_pattern option.
    """
    state.stop_requested = False

    # Track whether we actually started executing patterns.
    # If cancelled before execution begins (e.g., by TestClient cleanup),
    # we should NOT clear state that was set by the caller.
    task_started_execution = False

    # Reset LED idle timeout activity time when playlist starts
    import time as time_module
    state.dw_led_last_activity_time = time_module.time()

    # Set initial playlist state only if not already set by caller (playlist_manager).
    # This ensures backward compatibility when this function is called directly.
    if state.playlist_mode is None:
        state.playlist_mode = run_mode
    if state.current_playlist_index is None:
        state.current_playlist_index = 0

    # Start progress update task for the playlist
    global progress_update_task
    if not progress_update_task:
        progress_update_task = asyncio.create_task(broadcast_progress())

    # Shuffle main patterns if requested (before starting)
    if shuffle:
        random.shuffle(file_paths)
        logger.info("Playlist shuffled")

    # Store patterns in state only if not already set by caller.
    # The caller (playlist_manager.run_playlist) sets this before creating the task.
    if state.current_playlist is None:
        state.current_playlist = file_paths

    try:
        while True:
            # Load metadata cache once per playlist iteration (for adaptive clear patterns)
            cache_data = None
            if clear_pattern and clear_pattern in ['adaptive', 'clear_from_in', 'clear_from_out']:
                from modules.core import cache_manager
                cache_data = await asyncio.to_thread(cache_manager.load_metadata_cache)
                logger.info(f"Loaded metadata cache for {len(cache_data.get('data', {}))} patterns")

            # Reset pattern counter at the start of the playlist
            state.patterns_since_last_home = 0

            # Execute main patterns using index-based access
            # This allows the playlist to be reordered during execution
            idx = 0
            while state.current_playlist and idx < len(state.current_playlist):
                state.current_playlist_index = idx

                if state.stop_requested or not state.current_playlist:
                    logger.info("Execution stopped")
                    return

                # Get the pattern at the current index (may have changed due to reordering)
                file_path = state.current_playlist[idx]
                logger.info(f"Running pattern {idx + 1}/{len(state.current_playlist)}: {file_path}")

                # Mark that we've started actual execution (for cleanup logic)
                task_started_execution = True

                # Clear pause state when starting a new pattern (prevents stale "waiting" UI)
                state.pause_time_remaining = 0
                state.original_pause_time = None

                # Execute the pattern with optional clear pattern
                await run_theta_rho_file(
                    file_path,
                    is_playlist=True,
                    clear_pattern=clear_pattern,
                    cache_data=cache_data
                )

                # Increment pattern counter (auto-home check happens after pause time)
                state.patterns_since_last_home += 1
                logger.debug(f"Patterns since last home: {state.patterns_since_last_home}")

                # Check for scheduled pause after pattern completes (when "finish pattern first" is enabled)
                if state.scheduled_pause_finish_pattern and is_in_scheduled_pause_period() and not state.stop_requested and not state.skip_requested:
                    logger.info("Pattern completed. Entering Still Sands period (finish pattern first mode)...")

                    wled_was_off_for_scheduled = False
                    if state.scheduled_pause_control_wled and state.led_controller:
                        logger.info("Turning off LED lights during Still Sands period")
                        await state.led_controller.set_power_async(0)
                        wled_was_off_for_scheduled = True
                    elif state.led_controller:
                        await state.led_controller.effect_idle_async(state.dw_led_idle_effect)
                        start_idle_led_timeout()

                    # Wait for scheduled pause to end, but allow stop/skip to interrupt
                    result = await wait_with_interrupt(
                        is_in_scheduled_pause_period,
                        check_stop=True,
                        check_skip=True,
                    )

                    if result == 'completed':
                        logger.info("Still Sands period ended. Resuming playlist...")
                        if state.led_controller:
                            if wled_was_off_for_scheduled:
                                logger.info("Turning LED lights back on as Still Sands period ended")
                                await state.led_controller.set_power_async(1)
                                await asyncio.sleep(0.5)
                            await state.led_controller.effect_playing_async(state.dw_led_playing_effect)
                            idle_timeout_manager.cancel_timeout()

                # Handle pause between patterns
                if state.current_playlist and idx < len(state.current_playlist) - 1 and not state.stop_requested and pause_time > 0 and not state.skip_requested:
                    logger.info(f"Pausing for {pause_time} seconds")
                    state.original_pause_time = pause_time
                    pause_start = time.time()
                    while time.time() - pause_start < pause_time:
                        state.pause_time_remaining = pause_start + pause_time - time.time()
                        if state.skip_requested:
                            logger.info("Pause interrupted by skip request")
                            break
                        await asyncio.sleep(1)
                    # Clear both pause state vars immediately (so UI updates right away)
                    state.pause_time_remaining = 0
                    state.original_pause_time = None

                # Auto-home after pause time, before next clear pattern starts
                # Only home if there's a next pattern and we haven't been stopped
                if (state.auto_home_enabled and
                    state.patterns_since_last_home >= state.auto_home_after_patterns and
                    state.current_playlist and idx < len(state.current_playlist) - 1 and
                    not state.stop_requested):
                    logger.info(f"Auto-homing triggered after {state.patterns_since_last_home} patterns (before next clear pattern)")
                    try:
                        success = await asyncio.to_thread(connection_manager.home)
                        if success:
                            logger.info("Auto-homing completed successfully")
                            state.patterns_since_last_home = 0
                        else:
                            logger.warning("Auto-homing failed, continuing with playlist")
                    except Exception as e:
                        logger.error(f"Error during auto-homing: {e}")

                state.skip_requested = False
                idx += 1

            if run_mode == "indefinite":
                logger.info("Playlist completed. Restarting as per 'indefinite' run mode")
                if pause_time > 0:
                    pause_start = time.time()
                    while time.time() - pause_start < pause_time:
                        state.pause_time_remaining = pause_start + pause_time - time.time()
                        if state.skip_requested:
                            logger.info("Pause interrupted by skip request")
                            break
                        await asyncio.sleep(1)
                    # Clear both pause state vars immediately (so UI updates right away)
                    state.pause_time_remaining = 0
                    state.original_pause_time = None
                continue
            else:
                logger.info("Playlist completed")
                break

    except asyncio.CancelledError:
        # Task was cancelled externally (e.g., by TestClient cleanup, or explicit cancellation).
        # Do NOT clear playlist state - preserve what the caller set.
        logger.info("Playlist task was cancelled externally, preserving state")
        if progress_update_task:
            progress_update_task.cancel()
            try:
                await progress_update_task
            except asyncio.CancelledError:
                pass
            progress_update_task = None
        raise  # Re-raise to signal cancellation
    finally:
        if progress_update_task:
            progress_update_task.cancel()
            try:
                await progress_update_task
            except asyncio.CancelledError:
                pass
            progress_update_task = None

        # Check if we're exiting due to CancelledError - if so, don't clear state.
        # State should only be cleared when:
        # 1. Task completed normally (all patterns executed)
        # 2. Task was stopped by user request (stop_requested)
        # NOT when task was cancelled externally (CancelledError)
        import sys
        exc_type = sys.exc_info()[0]
        if exc_type is asyncio.CancelledError:
            logger.info("Task exiting due to cancellation, state preserved for caller")
        else:
            # Normal completion or user-requested stop - clear state
            state.current_playing_file = None
            state.execution_progress = None
            state.current_playlist = None
            state.current_playlist_index = None
            state.playlist_mode = None
            state.pause_time_remaining = 0

            if state.led_controller:
                await state.led_controller.effect_idle_async(state.dw_led_idle_effect)
                start_idle_led_timeout()

            logger.info("All requested patterns completed (or stopped) and state cleared")

async def stop_actions(clear_playlist = True, wait_for_lock = True):
    """Stop all current actions and wait for pattern to fully release.

    Args:
        clear_playlist: Whether to clear playlist state
        wait_for_lock: Whether to wait for pattern_lock to be released. Set to False when
                      called from within pattern execution to avoid deadlock.

    Returns:
        True if stopped cleanly, False if timed out waiting for pattern lock
    """
    timed_out = False
    try:
        with state.pause_condition:
            state.pause_requested = False
            state.stop_requested = True
            state.is_clearing = False

            # Always clear pause time between patterns on stop
            state.pause_time_remaining = 0
            state.original_pause_time = None

            if clear_playlist:
                # Clear playlist state
                state.current_playlist = None
                state.current_playlist_index = None
                state.playlist_mode = None

                # Cancel progress update task if we're clearing the playlist
                global progress_update_task
                if progress_update_task and not progress_update_task.done():
                    progress_update_task.cancel()

                # Cancel the playlist task itself (late import to avoid circular dependency)
                from modules.core import playlist_manager
                await playlist_manager.cancel_current_playlist()

            state.pause_condition.notify_all()

        # Also set the pause event to wake up any paused patterns
        get_pause_event().set()

        # Send stop command to motion thread to clear its queue
        if motion_controller.running:
            motion_controller.command_queue.put(MotionCommand('stop'))

        # Wait for the pattern lock to be released before continuing
        # This ensures that when stop_actions completes, the pattern has fully stopped
        # Skip this if called from within pattern execution to avoid deadlock
        lock = get_pattern_lock()
        if wait_for_lock and lock.locked():
            logger.info("Waiting for pattern to fully stop...")
            # Use a timeout to prevent hanging forever
            # Use wait_for for Python 3.9 compatibility (asyncio.timeout is 3.11+)
            try:
                async def acquire_stop_lock():
                    async with lock:
                        logger.info("Pattern lock acquired - pattern has fully stopped")
                await asyncio.wait_for(acquire_stop_lock(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for pattern to stop - forcing cleanup")
                timed_out = True
                # Force cleanup of state even if pattern didn't release lock gracefully
                state.current_playing_file = None
                state.execution_progress = None
                state.is_running = False

        # Clear current playing file only when clearing the entire playlist.
        # When clear_playlist=False (called from within pattern execution), the caller
        # will set current_playing_file to the new pattern immediately after.
        if clear_playlist:
            state.current_playing_file = None
            state.execution_progress = None

        # Clear stop_requested now that the pattern has stopped - this allows
        # check_idle_async to work (it exits early if stop_requested is True)
        state.stop_requested = False

        # Wait for hardware to reach idle state before returning
        # This ensures the machine has physically stopped moving
        if not timed_out:
            idle = await connection_manager.check_idle_async(timeout=30.0)
            if not idle:
                logger.warning("Machine did not reach idle after stop")

        # Call async function directly since we're in async context
        await connection_manager.update_machine_position()
        return not timed_out
    except Exception as e:
        logger.error(f"Error during stop_actions: {e}")
        # Force cleanup state on error
        state.current_playing_file = None
        state.execution_progress = None
        state.is_running = False
        # Ensure we still update machine position even if there's an error
        try:
            await connection_manager.update_machine_position()
        except Exception as update_err:
            logger.error(f"Error updating machine position on error: {update_err}")
        return False

async def move_polar(theta, rho, speed=None):
    """
    Queue a motion command to be executed in the dedicated motion control thread.
    This makes motion control non-blocking for API endpoints.

    Args:
        theta (float): Target theta coordinate
        rho (float): Target rho coordinate
        speed (int, optional): Speed override. If None, uses state.speed
    """
    # Note: stop_requested is cleared once at pattern start (execute_theta_rho_file line 890)
    # Don't clear it here on every coordinate - causes performance issues with event system

    # Ensure motion control thread is running
    if not motion_controller.running:
        motion_controller.start()

    # Create future for async/await pattern
    loop = asyncio.get_event_loop()
    future = loop.create_future()

    # Create and queue motion command
    command = MotionCommand(
        command_type='move',
        theta=theta,
        rho=rho,
        speed=speed,
        future=future
    )

    motion_controller.command_queue.put(command)
    logger.debug(f"Queued motion command: theta={theta}, rho={rho}, speed={speed}")

    # Wait for command completion
    await future
    
def pause_execution():
    """Pause pattern execution using asyncio Event."""
    logger.info("Pausing pattern execution")
    state.pause_requested = True
    get_pause_event().clear()  # Clear the event to pause execution
    return True

def resume_execution():
    """Resume pattern execution using asyncio Event."""
    logger.info("Resuming pattern execution")
    state.pause_requested = False
    get_pause_event().set()  # Set the event to resume execution
    return True
    
async def reset_theta():
    """
    Reset theta to [0, 2π) range and hard reset machine position using $Bye.

    $Bye sends a soft reset to FluidNC which resets the controller and clears
    all position counters to 0. This is more reliable than G92 which only sets
    a work coordinate offset without changing the actual machine position (MPos).

    IMPORTANT: We wait for machine to be idle before sending $Bye to avoid
    error:25 ("Feed rate not specified in block") which can occur if the
    controller is still processing commands when reset is triggered.
    """
    logger.info('Resetting Theta')

    # Wait for machine to be idle before reset to prevent error:25
    if state.conn and state.conn.is_connected():
        logger.info("Waiting for machine to be idle before reset...")
        idle = await connection_manager.check_idle_async(timeout=30)
        if not idle:
            logger.warning("Machine not idle after 30s, proceeding with reset anyway")

    state.current_theta = state.current_theta % (2 * pi)

    # Hard reset machine position using $Bye via connection_manager
    success = await connection_manager.perform_soft_reset()
    if not success:
        logger.error("Soft reset failed - theta reset may be unreliable")

def set_speed(new_speed):
    state.speed = new_speed
    logger.info(f'Set new state.speed {new_speed}')

def get_status():
    """Get the current status of pattern execution."""
    status = {
        "current_file": state.current_playing_file,
        "is_paused": state.pause_requested or is_in_scheduled_pause_period(),
        "manual_pause": state.pause_requested,
        "scheduled_pause": is_in_scheduled_pause_period(),
        "is_running": bool(state.current_playing_file and not state.stop_requested),
        "is_homing": state.is_homing,
        "sensor_homing_failed": state.sensor_homing_failed,
        "is_clearing": state.is_clearing,
        "progress": None,
        "playlist": None,
        "speed": state.speed,
        "pause_time_remaining": state.pause_time_remaining,
        "original_pause_time": getattr(state, 'original_pause_time', None),
        "connection_status": state.conn.is_connected() if state.conn else False,
        "current_theta": state.current_theta,
        "current_rho": state.current_rho
    }
    
    # Add playlist information if available
    if state.current_playlist and state.current_playlist_index is not None:
        # When a clear pattern is running, the "next" pattern is the current main pattern
        # (since the clear pattern runs before the main pattern at current_playlist_index)
        if state.is_clearing:
            next_file = state.current_playlist[state.current_playlist_index]
        else:
            next_index = state.current_playlist_index + 1
            next_file = state.current_playlist[next_index] if next_index < len(state.current_playlist) else None

        status["playlist"] = {
            "current_index": state.current_playlist_index,
            "total_files": len(state.current_playlist),
            "mode": state.playlist_mode,
            "next_file": next_file,
            "files": state.current_playlist,
            "name": state.current_playlist_name
        }
    
    if state.execution_progress:
        current, total, remaining_time, elapsed_time = state.execution_progress
        status["progress"] = {
            "current": current,
            "total": total,
            "remaining_time": remaining_time,
            "elapsed_time": elapsed_time,
            "percentage": (current / total * 100) if total > 0 else 0
        }

        # Add historical execution time if available for this pattern at current speed
        if state.current_playing_file:
            pattern_name = os.path.basename(state.current_playing_file)
            historical_time = get_last_completed_execution_time(pattern_name, state.speed)
            if historical_time:
                status["progress"]["last_completed_time"] = historical_time

    return status

async def broadcast_progress():
    """Background task to broadcast progress updates."""
    from main import broadcast_status_update
    while True:
        # Send status updates regardless of pattern_lock state
        status = get_status()
        
        # Use the existing broadcast function from main.py
        await broadcast_status_update(status)
            
        # Check if we should stop broadcasting
        if not state.current_playlist:
            # If no playlist, only stop if no pattern is being executed
            if not get_pattern_lock().locked():
                logger.info("No playlist or pattern running, stopping broadcast")
                break
        
        # Wait before next update
        await asyncio.sleep(1)
