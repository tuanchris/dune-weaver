import serial
import serial.tools.list_ports
import threading
import time
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Global state
ser = None
ser_port = None
serial_lock = threading.RLock()
IGNORE_PORTS = ['/dev/cu.debug-console', '/dev/cu.Bluetooth-Incoming-Port']

# Device information
arduino_table_name = None
arduino_driver_type = 'Unknown'
firmware_version = 'Unknown'

def list_serial_ports():
    """Return a list of available serial ports."""
    ports = serial.tools.list_ports.comports()
    available_ports = [port.device for port in ports if port.device not in IGNORE_PORTS]
    logger.debug(f"Available serial ports: {available_ports}")
    return available_ports

def connect_to_serial(port=None, baudrate=115200):
    """Automatically connect to the first available serial port or a specified port."""
    global ser, ser_port, arduino_table_name, arduino_driver_type, firmware_version
    try:
        if port is None:
            ports = list_serial_ports()
            if not ports:
                logger.warning("No serial port connected")
                return False
            port = ports[0]  # Auto-select the first available port

        with serial_lock:
            if ser and ser.is_open:
                ser.close()
            ser = serial.Serial(port, baudrate, timeout=2)
            ser_port = port
        home()
        logger.info(f"Connected to serial port: {port}")
        time.sleep(2)  # Allow time for the connection to establish

        # Read initial startup messages from Arduino
        while ser.in_waiting > 0:
            line = ser.readline().decode().strip()
            logger.debug(f"Arduino: {line}")

            # Store the device details based on the expected messages
            if "Table:" in line:
                arduino_table_name = line.replace("Table: ", "").strip()
            elif "Drivers:" in line:
                arduino_driver_type = line.replace("Drivers: ", "").strip()
            elif "Version:" in line:
                firmware_version = line.replace("Version: ", "").strip()

        logger.info(f"Detected Table: {arduino_table_name or 'Unknown'}")
        logger.info(f"Detected Drivers: {arduino_driver_type or 'Unknown'}")

        return True
    except serial.SerialException as e:
        logger.error(f"Failed to connect to serial port {port}: {e}")
        ser_port = None

    logger.error("Max retries reached. Could not connect to a serial port.")
    return False

def disconnect_serial():
    """Disconnect the current serial connection."""
    global ser, ser_port
    if ser and ser.is_open:
        logger.info("Disconnecting serial connection")
        ser.close()
        ser = None
    ser_port = None

def restart_serial(port, baudrate=115200):
    """Restart the serial connection."""
    logger.info(f"Restarting serial connection on port {port}")
    disconnect_serial()
    return connect_to_serial(port, baudrate)

def is_connected():
    """Check if serial connection is established and open."""
    return ser is not None and ser.is_open

def get_port():
    """Get the current serial port."""
    return ser_port


def send_grbl_coordinates(x, y, speed=600, max_retries=20, retry_interval=0.5):
    """Send G-code command to FluidNC and retry every 0.5s if no 'ok' is received."""
    attempt = 0  # Retry counter

    while attempt < max_retries:
        with serial_lock:
            gcode = f"$J=G91 G21 X{x} Y{y} F{speed}"
            ser.write(f"{gcode}\n".encode())
            ser.flush()
            logger.debug(f"Sent command (Attempt {attempt+1}/{max_retries}): {gcode}")

            # Wait for response
            while True:
                if ser.in_waiting > 0:
                    response = ser.readline().decode().strip()
                    logger.debug(f"Response: {response}")
                    if response.lower() == "ok":
                        logger.debug("Command execution completed")
                        return  # Exit function if 'ok' is received

        # Wait before retrying
        attempt += 1
        logger.warning(f"Attempt {attempt}: No 'ok' received, retrying in {retry_interval}s...")
        time.sleep(retry_interval)

    logger.error(f"Failed to receive 'ok' after {max_retries} attempts. Giving up.")

def home():
    logger.info("Homing")
    send_grbl_coordinates(0, -110, 1000)
    current_theta = current_rho = 0

def check_idle():
    """Continuously check if the machine is in the 'Idle' state."""
    logger.info("Checking idle")
    while True:
        with serial_lock:
            ser.write('?'.encode())  # Send status query
            ser.flush()  # Ensure it's sent immediately

            if ser.in_waiting > 0:
                response = ser.readline().decode().strip()
                logger.info(f"Response: {response}")
                if "Idle" in response:
                    logger.info("Tabble is idle")
                    return True  # Exit function once 'Idle' is received

        time.sleep(1)  # Wait before retrying