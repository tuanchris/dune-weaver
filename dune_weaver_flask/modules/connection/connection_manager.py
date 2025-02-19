import threading
import time
import logging
import serial
import serial.tools.list_ports
import websocket

from dune_weaver_flask.modules.core.state import state

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
        with self.lock:
            if self.ser.is_open:
                self.ser.close()

###############################################################################
# WebSocket Connection Implementation
###############################################################################

class WebSocketConnection(BaseConnection):
    def __init__(self, url: str, timeout: int = 2):
        self.url = url
        self.timeout = timeout
        self.lock = threading.RLock()
        self.ws = None
        self.connect()

    def connect(self):
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
        with self.lock:
            if self.ws:
                self.ws.close()
                
def list_serial_ports():
    """Return a list of available serial ports."""
    ports = serial.tools.list_ports.comports()
    available_ports = [port.device for port in ports if port.device not in IGNORE_PORTS]
    logger.debug(f"Available serial ports: {available_ports}")
    return available_ports

def connect_device():
    ports = list_serial_ports()
    if not ports:
        state.conn = WebSocketConnection('ws://fluidnc.local:81')
    else:
        state.conn = SerialConnection(ports[0])
        

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
    """
    logger.debug(f"Sending G-code: X{x} Y{y} at F{speed}")
    while True:
        try:
            gcode = f"$J=G91 Y{y} F{speed}" if home else f"G1 X{x} Y{y} F{speed}"
            state.conn.send(gcode + "\n")
            logger.debug(f"Sent command: {gcode}")
            start_time = time.time()
            while time.time() - start_time < timeout:
                response = state.conn.readline()
                logger.debug(f"Response: {response}")
                if response.lower() == "ok":
                    logger.debug("Command execution confirmed.")
                    return
        except Exception as e:
            logger.debug(f"No 'ok' received for X{x} Y{y}, speed {speed}. Retrying in 1s...")
        time.sleep(0.1)
        

def get_machine_steps(timeout=10):
    """
    Send "$$" to retrieve machine settings and update state.
    Returns True if the expected configuration is received, or False if it times out.
    """
    if not state.conn.is_connected():
        logger.error("Connection is not established.")
        return False

    # Send the command once
    state.conn.send("$$\n")
    start_time = time.time()
    x_steps_per_mm = y_steps_per_mm = gear_ratio = None

    while time.time() - start_time < timeout:
        try:
            # Attempt to read a line from the connection
            response = state.conn.readline()
            logger.debug(response)
            for line in response.splitlines():
                logger.debug(f"Config response: {line}")
                if line.startswith("$100="):
                    x_steps_per_mm = float(line.split("=")[1])
                    state.x_steps_per_mm = x_steps_per_mm
                elif line.startswith("$101="):
                    y_steps_per_mm = float(line.split("=")[1])
                    state.y_steps_per_mm = y_steps_per_mm
                elif line.startswith("$131="):
                    gear_ratio = float(line.split("=")[1])
                    state.gear_ratio = gear_ratio
            
            # If all parameters are received, exit early
            if x_steps_per_mm is not None and y_steps_per_mm is not None and gear_ratio is not None:
                return True

        except Exception as e:
            logger.error(f"Error getting machine steps: {e}")
            return False

        # Use a smaller sleep to poll more frequently
        time.sleep(0.1)

    logger.error("Timeout reached waiting for machine steps")
    return False


def home(retry=0):
    """
    Perform homing by checking device configuration and sending the appropriate commands.
    """
    logger.info(f"Homing with speed {state.speed}")
    try:
        state.conn.send("$config\n")
        response = state.conn.readline().strip().lower()
        logger.debug(f"Config response: {response}")
    except Exception as e:
        logger.error(f"Error during homing config: {e}")
        response = ""
    if "sensorless" in response:
        logger.info("Using sensorless homing")
        state.conn.send("$H\n")
        state.conn.send("G1 Y0 F100\n")
    elif "filename" in response or "error:3" in response:
        logger.info("Using crash homing")
        send_grbl_coordinates(0, -110/5, 300, home=True)
    else:
        if retry < 3:
            time.sleep(1)
            home(retry + 1)
            return
        else:
            raise Exception("Couldn't get a valid response for homing after 3 retries")
    state.current_theta = state.current_rho = 0
    update_machine_position()

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
        time.sleep(0.1)
    logger.warning("Timeout reached waiting for machine position")
    return None, None

def update_machine_position():
    state.machine_x, state.machine_y = get_machine_position()
    state.save()

def restart_connection():
    """
    Restart the connection. If a connection exists, close it and attempt to establish a new one.
    It will try to connect via serial first (if available), otherwise it will fall back to websocket.
    The new connection is saved to state.conn.
    
    Returns:
        True if the connection was restarted successfully, False otherwise.
    """
    try:
        if state.conn and state.conn.is_connected():
            logger.info("Closing current connection...")
            state.conn.close()
    except Exception as e:
        logger.error(f"Error while closing connection: {e}")

    # Clear the connection reference.
    state.conn = None

    logger.info("Attempting to restart connection...")
    try:
        connect_device()  # This will set state.conn appropriately.
        if state.conn and state.conn.is_connected():
            logger.info("Connection restarted successfully.")
            return True
        else:
            logger.error("Failed to restart connection.")
            return False
    except Exception as e:
        logger.error(f"Error restarting connection: {e}")
        return False
