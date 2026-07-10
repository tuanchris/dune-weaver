"""
Connection manager — drives the headless FluidNC board over HTTP.

The board firmware now owns kinematics, `.thr` playback, progress and homing
(contract: the firmware repo's API.md). This module is the thin seam the backend
uses to talk to it: it builds a FluidNCClient, exposes the same public functions
the rest of the app already calls (connect_device, device_init, home,
check_idle_async, is_machine_idle, update_machine_position, perform_soft_reset,
restart_connection, list_serial_ports), and keeps the LED hooks intact. The old
serial/websocket GRBL transport, coordinate streaming, and the $H/$J homing
handshake are gone — the firmware does all of that itself.
"""

import os
import time
import math
import logging
import asyncio
import threading

from modules.core.state import state
from modules.connection.fluidnc_client import FluidNCClient
from modules.led.led_interface import LEDInterface
from modules.led.idle_timeout_manager import idle_timeout_manager

logger = logging.getLogger(__name__)

DEFAULT_BOARD_URL = "http://192.168.68.160"


def _normalize_board_url(value: str) -> str:
    """Accept a bare IP/host or a full URL and return a normalized base URL."""
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = "http://" + value
    return value


def board_url() -> str:
    """Resolve the board base URL: explicit setting > env > default."""
    return (
        _normalize_board_url(getattr(state, "board_url", None) or "")
        or _normalize_board_url(os.environ.get("DUNE_BOARD_URL", ""))
        or DEFAULT_BOARD_URL
    )


async def _check_table_is_idle() -> bool:
    """Helper for the idle-LED timeout: table counts as idle when nothing plays."""
    return not state.current_playing_file or state.pause_requested


def _start_idle_led_timeout():
    """Start idle LED timeout if enabled."""
    if not state.dw_led_idle_timeout_enabled or state.dw_led_idle_timeout_minutes <= 0:
        return
    logger.debug(f"Starting idle LED timeout: {state.dw_led_idle_timeout_minutes} minutes")
    idle_timeout_manager.start_idle_timeout(
        timeout_minutes=state.dw_led_idle_timeout_minutes,
        state=state,
        check_idle_callback=_check_table_is_idle,
    )


###############################################################################
# Status helpers
###############################################################################

def apply_status(st: dict) -> None:
    """Mirror the board's /sand_status fields into app state."""
    if not st:
        return
    if "theta" in st:
        state.current_theta = st["theta"]
    if "rho" in st:
        state.current_rho = st["rho"]
    if st.get("feed"):
        state.speed = st["feed"]


def poll_status_once() -> dict | None:
    """Read /sand_status once and mirror it into state. Returns the raw dict."""
    if not state.conn:
        return None
    try:
        st = state.conn.get_status()
        apply_status(st)
        return st
    except Exception as e:
        logger.debug(f"Status poll failed: {e}")
        return None


###############################################################################
# Connection lifecycle
###############################################################################

def list_serial_ports():
    """
    There are no serial ports anymore — the board is reached over HTTP. Return
    the board URL as the single selectable "port" so the frontend's connection
    panel keeps working unchanged.
    """
    return [board_url()]


def _push_homing_settings():
    """Push the host's homing preferences onto the board (best effort)."""
    try:
        state.conn.set_homing_mode("sensor" if state.homing == 1 else "crash")
        state.conn.set_theta_offset(state.angular_homing_offset_degrees)
    except Exception as e:
        logger.warning(f"Could not push homing settings to board: {e}")


def _sync_homing_settings():
    """
    Reconcile homing config between host and board. If the user has explicitly
    chosen a homing mode (homing_user_override), the host is authoritative and we
    push it to the board. Otherwise we *adopt* the board's configured mode/offset
    so we never clobber a correctly-configured board with a host default.
    """
    if state.homing_user_override:
        _push_homing_settings()
        return
    try:
        settings = state.conn.get_settings()
        board_mode = (settings.get("Sand/HomingMode") or "").lower()
        if board_mode in ("sensor", "crash"):
            state.homing = 1 if board_mode == "sensor" else 0
        offset = settings.get("Sand/ThetaOffset")
        if offset is not None:
            state.angular_homing_offset_degrees = float(offset)
        logger.info(
            f"Adopted board homing config: mode={board_mode}, "
            f"offset={state.angular_homing_offset_degrees}"
        )
    except Exception as e:
        logger.warning(f"Could not read board homing settings: {e}")


def device_init(homing=True):
    """Read board status, record firmware, reconcile homing, optionally home."""
    try:
        st = state.conn.get_status()
    except Exception as e:
        logger.fatal(f"Board status unreadable: {e}")
        state.conn.close()
        return False

    state.firmware_type = "fluidnc"
    state.firmware_version = st.get("fw") or state.firmware_version or "fluidnc"
    apply_status(st)
    _sync_homing_settings()

    # Reconcile board-owned settings (clock, Still Sands, auto-home cadence) and
    # mirror playlists in the background — mirroring can be slow and must never
    # delay connect/homing.
    from modules.core import board_settings
    threading.Thread(
        target=board_settings.sync_on_connect, args=(state.conn,), daemon=True
    ).start()

    if homing and state.home_on_connect:
        home()

    return True


def connect_device(homing=True):
    """Initialize LEDs, connect to the board over HTTP, and init the device."""
    # Initialize LED interface based on configured provider (unchanged from before).
    if state.led_provider == "wled" and state.wled_ip:
        state.led_controller = LEDInterface(provider="wled", ip_address=state.wled_ip)
    elif state.led_provider == "board":
        if not state.led_controller or not state.led_controller.is_configured:
            state.led_controller = LEDInterface(provider="board")
    else:
        state.led_controller = None

    if state.led_controller:
        state.led_controller.effect_loading()

    url = board_url()
    logger.info(f"Connecting to FluidNC board at {url}")
    state.conn = FluidNCClient(url)
    if not state.conn.reachable():
        logger.error(f"Board not reachable at {url}")
        state.conn = None
    else:
        state.port = url
        logger.info(f"Connected to board at {url}")
        device_init(homing)

    # Show connected effect, then transition to the configured idle effect.
    if state.led_controller:
        logger.info("Showing LED connected effect (green flash)")
        state.led_controller.effect_connected()
        state.led_controller.effect_idle(None)
        _start_idle_led_timeout()


###############################################################################
# Homing
###############################################################################

def home(timeout=120):
    """
    Home the table by delegating to the board's /sand_home (which honors its own
    $Sand/HomingMode — sensor or crash). Polls /sand_status until Idle.
    """
    if not state.conn or not state.conn.is_connected():
        logger.error("Cannot home: no board connection")
        return False

    state.is_homing = True
    state.sensor_homing_failed = False
    try:
        _push_homing_settings()
        logger.info("Sending home command to board...")
        state.conn.home()
        # Give the board a moment to enter the Home state before polling.
        time.sleep(1.0)

        start = time.time()
        while time.time() - start < timeout:
            try:
                st = state.conn.get_status()
            except Exception:
                time.sleep(1.0)
                continue

            machine_state = st.get("state", "")
            if machine_state == "Idle":
                apply_status(st)
                logger.info(
                    f"Homing complete (theta={state.current_theta}, rho={state.current_rho})"
                )
                state.save()
                return True
            if machine_state == "Alarm":
                logger.error("Homing failed: board reports Alarm")
                # In sensor mode an alarm means the switch was not found.
                state.sensor_homing_failed = state.homing == 1
                return False
            time.sleep(1.0)

        logger.warning(f"Homing timed out after {timeout}s")
        return False
    except Exception as e:
        logger.error(f"Error during homing: {e}")
        return False
    finally:
        state.is_homing = False


###############################################################################
# Idle / position / reset
###############################################################################

async def check_idle_async(timeout: float = 30.0):
    """Wait until the board reports Idle (or timeout)."""
    start_time = asyncio.get_event_loop().time()
    while True:
        if asyncio.get_event_loop().time() - start_time > timeout:
            logger.warning(f"Timeout ({timeout}s) waiting for board idle state")
            return False
        st = await asyncio.to_thread(poll_status_once)
        if st and st.get("state") == "Idle":
            return True
        await asyncio.sleep(0.5)


def is_machine_idle() -> bool:
    """Single, immediate check of whether the board is idle."""
    st = poll_status_once()
    return bool(st and st.get("state") == "Idle")


async def update_machine_position():
    """Refresh theta/rho from the board and persist state."""
    if state.conn and state.conn.is_connected():
        try:
            await asyncio.to_thread(poll_status_once)
            await asyncio.to_thread(state.save)
        except Exception as e:
            logger.error(f"Error updating machine position: {e}")


def perform_soft_reset_sync():
    """Reboot the controller via $Bye (loses position; caller re-homes)."""
    if not state.conn or not state.conn.is_connected():
        logger.warning("Cannot perform soft reset: no board connection")
        return False
    try:
        state.conn.soft_reset()
        time.sleep(2.0)  # board reboots; give it a moment
        return True
    except Exception as e:
        logger.error(f"Error performing soft reset: {e}")
        return False


async def perform_soft_reset():
    return await asyncio.to_thread(perform_soft_reset_sync)


def restart_connection(homing=False):
    """Close any existing connection and reconnect to the board."""
    if state.conn:
        try:
            state.conn.close()
        except Exception:
            pass
        state.conn = None
    connect_device(homing)
    return state.conn is not None and state.conn.is_connected()
