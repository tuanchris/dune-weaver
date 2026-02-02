import threading
import time
import logging
import serial
import serial.tools.list_ports
import websocket
import asyncio
import os

from modules.core.state import state
from modules.led.led_interface import LEDInterface
from modules.led.idle_timeout_manager import idle_timeout_manager

logger = logging.getLogger(__name__)

IGNORE_PORTS = ['/dev/cu.debug-console', '/dev/cu.Bluetooth-Incoming-Port', '/dev/ttyS0']

# Ports to deprioritize during auto-connect (shown in UI but not auto-selected)
DEPRIORITIZED_PORTS = ['/dev/ttyS0']


async def _check_table_is_idle() -> bool:
    """Helper function to check if table is idle."""
    return not state.current_playing_file or state.pause_requested


def _start_idle_led_timeout():
    """Start idle LED timeout if enabled."""
    if not state.dw_led_idle_timeout_enabled or state.dw_led_idle_timeout_minutes <= 0:
        return

    logger.debug(f"Starting idle LED timeout: {state.dw_led_idle_timeout_minutes} minutes")
    idle_timeout_manager.start_idle_timeout(
        timeout_minutes=state.dw_led_idle_timeout_minutes,
        state=state,
        check_idle_callback=_check_table_is_idle
    )


###############################################################################
# Connection Abstraction
###############################################################################

class BaseConnection:
    """Abstract base class for a connection."""
    def send(self, data: str) -> None:
        raise NotImplementedError

    def flush(self) -> None:
        raise NotImplementedError

    def readline(self) -> str:
        raise NotImplementedError

    def in_waiting(self) -> int:
        raise NotImplementedError

    def is_connected(self) -> bool:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

###############################################################################
# Serial Connection Implementation
###############################################################################

class SerialConnection(BaseConnection):
    def __init__(self, port: str, baudrate: int = 115200, timeout: int = 2):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.lock = threading.RLock()
        logger.info(f'Connecting to Serial port {port}')
        self.ser = serial.Serial(port, baudrate, timeout=timeout)
        state.port = port
        logger.info(f'Connected to Serial port {port}')

    def send(self, data: str) -> None:
        with self.lock:
            self.ser.write(data.encode())
            self.ser.flush()

    def flush(self) -> None:
        with self.lock:
            self.ser.flush()

    def readline(self) -> str:
        with self.lock:
            return self.ser.readline().decode().strip()

    def in_waiting(self) -> int:
        with self.lock:
            return self.ser.in_waiting

    def reset_input_buffer(self) -> None:
        """Clear any stale data from the serial input buffer."""
        with self.lock:
            if self.ser and self.ser.is_open:
                self.ser.reset_input_buffer()

    def is_connected(self) -> bool:
        return self.ser is not None and self.ser.is_open

    def close(self) -> None:
        # Save current state synchronously first (critical for position persistence)
        try:
            state.save()
        except Exception as e:
            logger.error(f"Error saving state on close: {e}")

        # Schedule async position update if event loop exists, otherwise skip
        # This avoids creating nested event loops which causes RuntimeError
        try:
            asyncio.get_running_loop()
            # We're in async context - schedule as task (fire-and-forget)
            asyncio.create_task(update_machine_position())
            logger.debug("Scheduled async machine position update")
        except RuntimeError:
            # No running event loop - we're in sync context
            # Position was already saved above, skip async update to avoid nested loop
            logger.debug("No event loop running, skipping async position update")

        with self.lock:
            if self.ser.is_open:
                self.ser.close()

###############################################################################
# WebSocket Connection Implementation
###############################################################################

class WebSocketConnection(BaseConnection):
    def __init__(self, url: str, timeout: int = 5):
        self.url = url
        self.timeout = timeout
        self.lock = threading.RLock()
        self.ws = None
        self.connect()

    def connect(self):
        logger.info(f'Connecting to Websocket {self.url}')
        self.ws = websocket.create_connection(self.url, timeout=self.timeout)
        state.port = self.url
        logger.info(f'Connected to Websocket {self.url}')
        
    def send(self, data: str) -> None:
        with self.lock:
            self.ws.send(data)

    def flush(self) -> None:
        # WebSocket sends immediately; nothing to flush.
        pass

    def readline(self) -> str:
        with self.lock:
            data = self.ws.recv()
            # Decode bytes to string if necessary
            if isinstance(data, bytes):
                data = data.decode('utf-8')
            return data.strip()

    def in_waiting(self) -> int:
        return 0  # Not applicable for WebSocket

    def is_connected(self) -> bool:
        return self.ws is not None

    def close(self) -> None:
        # Save current state synchronously first (critical for position persistence)
        try:
            state.save()
        except Exception as e:
            logger.error(f"Error saving state on close: {e}")

        # Schedule async position update if event loop exists, otherwise skip
        # This avoids creating nested event loops which causes RuntimeError
        try:
            asyncio.get_running_loop()
            # We're in async context - schedule as task (fire-and-forget)
            asyncio.create_task(update_machine_position())
            logger.debug("Scheduled async machine position update")
        except RuntimeError:
            # No running event loop - we're in sync context
            # Position was already saved above, skip async update to avoid nested loop
            logger.debug("No event loop running, skipping async position update")

        with self.lock:
            if self.ws:
                self.ws.close()
                self.ws = None

def list_serial_ports():
    """Return a list of available serial ports."""
    ports = serial.tools.list_ports.comports()
    available_ports = [port.device for port in ports if port.device not in IGNORE_PORTS]
    logger.debug(f"Available serial ports: {available_ports}")
    return available_ports

def device_init(homing=True):
    # IMPORTANT: Query machine position BEFORE reset to determine if homing is needed
    # If machine wasn't power cycled, it retains position and we can skip homing
    # Reset ($Bye) zeroes position counters, so we must check BEFORE reset

    try:
        if get_machine_steps():
            logger.info(f"x_steps_per_mm: {state.x_steps_per_mm}, y_steps_per_mm: {state.y_steps_per_mm}, gear_ratio: {state.gear_ratio}")
        else:
            logger.fatal("Failed to get machine steps")
            state.conn.close()
            return False
    except Exception:
        logger.fatal("Not GRBL firmware")
        state.conn.close()
        return False

    # Check machine position BEFORE reset to decide if homing is needed
    machine_x, machine_y = get_machine_position()
    needs_homing = False

    if machine_x != state.machine_x or machine_y != state.machine_y:
        logger.info(f'Machine position mismatch - machine: ({machine_x}, {machine_y}), saved: ({state.machine_x}, {state.machine_y})')
        needs_homing = homing
    else:
        logger.info('Machine position matches saved state, skipping home')
        logger.info(f'Theta: {state.current_theta}, rho: {state.current_rho}')
        logger.info(f'Position: ({machine_x}, {machine_y})')

    # Now perform soft reset to ensure controller is in a clean state
    # This clears any pending commands and resets position counters to 0
    logger.info("Performing soft reset for clean controller state...")
    perform_soft_reset_sync()
    time.sleep(1)  # Extra stabilization after controller restart

    # Reset work coordinate offsets for a clean start
    # This ensures we're using work coordinates (G54) starting from 0
    reset_work_coordinates()

    # Home if position was mismatched (machine may have been power cycled)
    if needs_homing:
        logger.info("Homing required due to position mismatch...")
        success = home()
        if not success:
            logger.error("Homing failed during device initialization")
            # If sensor homing failed, close connection and return False
            # This prevents auto-connection from completing until user takes action
            if state.sensor_homing_failed:
                logger.error("Sensor homing failed - closing connection. User must check sensor or switch to crash homing.")
                state.conn.close()
                state.conn = None
                return False

    time.sleep(2)  # Allow time for the connection to establish
    return True


def connect_device(homing=True):
    # Initialize LED interface based on configured provider
    # Note: DW LEDs are initialized at startup in main.py, so we preserve the existing controller
    if state.led_provider == "wled" and state.wled_ip:
        state.led_controller = LEDInterface(provider="wled", ip_address=state.wled_ip)
    elif state.led_provider == "dw_leds":
        # DW LEDs are already initialized in main.py at startup
        # Only initialize here if not already set up (e.g., reconnection scenario)
        if not state.led_controller or not state.led_controller.is_configured:
            state.led_controller = LEDInterface(
                provider="dw_leds",
                num_leds=state.dw_led_num_leds,
                gpio_pin=state.dw_led_gpio_pin,
                pixel_order=state.dw_led_pixel_order,
                brightness=state.dw_led_brightness / 100.0,
                speed=state.dw_led_speed,
                intensity=state.dw_led_intensity
            )
    elif state.led_provider == "hyperion" and state.hyperion_ip:
        state.led_controller = LEDInterface(
            provider="hyperion",
            ip_address=state.hyperion_ip,
            port=state.hyperion_port
        )
    elif state.led_provider == "none" or not state.led_provider:
        state.led_controller = None
    # For other cases (e.g., wled without IP), preserve existing controller

    # Show loading effect
    if state.led_controller:
        state.led_controller.effect_loading()

    ports = list_serial_ports()

    # Check auto-connect mode: "__auto__" or None = auto, "__none__" = disabled, else specific port
    if state.preferred_port == "__none__":
        logger.info("Auto-connect disabled by user preference")
        # Skip all auto-connect logic, no connection will be established
    # Priority for auto-connect:
    # 1. Preferred port (user's explicit choice) if available
    # 2. Last used port if available
    # 3. First available port as fallback
    elif state.preferred_port and state.preferred_port not in ("__auto__", None) and state.preferred_port in ports:
        logger.info(f"Connecting to preferred port: {state.preferred_port}")
        state.conn = SerialConnection(state.preferred_port)
    elif state.port and state.port in ports:
        logger.info(f"Connecting to last used port: {state.port}")
        state.conn = SerialConnection(state.port)
    elif ports:
        # Prefer non-deprioritized ports (e.g., USB serial over hardware UART)
        preferred_ports = [p for p in ports if p not in DEPRIORITIZED_PORTS]
        fallback_ports = [p for p in ports if p in DEPRIORITIZED_PORTS]

        if preferred_ports:
            logger.info(f"Connecting to first available port: {preferred_ports[0]}")
            state.conn = SerialConnection(preferred_ports[0])
        elif fallback_ports:
            logger.info(f"Connecting to deprioritized port (no better option): {fallback_ports[0]}")
            state.conn = SerialConnection(fallback_ports[0])
    else:
        logger.error("Auto connect failed: No serial ports available")
        # state.conn = WebSocketConnection('ws://fluidnc.local:81')

    if (state.conn.is_connected() if state.conn else False):
        # Check for alarm state and unlock if needed before initializing
        if not check_and_unlock_alarm():
            logger.error("Failed to unlock device from alarm state")
            # Still proceed with device_init but log the issue

        device_init(homing)

    # Show connected effect, then transition to configured idle effect
    if state.led_controller:
        logger.info("Showing LED connected effect (green flash)")
        state.led_controller.effect_connected()
        # Set the configured idle effect after connection
        logger.info(f"Setting LED to idle effect: {state.dw_led_idle_effect}")
        state.led_controller.effect_idle(state.dw_led_idle_effect)
        _start_idle_led_timeout()

def check_and_unlock_alarm():
    """
    Check if GRBL is in alarm state and unlock it with $X if needed.
    Returns True if device is ready (unlocked or no alarm), False on error.

    Note: If sensors are physically triggered (Pn:XY), the alarm may persist
    but we still return True to allow homing to proceed.
    """
    try:
        logger.info("Checking device status for alarm state...")

        # Clear any pending data in buffer first
        while state.conn.in_waiting() > 0:
            state.conn.readline()

        # Send status query
        state.conn.send('?\n')
        time.sleep(0.2)

        # Read response with timeout
        max_attempts = 10
        response = None

        for attempt in range(max_attempts):
            if state.conn.in_waiting() > 0:
                response = state.conn.readline()
                logger.debug(f"Status response: {response}")
                if response and ('<' in response or 'Alarm' in response or 'Idle' in response):
                    break  # Got a valid status response
            time.sleep(0.1)

        if not response:
            logger.warning("No status response received, proceeding anyway")
            return True

        # Check for alarm state
        if "Alarm" in response:
            logger.warning(f"Device in ALARM state: {response}")

            # Send unlock command
            logger.info("Sending $X to unlock...")
            state.conn.send('$X\n')
            time.sleep(1.0)  # Give more time for unlock to process

            # Clear buffer before verification
            while state.conn.in_waiting() > 0:
                discarded = state.conn.readline()
                logger.debug(f"Discarded response: {discarded}")

            # Verify unlock succeeded
            state.conn.send('?\n')
            time.sleep(0.3)

            verify_response = None
            for attempt in range(max_attempts):
                if state.conn.in_waiting() > 0:
                    verify_response = state.conn.readline()
                    logger.debug(f"Verification response: {verify_response}")
                    if verify_response and '<' in verify_response:
                        break
                time.sleep(0.1)

            if verify_response and "Alarm" in verify_response:
                # Check if pins are physically triggered (Pn: in response)
                if "Pn:" in verify_response:
                    logger.warning(f"Alarm persists due to triggered sensors: {verify_response}")
                    logger.warning("Proceeding anyway - homing may clear the sensor state")
                    return True  # Let homing attempt to proceed
                else:
                    logger.error("Failed to unlock device from alarm state")
                    return False
            else:
                logger.info("Device successfully unlocked")
                return True
        else:
            logger.info("Device not in alarm state, proceeding normally")
            return True

    except Exception as e:
        logger.error(f"Error checking/unlocking alarm: {e}")
        return False

def get_status_response() -> str:
    """
    Send a status query ('?') and return the response if available.
    Accepts both MPos (machine position) and WPos (work position) formats
    depending on GRBL's $10 setting.
    """
    if state.conn is None or not state.conn.is_connected():
        logger.warning("Cannot get status response: no active connection")
        return False

    while True:
        try:
            state.conn.send('?')
            response = state.conn.readline()
            # Accept either MPos or WPos format (depends on GRBL $10 setting)
            if "MPos" in response or "WPos" in response:
                logger.debug(f"Status response: {response}")
                return response
        except Exception as e:
            logger.error(f"Error getting status response: {e}")
            return False
        time.sleep(1)
        
def parse_machine_position(response: str):
    """
    Parse the position from a status response.
    Supports both MPos (machine position) and WPos (work position) formats
    depending on GRBL's $10 setting.
    Expected formats:
        "<...|MPos:-994.869,-321.861,0.000|...>"
        "<...|WPos:0.000,19.000,0.000|...>"
    Returns a tuple (x, y) if found, else None.
    """
    if "MPos:" not in response and "WPos:" not in response:
        return None
    try:
        # Try MPos first, then WPos
        pos_section = next((part for part in response.split("|") if part.startswith("MPos:")), None)
        if pos_section is None:
            pos_section = next((part for part in response.split("|") if part.startswith("WPos:")), None)

        if pos_section:
            pos_str = pos_section.split(":", 1)[1]
            pos_values = pos_str.split(",")
            pos_x = float(pos_values[0])
            pos_y = float(pos_values[1])
            return pos_x, pos_y
    except Exception as e:
        logger.error(f"Error parsing position: {e}")
    return None


async def send_grbl_coordinates(x, y, speed=600, timeout=30, home=False):
    """
    Send a G-code command to FluidNC and wait for an 'ok' response.
    If no response after set timeout, returns False.

    Args:
        x: X coordinate
        y: Y coordinate
        speed: Feed rate in mm/min
        timeout: Maximum time in seconds to wait for 'ok' response
        home: If True, sends jog command ($J=) instead of G1

    Returns:
        True on success, False on timeout or error
    """
    logger.debug(f"Sending G-code: X{x} Y{y} at F{speed}")

    overall_start_time = time.time()
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        # Check overall timeout
        if time.time() - overall_start_time > timeout:
            logger.error(f"Timeout waiting for 'ok' response after {timeout}s")
            return False

        try:
            gcode = f"$J=G91 G21 Y{y:.2f} F{speed}" if home else f"G1 X{x:.2f} Y{y:.2f} F{speed}"
            await asyncio.to_thread(state.conn.send, gcode + "\n")
            logger.debug(f"Sent command: {gcode}")

            # Wait for 'ok' response with timeout
            response_start = time.time()
            response_timeout = min(10, timeout - (time.time() - overall_start_time))

            while time.time() - response_start < response_timeout:
                # Check overall timeout
                if time.time() - overall_start_time > timeout:
                    logger.error("Overall timeout waiting for 'ok' response")
                    return False

                response = await asyncio.to_thread(state.conn.readline)
                if response:
                    logger.debug(f"Response: {response}")
                    if response.lower().strip() == "ok":
                        logger.debug("Command execution confirmed.")
                        return True
                    elif 'error' in response.lower():
                        logger.warning(f"Got error response: {response}")
                        # Don't immediately fail - some errors are recoverable
                else:
                    await asyncio.sleep(0.05)

            # Response timeout for this attempt
            logger.warning(f"No 'ok' received for {gcode}, retrying... ({retry_count + 1}/{max_retries})")
            retry_count += 1
            await asyncio.sleep(0.2)

        except Exception as e:
            error_str = str(e)
            logger.warning(f"Error sending command: {error_str}")

            # Immediately return for device not configured errors
            if "Device not configured" in error_str or "Errno 6" in error_str:
                logger.error(f"Device configuration error detected: {error_str}")
                state.stop_requested = True
                state.conn = None
                state.is_connected = False
                logger.info("Connection marked as disconnected due to device error")
                return False

            retry_count += 1
            await asyncio.sleep(0.2)

    logger.error(f"Failed to receive 'ok' response after {max_retries} retries")
    return False


def _detect_firmware():
    """
    Detect firmware type (FluidNC or GRBL) by sending $I command.
    Returns tuple: (firmware_type: str, version: str or None)
    firmware_type is 'fluidnc', 'grbl', or 'unknown'
    """
    if not state.conn or not state.conn.is_connected():
        return ('unknown', None)

    # Clear buffer first
    try:
        while state.conn.in_waiting() > 0:
            state.conn.readline()
    except Exception:
        pass

    try:
        state.conn.send("$I\n")
        time.sleep(0.3)

        firmware_type = 'unknown'
        version = None
        start_time = time.time()

        while time.time() - start_time < 2.0:
            if state.conn.in_waiting() > 0:
                response = state.conn.readline()
                if response:
                    logger.debug(f"Firmware detection response: {response}")
                    response_lower = response.lower()

                    if 'fluidnc' in response_lower:
                        firmware_type = 'fluidnc'
                        # Try to extract version from response like "FluidNC v3.7.2"
                        if 'v' in response_lower:
                            parts = response.split()
                            for part in parts:
                                if part.lower().startswith('v') and any(c.isdigit() for c in part):
                                    version = part
                                    break
                        break
                    elif 'grbl' in response_lower and 'fluidnc' not in response_lower:
                        firmware_type = 'grbl'
                        # Try to extract version like "Grbl 1.1h"
                        parts = response.split()
                        for i, part in enumerate(parts):
                            if 'grbl' in part.lower() and i + 1 < len(parts):
                                version = parts[i + 1]
                                break
                        break
                    elif response.lower().strip() == 'ok':
                        break
            else:
                time.sleep(0.05)

        # Clear any remaining responses
        while state.conn.in_waiting() > 0:
            state.conn.readline()

        return (firmware_type, version)

    except Exception as e:
        logger.warning(f"Firmware detection failed: {e}")
        return ('unknown', None)


def _get_steps_fluidnc():
    """
    Get steps/mm from FluidNC using individual setting queries.
    Returns tuple: (x_steps_per_mm, y_steps_per_mm) or (None, None) on failure.

    Note: Works even when device is in ALARM state (e.g., limit switch active).
    """
    x_steps = None
    y_steps = None

    # Clear buffer
    try:
        while state.conn.in_waiting() > 0:
            state.conn.readline()
    except Exception:
        pass

    # Query X steps/mm
    try:
        state.conn.send("$/axes/x/steps_per_mm\n")
        time.sleep(0.2)

        start_time = time.time()
        while time.time() - start_time < 2.0:
            if state.conn.in_waiting() > 0:
                response = state.conn.readline()
                if response:
                    logger.debug(f"FluidNC X steps response: {response}")
                    # Response format: "/axes/x/steps_per_mm=200.000" or similar
                    if 'steps_per_mm=' in response:
                        try:
                            x_steps = float(response.split('=')[1].strip())
                            state.x_steps_per_mm = x_steps
                            logger.info(f"X steps per mm (FluidNC): {x_steps}")
                        except (ValueError, IndexError) as e:
                            logger.warning(f"Failed to parse X steps: {e}")
                        break
                    elif response.lower().strip() == 'ok':
                        break
                    elif 'error' in response.lower() or 'alarm' in response.lower():
                        # Device may be in alarm state (e.g., limit switch active)
                        # Log and continue - settings queries often work anyway
                        logger.debug(f"Got error/alarm response, continuing: {response}")
            else:
                time.sleep(0.05)
    except Exception as e:
        logger.error(f"Error querying FluidNC X steps: {e}")

    # Clear buffer before next query
    try:
        while state.conn.in_waiting() > 0:
            state.conn.readline()
    except Exception:
        pass

    # Query Y steps/mm
    try:
        state.conn.send("$/axes/y/steps_per_mm\n")
        time.sleep(0.2)

        start_time = time.time()
        while time.time() - start_time < 2.0:
            if state.conn.in_waiting() > 0:
                response = state.conn.readline()
                if response:
                    logger.debug(f"FluidNC Y steps response: {response}")
                    if 'steps_per_mm=' in response:
                        try:
                            y_steps = float(response.split('=')[1].strip())
                            state.y_steps_per_mm = y_steps
                            logger.info(f"Y steps per mm (FluidNC): {y_steps}")
                        except (ValueError, IndexError) as e:
                            logger.warning(f"Failed to parse Y steps: {e}")
                        break
                    elif response.lower().strip() == 'ok':
                        break
                    elif 'error' in response.lower() or 'alarm' in response.lower():
                        logger.debug(f"Got error/alarm response, continuing: {response}")
            else:
                time.sleep(0.05)
    except Exception as e:
        logger.error(f"Error querying FluidNC Y steps: {e}")

    # Clear buffer before homing query
    try:
        while state.conn.in_waiting() > 0:
            state.conn.readline()
    except Exception:
        pass

    # Query homing cycle setting (informational - user preference takes precedence)
    try:
        state.conn.send("$/axes/y/homing/cycle\n")
        time.sleep(0.2)

        start_time = time.time()
        while time.time() - start_time < 1.5:
            if state.conn.in_waiting() > 0:
                response = state.conn.readline()
                if response:
                    logger.debug(f"FluidNC homing response: {response}")
                    if 'homing/cycle=' in response:
                        try:
                            homing_cycle = int(float(response.split('=')[1].strip()))
                            # cycle >= 1 means homing is enabled in firmware
                            logger.info(f"Firmware homing setting (cycle): {homing_cycle}, using user preference: {state.homing}")
                        except (ValueError, IndexError):
                            pass
                        break
                    elif response.lower().strip() == 'ok':
                        break
            else:
                time.sleep(0.05)
    except Exception as e:
        logger.debug(f"Could not query FluidNC homing setting: {e}")

    # Clear buffer
    try:
        while state.conn.in_waiting() > 0:
            state.conn.readline()
    except Exception:
        pass

    return (x_steps, y_steps)


def _get_steps_grbl():
    """
    Get steps/mm from GRBL using $$ command.
    Returns tuple: (x_steps_per_mm, y_steps_per_mm) or (None, None) on failure.

    Note: Works even when device is in ALARM state (e.g., limit switch active).
    $$ command typically responds with settings even during alarm.
    """
    x_steps_per_mm = None
    y_steps_per_mm = None

    max_retries = 3
    attempt_timeout = 4

    for attempt in range(max_retries):
        logger.info(f"Requesting GRBL settings with $$ command (attempt {attempt + 1}/{max_retries})")

        try:
            state.conn.send("$$\n")
        except Exception as e:
            logger.error(f"Error sending $$ command: {e}")
            continue

        attempt_start = time.time()
        got_ok = False

        while time.time() - attempt_start < attempt_timeout:
            try:
                response = state.conn.readline()

                if not response:
                    continue

                logger.debug(f"Raw response: {response}")

                for line in response.splitlines():
                    line = line.strip()
                    if not line:
                        continue

                    logger.debug(f"Config response: {line}")

                    if line.startswith("$100="):
                        x_steps_per_mm = float(line.split("=")[1])
                        state.x_steps_per_mm = x_steps_per_mm
                        logger.info(f"X steps per mm: {x_steps_per_mm}")
                    elif line.startswith("$101="):
                        y_steps_per_mm = float(line.split("=")[1])
                        state.y_steps_per_mm = y_steps_per_mm
                        logger.info(f"Y steps per mm: {y_steps_per_mm}")
                    elif line.startswith("$22="):
                        firmware_homing = int(line.split('=')[1])
                        logger.info(f"Firmware homing setting ($22): {firmware_homing}, using user preference: {state.homing}")
                    elif line.lower() == 'ok':
                        got_ok = True
                        logger.debug("Received 'ok' confirmation from GRBL")
                    elif line.lower().startswith('error') or 'alarm' in line.lower():
                        # Device may be in alarm state (e.g., limit switch active)
                        # Log and continue - $$ typically works anyway
                        logger.debug(f"Got error/alarm during settings query (proceeding): {line}")

                if got_ok:
                    if x_steps_per_mm is not None and y_steps_per_mm is not None:
                        logger.info("Successfully received all GRBL settings")
                        break
                    else:
                        logger.warning("Received 'ok' but missing some settings")
                        break

            except Exception as e:
                logger.error(f"Error reading GRBL response: {e}")
                break

        if x_steps_per_mm is not None and y_steps_per_mm is not None:
            break

        if attempt < max_retries - 1:
            logger.warning(f"Attempt {attempt + 1} did not get all settings, retrying...")
            time.sleep(0.5)
            try:
                while state.conn.in_waiting() > 0:
                    state.conn.readline()
            except Exception:
                pass

    return (x_steps_per_mm, y_steps_per_mm)


def get_machine_steps(timeout=10):
    """
    Get machine steps/mm from the controller (FluidNC or GRBL).
    Returns True if successful, False otherwise.

    Detects firmware type first:
    - FluidNC: Uses targeted $/axes/x/steps_per_mm queries (more reliable)
    - GRBL: Falls back to $$ command with retries
    """
    if not state.conn or not state.conn.is_connected():
        logger.error("Cannot get machine steps: No connection available")
        return False

    # Clear any pending data in the buffer
    try:
        while state.conn.in_waiting() > 0:
            state.conn.readline()
    except Exception as e:
        logger.warning(f"Error clearing buffer: {e}")

    # Verify controller is responsive before querying
    try:
        state.conn.send("?\n")
        time.sleep(0.2)
        ready_check_attempts = 5
        controller_ready = False
        for _ in range(ready_check_attempts):
            if state.conn.in_waiting() > 0:
                response = state.conn.readline()
                if response and ('<' in response or 'Idle' in response or 'Alarm' in response):
                    controller_ready = True
                    if 'Alarm' in response:
                        logger.info(f"Controller in ALARM state (likely limit switch active), proceeding with settings query: {response.strip()}")
                    else:
                        logger.debug(f"Controller ready, status: {response}")
                    break
            time.sleep(0.1)

        if not controller_ready:
            logger.warning("Controller not responding to status query, proceeding anyway...")

        # Clear buffer after readiness check
        while state.conn.in_waiting() > 0:
            state.conn.readline()
        time.sleep(0.1)
    except Exception as e:
        logger.warning(f"Readiness check failed: {e}, proceeding anyway...")

    # Detect firmware type
    firmware_type, firmware_version = _detect_firmware()

    if firmware_type == 'fluidnc':
        if firmware_version:
            logger.info(f"Detected FluidNC firmware, version: {firmware_version}")
        else:
            logger.info("Detected FluidNC firmware (version unknown)")
        x_steps_per_mm, y_steps_per_mm = _get_steps_fluidnc()

        # Fallback to GRBL method if FluidNC queries failed
        if x_steps_per_mm is None or y_steps_per_mm is None:
            logger.warning("FluidNC setting queries failed, falling back to $$ command...")
            x_steps_per_mm, y_steps_per_mm = _get_steps_grbl()
    else:
        if firmware_type == 'grbl':
            if firmware_version:
                logger.info(f"Detected GRBL firmware, version: {firmware_version}")
            else:
                logger.info("Detected GRBL firmware (version unknown)")
        else:
            logger.info("Could not detect firmware type, using GRBL commands")
        x_steps_per_mm, y_steps_per_mm = _get_steps_grbl()
    
    # Process results and determine table type
    settings_complete = (x_steps_per_mm is not None and y_steps_per_mm is not None)
    if settings_complete:
        if y_steps_per_mm == 180 and x_steps_per_mm == 256:
            state.table_type = 'dune_weaver_mini'
        elif y_steps_per_mm == 210 and x_steps_per_mm == 256:
            state.table_type = 'dune_weaver_mini_pro_byj'
        elif (y_steps_per_mm == 270 or y_steps_per_mm == 250) and x_steps_per_mm == 200:
            state.table_type = 'dune_weaver_gold'
        elif y_steps_per_mm == 287:
            state.table_type = 'dune_weaver'
        elif y_steps_per_mm == 164:
            state.table_type = 'dune_weaver_mini_pro'
        elif y_steps_per_mm >= 320:
            state.table_type = 'dune_weaver_pro'
        else:
            state.table_type = None
            logger.warning(f"Unknown table type with Y steps/mm: {y_steps_per_mm}")

        # Use override if set, otherwise use detected table type
        effective_table_type = state.table_type_override or state.table_type

        # Set gear ratio based on effective table type (hardcoded)
        if effective_table_type in ['dune_weaver_mini', 'dune_weaver_mini_pro', 'dune_weaver_mini_pro_byj', 'dune_weaver_gold']:
            state.gear_ratio = 6.25
        else:
            state.gear_ratio = 10

        # Check for environment variable override
        gear_ratio_override = os.getenv('GEAR_RATIO')
        if gear_ratio_override is not None:
            try:
                state.gear_ratio = float(gear_ratio_override)
                logger.info(f"Machine type detected: {state.table_type}, effective: {effective_table_type}, gear ratio: {state.gear_ratio} (from GEAR_RATIO env var)")
            except ValueError:
                logger.error(f"Invalid GEAR_RATIO env var value: {gear_ratio_override}, using default: {state.gear_ratio}")
                logger.info(f"Machine type detected: {state.table_type}, effective: {effective_table_type}, gear ratio: {state.gear_ratio} (hardcoded)")
        elif state.table_type_override:
            logger.info(f"Machine type detected: {state.table_type}, overridden to: {effective_table_type}, gear ratio: {state.gear_ratio}")
        else:
            logger.info(f"Machine type detected: {state.table_type}, gear ratio: {state.gear_ratio} (hardcoded)")

        return True
    else:
        missing = []
        if x_steps_per_mm is None:
            missing.append("X steps/mm")
        if y_steps_per_mm is None:
            missing.append("Y steps/mm")
        logger.error(f"Failed to get all machine parameters after {timeout}s. Missing: {', '.join(missing)}")
        return False

def home(timeout=120):
    """
    Perform homing sequence based on configured mode:

    Mode 0 (Crash):
        - Y axis moves -22mm (or -30mm for mini) until physical stop
        - Set theta=0, rho=0 (no x0 y0 command)

    Mode 1 (Sensor):
        - Send $H command to home both X and Y axes
        - Wait for [MSG:Homed:X] and [MSG:Homed:Y] messages
        - Send x0 y0 to zero positions
        - Set theta to compass offset, rho=0

    Args:
        timeout: Maximum time in seconds to wait for homing to complete (default: 120)
                 Increased from 90s to allow buffer after soft reset recovery
    """
    import threading
    import math

    # Check for alarm state before homing and unlock if needed
    if not check_and_unlock_alarm():
        logger.error("Failed to unlock device from alarm state, cannot proceed with homing")
        return False

    # Flag to track if homing completed
    homing_complete = threading.Event()
    homing_success = False

    def home_internal():
        nonlocal homing_success
        effective_table_type = state.table_type_override or state.table_type
        homing_speed = 400
        if effective_table_type == 'dune_weaver_mini':
            homing_speed = 100
        try:
            if state.homing == 1:
                # Mode 1: Sensor-based homing using $H
                logger.info("Using sensor-based homing mode ($H)")

                # Clear any pending responses
                state.homed_x = False
                state.homed_y = False

                # Clear any stale data from previous operations
                try:
                    while state.conn.in_waiting() > 0:
                        stale = state.conn.readline()
                        logger.debug(f"Cleared stale data before homing: {stale}")
                except Exception:
                    pass

                # Send $H command
                state.conn.send("$H\n")
                logger.info("Sent $H command, waiting for homing messages...")

                # Wait for [MSG:Homed:X] and [MSG:Homed:Y] messages
                max_wait_time = 60  # 60 seconds - boot recovery needs more time
                start_time = time.time()

                while (time.time() - start_time) < max_wait_time:
                    try:
                        response = state.conn.readline()
                        if response:
                            logger.debug(f"Homing response: {response}")

                            # Check for homing messages
                            if "[MSG:Homed:X]" in response:
                                state.homed_x = True
                                logger.info("Received [MSG:Homed:X]")
                            if "[MSG:Homed:Y]" in response:
                                state.homed_y = True
                                logger.info("Received [MSG:Homed:Y]")

                            # Break if we've received both messages
                            if state.homed_x and state.homed_y:
                                logger.info("Received both homing confirmation messages")
                                break
                    except Exception as e:
                        logger.error(f"Error reading homing response: {e}")

                    time.sleep(0.1)

                if not (state.homed_x and state.homed_y):
                    logger.warning(f"Did not receive all homing messages (X:{state.homed_x}, Y:{state.homed_y}), unlocking and continuing...")
                    # Unlock machine to clear any alarm state
                    state.conn.send("$X\n")
                    time.sleep(0.5)

                # Wait for idle state after $H
                logger.info("Waiting for device to reach idle state after $H...")
                idle_reached = check_idle()

                if not idle_reached:
                    logger.error("Device did not reach idle state after $H command")
                    homing_complete.set()
                    return

                # If X homed but Y failed, fallback to crash homing for Y
                if state.homed_x and not state.homed_y:
                    logger.warning("Sensor homing incomplete (Y failed) - falling back to crash homing")

                    # Perform crash homing as fallback
                    logger.info(f"Executing crash homing fallback at {homing_speed} mm/min")

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        if effective_table_type == 'dune_weaver_mini':
                            result = loop.run_until_complete(send_grbl_coordinates(0, -30, homing_speed, home=True))
                            if not result:
                                logger.error("Crash homing fallback failed")
                                homing_complete.set()
                                return
                        else:
                            result = loop.run_until_complete(send_grbl_coordinates(0, -22, homing_speed, home=True))
                            if not result:
                                logger.error("Crash homing fallback failed")
                                homing_complete.set()
                                return
                    finally:
                        loop.close()

                    # Wait for idle after crash homing
                    logger.info("Waiting for device to reach idle state after crash homing fallback...")
                    idle_reached = check_idle()
                    if not idle_reached:
                        logger.error("Device did not reach idle state after crash homing fallback")
                        homing_complete.set()
                        return

                    # Set position like crash homing does
                    state.current_theta = 0
                    state.current_rho = 0
                    logger.info("Crash homing fallback completed - theta=0, rho=0")

                elif not state.homed_x and not state.homed_y:
                    # Neither axis homed - this is a failure, don't proceed
                    # Set sensor_homing_failed flag to notify UI for user action
                    logger.error("Sensor homing failed - neither axis homed. User action required.")
                    state.sensor_homing_failed = True
                    homing_complete.set()
                    return
                else:
                    # Send x0 y0 to zero both positions using send_grbl_coordinates
                    logger.info(f"Zeroing positions with x0 y0 f{homing_speed}")

                    # Run async function in new event loop
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        # Send G1 X0 Y0 F{homing_speed}
                        result = loop.run_until_complete(send_grbl_coordinates(0, 0, homing_speed))
                        if not result:
                            logger.error("Position zeroing failed - send_grbl_coordinates returned False")
                            homing_complete.set()
                            return
                        logger.info("Position zeroing completed successfully")
                    finally:
                        loop.close()

                    # Wait for device to reach idle state after zeroing movement
                    logger.info("Waiting for device to reach idle state after zeroing...")
                    idle_reached = check_idle()

                    if not idle_reached:
                        logger.error("Device did not reach idle state after zeroing")
                        homing_complete.set()
                        return

                # Set current position based on compass reference point (sensor mode only)
                offset_radians = math.radians(state.angular_homing_offset_degrees)
                state.current_theta = offset_radians
                state.current_rho = 0

                logger.info(f"Sensor homing completed - theta set to {state.angular_homing_offset_degrees}° ({offset_radians:.3f} rad), rho=0")

            else:
                logger.info(f"Using crash homing mode at {homing_speed} mm/min")

                # Run async function in new event loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    if effective_table_type == 'dune_weaver_mini':
                        result = loop.run_until_complete(send_grbl_coordinates(0, -30, homing_speed, home=True))
                        if not result:
                            logger.error("Crash homing failed - send_grbl_coordinates returned False")
                            homing_complete.set()
                            return
                        state.machine_y -= 30
                    else:
                        result = loop.run_until_complete(send_grbl_coordinates(0, -22, homing_speed, home=True))
                        if not result:
                            logger.error("Crash homing failed - send_grbl_coordinates returned False")
                            homing_complete.set()
                            return
                        state.machine_y -= 22
                finally:
                    loop.close()

                # Wait for device to reach idle state after crash homing
                logger.info("Waiting for device to reach idle state after crash homing...")
                idle_reached = check_idle()

                if not idle_reached:
                    logger.error("Device did not reach idle state after crash homing")
                    homing_complete.set()
                    return

                # Crash homing just sets theta and rho to 0 (no x0 y0 command)
                state.current_theta = 0
                state.current_rho = 0

                logger.info("Crash homing completed - theta=0, rho=0")

            # Update machine position from hardware after homing
            logger.info("Updating machine position after homing...")
            try:
                pos = get_machine_position()
                if pos and pos[0] is not None and pos[1] is not None:
                    state.machine_x, state.machine_y = pos
                    state.save()
                    logger.info(f"Machine position updated after homing: X={state.machine_x}, Y={state.machine_y}")
                else:
                    logger.warning("Could not get machine position after homing")
            except Exception as e:
                logger.error(f"Error updating machine position after homing: {e}")

            homing_success = True
            # Clear sensor_homing_failed flag on successful homing
            state.sensor_homing_failed = False
            homing_complete.set()

        except Exception as e:
            logger.error(f"Error during homing: {e}")
            homing_complete.set()

    # Start homing in a separate thread
    homing_thread = threading.Thread(target=home_internal)
    homing_thread.daemon = True
    homing_thread.start()

    # Wait for homing to complete or timeout
    if not homing_complete.wait(timeout):
        logger.error(f"Homing timeout after {timeout} seconds")
        # Try to stop any ongoing movement
        try:
            if state.conn and state.conn.is_connected():
                state.conn.send("!\n")  # Send feed hold
                time.sleep(0.1)
                state.conn.send("\x18\n")  # Send reset
        except Exception as e:
            logger.error(f"Error stopping movement after timeout: {e}")
        return False

    if not homing_success:
        logger.error("Homing failed")
        return False

    logger.info("Homing completed successfully")
    return True

def check_idle():
    """
    Continuously check if the device is idle (synchronous version).
    """
    logger.info("Checking idle")
    while True:
        response = get_status_response()
        if response and "Idle" in response:
            logger.info("Device is idle")
            # Schedule async update_machine_position in the existing event loop
            try:
                # Try to schedule in existing event loop if available
                try:
                    asyncio.get_running_loop()
                    # Create a task but don't await it (fire and forget)
                    asyncio.create_task(update_machine_position())
                    logger.debug("Scheduled machine position update task")
                except RuntimeError:
                    # No event loop running, skip machine position update
                    logger.debug("No event loop running, skipping machine position update")
            except Exception as e:
                logger.error(f"Error scheduling machine position update: {e}")
            return True
        time.sleep(1)

async def check_idle_async(timeout: float = 30.0):
    """
    Continuously check if the device is idle (async version).

    Args:
        timeout: Maximum seconds to wait for idle state (default 30s)

    Returns:
        True if device became idle, False if timeout or stop requested
    """
    logger.info("Checking idle (async)")
    start_time = asyncio.get_event_loop().time()

    while True:
        # Check if stop was requested - exit early
        if state.stop_requested:
            logger.info("Stop requested during idle check, exiting early")
            return False

        # Check timeout
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > timeout:
            logger.warning(f"Timeout ({timeout}s) waiting for device idle state")
            return False

        response = await asyncio.to_thread(get_status_response)
        if response and "Idle" in response:
            logger.info("Device is idle")
            try:
                await update_machine_position()
            except Exception as e:
                logger.error(f"Error updating machine position: {e}")
            return True
        await asyncio.sleep(1)

def is_machine_idle() -> bool:
    """
    Single check to see if the machine is currently idle.
    Does not loop - returns immediately with current status.

    Returns:
        True if machine is idle, False otherwise
    """
    if not state.conn or not state.conn.is_connected():
        logger.debug("No connection - machine not idle")
        return False

    try:
        state.conn.send('?')
        response = state.conn.readline()

        if response and "Idle" in response:
            logger.debug("Machine status: Idle")
            return True
        else:
            logger.debug(f"Machine status: {response}")
            return False
    except Exception as e:
        logger.error(f"Error checking machine idle status: {e}")
        return False


def get_machine_position(timeout=5):
    """
    Query the device for its position.
    Supports both MPos and WPos formats (depends on GRBL $10 setting).
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            state.conn.send('?')
            response = state.conn.readline()
            logger.debug(f"Raw status response: {response}")
            # Accept either MPos or WPos format
            if "MPos" in response or "WPos" in response:
                pos = parse_machine_position(response)
                if pos:
                    machine_x, machine_y = pos
                    logger.debug(f"Machine position: X={machine_x}, Y={machine_y}")
                    return machine_x, machine_y
        except Exception as e:
            logger.error(f"Error getting machine position: {e}")
            return
        time.sleep(0.1)
    logger.warning("Timeout reached waiting for machine position")
    return None, None

async def update_machine_position():
    if (state.conn.is_connected() if state.conn else False):
        try:
            logger.info('Saving machine position')
            state.machine_x, state.machine_y = await asyncio.to_thread(get_machine_position)
            await asyncio.to_thread(state.save)
            logger.info(f'Machine position saved: {state.machine_x}, {state.machine_y}')
        except Exception as e:
            logger.error(f"Error updating machine position: {e}")


def perform_soft_reset_sync(max_retries: int = 5):
    """
    Synchronous version of soft reset for use during device initialization.

    Supports both FluidNC ($Bye) and GRBL (Ctrl+X / 0x18) firmware.
    Triggers a software reset which clears position counters to 0.
    This is more reliable than G92 which only sets a work coordinate offset
    without changing the actual machine position (MPos).

    IMPORTANT: Position is only reset to (0,0) if confirmation is received.
    This prevents position drift from accumulating over long operation periods.

    Uses exponential backoff for retries:
    - Attempt 1: 5s timeout
    - Attempt 2: 7.5s timeout, 1s delay before retry
    - Attempt 3: 11s timeout, 2s delay before retry
    - Attempt 4: 17s timeout, 4s delay before retry
    - Attempt 5: 25s timeout, 8s delay before retry

    Args:
        max_retries: Maximum number of reset attempts (default 5)

    Returns:
        True if reset confirmed, False if all attempts failed
    """
    if not state.conn or not state.conn.is_connected():
        logger.warning("Cannot perform soft reset: no active connection")
        return False

    try:
        # Detect firmware type to use appropriate reset command
        firmware_type, version = _detect_firmware()
        logger.info(f"Detected firmware: {firmware_type} {version or ''}")
        logger.info(f"Performing soft reset (was: X={state.machine_x:.2f}, Y={state.machine_y:.2f})")

        for attempt in range(max_retries):
            # Exponential backoff: 5s * 1.5^attempt → 5s, 7.5s, 11s, 17s, 25s
            timeout = 5.0 * (1.5 ** attempt)
            logger.info(f"Reset attempt {attempt + 1}/{max_retries} (timeout: {timeout:.1f}s)")

            # Clear any pending data first
            if isinstance(state.conn, SerialConnection) and state.conn.ser:
                state.conn.ser.reset_input_buffer()

            # Send appropriate reset command based on firmware
            if firmware_type == 'fluidnc':
                # FluidNC uses $Bye for soft reset
                if isinstance(state.conn, SerialConnection) and state.conn.ser:
                    state.conn.ser.write(b'$Bye\n')
                    state.conn.ser.flush()
                    logger.info(f"$Bye sent directly via serial to {state.port}")
                else:
                    state.conn.send('$Bye\n')
                    logger.info("$Bye sent via connection abstraction")
            else:
                # GRBL uses Ctrl+X (0x18) for soft reset
                if isinstance(state.conn, SerialConnection) and state.conn.ser:
                    state.conn.ser.write(b'\x18')
                    state.conn.ser.flush()
                    logger.info(f"Ctrl+X (0x18) sent directly via serial to {state.port}")
                else:
                    state.conn.send('\x18')
                    logger.info("Ctrl+X (0x18) sent via connection abstraction")

            # Wait for controller to fully restart
            # FluidNC sequence: [MSG:INFO: Restarting] -> ... -> "Grbl 3.9 [FluidNC...]"
            # GRBL sequence: "Grbl 1.1h ['$' for help]"
            start_time = time.time()
            reset_confirmed = False
            while time.time() - start_time < timeout:
                try:
                    response = state.conn.readline()
                    if response:
                        logger.debug(f"Reset response: {response}")
                        # Wait for the "Grbl" startup banner - this means fully ready
                        if response.startswith("Grbl") or "fluidnc" in response.lower():
                            reset_confirmed = True
                            logger.info(f"Controller restart complete: {response}")
                            break
                except Exception:
                    pass
                time.sleep(0.05)

            if reset_confirmed:
                # Small delay to let controller fully stabilize
                time.sleep(0.2)

                # Unlock controller in case it's in alarm state after reset
                logger.info("Sending $X to unlock controller after reset")
                state.conn.send("$X\n")
                # Wait for ok response
                unlock_start = time.time()
                while time.time() - unlock_start < 1.0:
                    try:
                        response = state.conn.readline()
                        if response:
                            logger.debug(f"$X response: {response}")
                            if response.lower() == "ok":
                                logger.info("Controller unlocked")
                                break
                    except Exception:
                        pass
                    time.sleep(0.05)

                # Only reset state positions when confirmation received
                state.machine_x = 0.0
                state.machine_y = 0.0
                reset_cmd = '$Bye' if firmware_type == 'fluidnc' else 'Ctrl+X'
                logger.info(f"Machine position reset to 0 via {reset_cmd} soft reset")

                # Save the reset position
                state.save()
                logger.info(f"Machine position saved: {state.machine_x}, {state.machine_y}")
                return True

            # Retry after failed attempt with exponential backoff delay
            if attempt < max_retries - 1:
                backoff_delay = 1.0 * (2 ** attempt)  # 1s, 2s, 4s, 8s
                logger.warning(f"Reset attempt {attempt + 1}/{max_retries} failed, retrying in {backoff_delay:.0f}s...")
                time.sleep(backoff_delay)

        # All attempts failed - DO NOT reset position to prevent drift
        logger.error(
            f"All {max_retries} reset attempts failed - no confirmation received. "
            f"Position NOT reset (still: X={state.machine_x:.2f}, Y={state.machine_y:.2f}). "
            "This may indicate communication issues or controller not responding."
        )
        return False

    except Exception as e:
        logger.error(f"Error performing soft reset: {e}")
        return False


async def perform_soft_reset():
    """
    Async version of soft reset for use in async contexts (API endpoints, pattern manager).
    Wraps the sync version in a thread to avoid blocking the event loop.
    """
    return await asyncio.to_thread(perform_soft_reset_sync)


def reset_work_coordinates():
    """
    Clear all work coordinate offsets for a clean start.

    This ensures the work coordinate system starts fresh on each connection,
    preventing accumulated offsets from previous sessions from affecting
    pattern execution.

    G92.1: Clears any G92 offset (resets work coordinates to machine coordinates)
    G10 L2 P1 X0 Y0: Sets G54 work offset to 0 (for completeness)
    """
    if not state.conn or not state.conn.is_connected():
        logger.warning("Cannot reset work coordinates: no active connection")
        return False

    try:
        logger.info("Resetting work coordinate offsets")

        # Clear any stale input data first
        try:
            while state.conn.in_waiting() > 0:
                state.conn.readline()
        except Exception:
            pass

        # Clear G92 offset
        state.conn.send("G92.1\n")
        time.sleep(0.2)

        # Wait for 'ok' response
        start_time = time.time()
        got_ok = False
        while time.time() - start_time < 2.0:
            if state.conn.in_waiting() > 0:
                response = state.conn.readline()
                if response:
                    logger.debug(f"G92.1 response: {response}")
                    if response.lower() == "ok":
                        got_ok = True
                        break
                    elif "error" in response.lower():
                        logger.warning(f"G92.1 error: {response}")
                        break
            time.sleep(0.05)

        if not got_ok:
            logger.warning("Did not receive 'ok' for G92.1, continuing anyway")

        # Set G54 offset to 0 (optional, for completeness)
        state.conn.send("G10 L2 P1 X0 Y0\n")
        time.sleep(0.2)

        # Wait for 'ok' response
        start_time = time.time()
        got_ok = False
        while time.time() - start_time < 2.0:
            if state.conn.in_waiting() > 0:
                response = state.conn.readline()
                if response:
                    logger.debug(f"G10 response: {response}")
                    if response.lower() == "ok":
                        got_ok = True
                        break
                    elif "error" in response.lower():
                        logger.warning(f"G10 error: {response}")
                        break
            time.sleep(0.05)

        if not got_ok:
            logger.warning("Did not receive 'ok' for G10 L2 P1 X0 Y0, continuing anyway")

        # Reset machine_x to 0 since work coordinates now start at 0
        state.machine_x = 0.0
        logger.info("Work coordinates reset complete")
        return True

    except Exception as e:
        logger.error(f"Error resetting work coordinates: {e}")
        return False


def restart_connection(homing=False):
    """
    Restart the connection. If a connection exists, close it and attempt to establish a new one.
    It will try to connect via serial first (if available), otherwise it will fall back to websocket.
    The new connection is saved to state.conn.
    
    Returns:
        True if the connection was restarted successfully, False otherwise.
    """
    try:
        if (state.conn.is_connected() if state.conn else False):
            logger.info("Closing current connection...")
            state.conn.close()
    except Exception as e:
        logger.error(f"Error while closing connection: {e}")

    # Clear the connection reference.
    state.conn = None

    logger.info("Attempting to restart connection...")
    try:
        connect_device(homing)  # This will set state.conn appropriately.
        if (state.conn.is_connected() if state.conn else False):
            logger.info("Connection restarted successfully.")
            return True
        else:
            logger.error("Failed to restart connection.")
            return False
    except Exception as e:
        logger.error(f"Error restarting connection: {e}")
        return False
