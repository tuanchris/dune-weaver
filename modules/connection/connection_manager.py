import threading
import time
import logging
import serial
import serial.tools.list_ports
import websocket

from modules.core.state import state
from modules.led.led_controller import effect_loading, effect_idle, effect_connected, LEDController
logger = logging.getLogger(__name__)

IGNORE_PORTS = ['/dev/cu.debug-console', '/dev/cu.Bluetooth-Incoming-Port']

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

    def is_connected(self) -> bool:
        return self.ser is not None and self.ser.is_open

    def close(self) -> None:
        update_machine_position()
        with self.lock:
            if self.ser.is_open:
                self.ser.close()
        # Release the lock resources
        self.lock = None

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
        update_machine_position()
        with self.lock:
            if self.ws:
                self.ws.close()
        # Release the lock resources
        self.lock = None
                
def list_serial_ports():
    """Return a list of available serial ports."""
    ports = serial.tools.list_ports.comports()
    available_ports = [port.device for port in ports if port.device not in IGNORE_PORTS]
    logger.debug(f"Available serial ports: {available_ports}")
    return available_ports

def device_init(homing=True):
    try:
        if get_machine_steps():
            logger.info(f"x_steps_per_mm: {state.x_steps_per_mm}, y_steps_per_mm: {state.y_steps_per_mm}, gear_ratio: {state.gear_ratio}")
    except:
        logger.fatal("Not GRBL firmware")
        pass

    machine_x, machine_y = get_machine_position()
    if machine_x != state.machine_x or machine_y != state.machine_y:
        logger.info(f'x, y; {machine_x}, {machine_y}')
        logger.info(f'State x, y; {state.machine_x}, {state.machine_y}')
        if homing:
            home()
    else:
        logger.info('Machine position known, skipping home')
        logger.info(f'Theta: {state.current_theta}, rho: {state.current_rho}')
        logger.info(f'x, y; {machine_x}, {machine_y}')
        logger.info(f'State x, y; {state.machine_x}, {state.machine_y}')

    time.sleep(2)  # Allow time for the connection to establish


def connect_device(homing=True):
    if state.wled_ip:
        state.led_controller = LEDController(state.wled_ip)
        effect_loading(state.led_controller)
        
    ports = list_serial_ports()

    if state.port and state.port in ports:
        state.conn = SerialConnection(state.port)
    elif ports:
        state.conn = SerialConnection(ports[0])
    else:
        logger.warning("No serial ports found. Falling back to WebSocket.")
        # state.conn = WebSocketConnection('ws://fluidnc.local:81')
        return
    if (state.conn.is_connected() if state.conn else False):
        device_init(homing)
        
    if state.led_controller:
        effect_connected(state.led_controller)

def get_status_response() -> str:
    """
    Send a status query ('?') and return the response if available.
    """
    while True:
        try:
            state.conn.send('?')
            response = state.conn.readline()
            if "MPos" in response:
                logger.debug(f"Status response: {response}")
                return response
        except Exception as e:
            logger.error(f"Error getting status response: {e}")
            return False
        time.sleep(1)
        
def parse_machine_position(response: str):
    """
    Parse the work position (MPos) from a status response.
    Expected format: "<...|MPos:-994.869,-321.861,0.000|...>"
    Returns a tuple (work_x, work_y) if found, else None.
    """
    if "MPos:" not in response:
        return None
    try:
        wpos_section = next((part for part in response.split("|") if part.startswith("MPos:")), None)
        if wpos_section:
            wpos_str = wpos_section.split(":", 1)[1]
            wpos_values = wpos_str.split(",")
            work_x = float(wpos_values[0])
            work_y = float(wpos_values[1])
            return work_x, work_y
    except Exception as e:
        logger.error(f"Error parsing work position: {e}")
    return None


def send_grbl_coordinates(x, y, speed=600, timeout=2, home=False):
    """
    Send a G-code command to FluidNC and wait for an 'ok' response.
    If no response after set timeout, sets state to stop and disconnects.
    """
    logger.debug(f"Sending G-code: X{x} Y{y} at F{speed}")
    
    # Track overall attempt time
    overall_start_time = time.time()
    
    while True:
        try:
            gcode = f"$J=G91 G21 Y{y} F{speed}" if home else f"G1 X{x} Y{y} F{speed}"
            state.conn.send(gcode + "\n")
            logger.debug(f"Sent command: {gcode}")
            start_time = time.time()
            while True:
                response = state.conn.readline()
                logger.debug(f"Response: {response}")
                if response.lower() == "ok":
                    logger.debug("Command execution confirmed.")
                    return
        except Exception as e:
            # Store the error string inside the exception block
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

            
        logger.warning(f"No 'ok' received for X{x} Y{y}, speed {speed}. Retrying...")
        time.sleep(0.1)
    
    # If we reach here, the timeout has occurred
    logger.error(f"Failed to receive 'ok' response after {max_total_attempt_time} seconds. Stopping and disconnecting.")
    
    # Set state to stop
    state.stop_requested = True
    
    # Set connection status to disconnected
    if state.conn:
        try:
            state.conn.disconnect()
        except:
            pass
        state.conn = None
        
    # Update the state connection status
    state.is_connected = False
    logger.info("Connection marked as disconnected due to timeout")
    return False

def get_machine_steps(timeout=10):
    """
    Get machine steps/mm from the GRBL controller.
    Returns True if successful, False otherwise.
    """
    if not state.conn or not state.conn.is_connected():
        logger.error("Cannot get machine steps: No connection available")
        return False

    x_steps_per_mm = None
    y_steps_per_mm = None
    gear_ratio = None
    start_time = time.time()

    # Clear any pending data in the buffer
    try:
        while state.conn.in_waiting() > 0:
            state.conn.readline()
    except Exception as e:
        logger.warning(f"Error clearing buffer: {e}")

    # Send the command to request all settings
    try:
        logger.info("Requesting GRBL settings with $$ command")
        state.conn.send("$$\n")
        time.sleep(0.5)  # Give GRBL a moment to process and respond
    except Exception as e:
        logger.error(f"Error sending $$ command: {e}")
        return False

    # Wait for and process responses
    settings_complete = False
    while time.time() - start_time < timeout and not settings_complete:
        try:
            # Attempt to read a line from the connection
            if state.conn.in_waiting() > 0:
                response = state.conn.readline()
                logger.debug(f"Raw response: {response}")
                
                # Process the line
                if response.strip():  # Only process non-empty lines
                    for line in response.splitlines():
                        line = line.strip()
                        logger.debug(f"Config response: {line}")
                        if line.startswith("$100="):
                            x_steps_per_mm = float(line.split("=")[1])
                            state.x_steps_per_mm = x_steps_per_mm
                            logger.info(f"X steps per mm: {x_steps_per_mm}")
                        elif line.startswith("$101="):
                            y_steps_per_mm = float(line.split("=")[1])
                            state.y_steps_per_mm = y_steps_per_mm
                            logger.info(f"Y steps per mm: {y_steps_per_mm}")
                        elif line.startswith("$131="):
                            gear_ratio = float(line.split("=")[1])
                            state.gear_ratio = gear_ratio
                            logger.info(f"Gear ratio: {gear_ratio}")
                        elif line.startswith("$22="):
                            # $22 reports if the homing cycle is enabled
                            # returns 0 if disabled, 1 if enabled
                            homing = int(line.split('=')[1])
                            state.homing = homing
                            logger.info(f"Homing enabled: {homing}")
                
                # Check if we've received all the settings we need
                if x_steps_per_mm is not None and y_steps_per_mm is not None and gear_ratio is not None:
                    settings_complete = True
            else:
                # No data waiting, small sleep to prevent CPU thrashing
                time.sleep(0.1)
                
                # If it's taking too long, try sending the command again after 3 seconds
                elapsed = time.time() - start_time
                if elapsed > 3 and elapsed < 4:
                    logger.warning("No response yet, sending $$ command again")
                    state.conn.send("$$\n")

        except Exception as e:
            logger.error(f"Error getting machine steps: {e}")
            time.sleep(0.5)
    
    # Process results and determine table type
    if settings_complete:
        if y_steps_per_mm == 180:
            state.table_type = 'dune_weaver_mini'
        elif y_steps_per_mm >= 320:
            state.table_type = 'dune_weaver_pro'
        elif y_steps_per_mm == 287.5:
            state.table_type = 'dune_weaver'
        else:
            state.table_type = None
            logger.warning(f"Unknown table type with Y steps/mm: {y_steps_per_mm}")
        logger.info(f"Machine type detected: {state.table_type}")
        return True
    else:
        missing = []
        if x_steps_per_mm is None: missing.append("X steps/mm")
        if y_steps_per_mm is None: missing.append("Y steps/mm")
        if gear_ratio is None: missing.append("gear ratio")
        logger.error(f"Failed to get all machine parameters after {timeout}s. Missing: {', '.join(missing)}")
        return False

def home():
    """
    Perform homing by checking device configuration and sending the appropriate commands.
    """
    try:
        if state.homing:
            logger.info("Using sensorless homing")
            state.conn.send("$H\n")
            state.conn.send("G1 Y0 F100\n")
        else:
            homing_speed = 400
            if state.table_type == 'dune_weaver_mini':
                homing_speed = 120
            logger.info("Sensorless homing not supported. Using crash homing")
            logger.info(f"Homing with speed {homing_speed}")
            if state.gear_ratio == 6.25:
                send_grbl_coordinates(0, - 30, homing_speed, home=True)
                state.machine_y -= 30
            else:
                send_grbl_coordinates(0, -22, homing_speed, home=True)
                state.machine_y -= 22

        state.current_theta = state.current_rho = 0
    except Exception as e:
        logger.error(f"Error homing: {e}")
        return False

def check_idle():
    """
    Continuously check if the device is idle.
    """
    logger.info("Checking idle")
    while True:
        response = get_status_response()
        if response and "Idle" in response:
            logger.info("Device is idle")
            update_machine_position()
            return True
        time.sleep(1)
        

def get_machine_position(timeout=5):
    """
    Query the device for its position.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            state.conn.send('?')
            response = state.conn.readline()
            logger.debug(f"Raw status response: {response}")
            if "MPos" in response:
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

def update_machine_position():
    if (state.conn.is_connected() if state.conn else False):
        try:
            logger.info('Saving machine position')
            state.machine_x, state.machine_y = get_machine_position()
            state.save()
            logger.info(f'Machine position saved: {state.machine_x}, {state.machine_y}')
        except Exception as e:
            logger.error(f"Error updating machine position: {e}")

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
