import serial
import serial.tools.list_ports
import threading
import time
import logging

logger = logging.getLogger(__name__)

# Configuration
IGNORE_PORTS = ['/dev/cu.debug-console', '/dev/cu.Bluetooth-Incoming-Port']

# Global variables
ser = None
ser_port = None
arduino_table_name = None
arduino_driver_type = 'Unknown'
firmware_version = 'Unknown'
serial_lock = threading.Lock()

def list_serial_ports():
    """Return a list of available serial ports."""
    try:
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports if port.device not in IGNORE_PORTS]
    except Exception as e:
        logger.error(f"Error listing serial ports: {str(e)}", exc_info=True)
        return []

def connect_to_serial(port=None, baudrate=115200):
    """Automatically connect to the first available serial port or a specified port."""
    global ser, ser_port, arduino_table_name, arduino_driver_type, firmware_version

    try:
        if port is None:
            ports = list_serial_ports()
            if not ports:
                logger.error("No serial port connected")
                return False
            port = ports[0]  # Auto-select the first available port

        with serial_lock:
            if ser and ser.is_open:
                ser.close()
            ser = serial.Serial(port, baudrate, timeout=2)  # Set timeout to avoid infinite waits
            ser_port = port  # Store the connected port globally

        logger.info(f"Connected to serial port: {port}")
        time.sleep(2)  # Allow time for the connection to establish

        # Read initial startup messages from Arduino
        arduino_table_name = None
        arduino_driver_type = None

        while ser.in_waiting > 0:
            try:
                line = ser.readline().decode().strip()
                logger.debug(f"Arduino: {line}")  # Print the received message

                # Store the device details based on the expected messages
                if "Table:" in line:
                    arduino_table_name = line.replace("Table: ", "").strip()
                elif "Drivers:" in line:
                    arduino_driver_type = line.replace("Drivers: ", "").strip()
                elif "Version:" in line:
                    firmware_version = line.replace("Version: ", "").strip()
            except UnicodeDecodeError as e:
                logger.warning(f"Failed to decode Arduino message: {str(e)}")
                continue

        logger.info(f"Detected Table: {arduino_table_name or 'Unknown'}")
        logger.info(f"Detected Drivers: {arduino_driver_type or 'Unknown'}")

        return True  # Successfully connected
    except serial.SerialException as e:
        logger.error(f"Failed to connect to serial port {port}: {str(e)}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Unexpected error connecting to serial port: {str(e)}", exc_info=True)
        return False

def disconnect_serial():
    """Disconnect the current serial connection."""
    global ser, ser_port
    try:
        if ser and ser.is_open:
            ser.close()
            logger.info(f"Disconnected from serial port: {ser_port}")
        ser = None
        ser_port = None
    except Exception as e:
        logger.error(f"Error disconnecting serial port: {str(e)}", exc_info=True)

def restart_serial(port, baudrate=115200):
    """Restart the serial connection."""
    try:
        disconnect_serial()
        return connect_to_serial(port, baudrate)
    except Exception as e:
        logger.error(f"Error restarting serial connection: {str(e)}", exc_info=True)
        return False

def send_command(command):
    """Send a single command to the Arduino."""
    try:
        if not ser or not ser.is_open:
            logger.error("Cannot send command: Serial port not open")
            return None

        ser.write(f"{command}\n".encode())
        logger.debug(f"Sent: {command}")

        # Wait for "R" acknowledgment from Arduino
        while True:
            with serial_lock:
                if ser.in_waiting > 0:
                    response = ser.readline().decode().strip()
                    logger.debug(f"Arduino response: {response}")
                    if response == "R":
                        logger.debug("Command execution completed.")
                        return response
    except serial.SerialException as e:
        logger.error(f"Serial communication error while sending command: {str(e)}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error sending command: {str(e)}", exc_info=True)
        return None

def send_coordinate_batch(coordinates):
    """Send a batch of theta-rho pairs to the Arduino."""
    try:
        if not ser or not ser.is_open:
            logger.error("Cannot send coordinates: Serial port not open")
            return False

        batch_str = ";".join(f"{theta:.5f},{rho:.5f}" for theta, rho in coordinates) + ";\n"
        ser.write(batch_str.encode())
        return True
    except Exception as e:
        logger.error(f"Error sending coordinate batch: {str(e)}", exc_info=True)
        return False

def get_serial_status():
    """Get the current status of the serial connection."""
    try:
        return {
            'connected': ser.is_open if ser else False,
            'port': ser_port
        }
    except Exception as e:
        logger.error(f"Error getting serial status: {str(e)}", exc_info=True)
        return {
            'connected': False,
            'port': None
        }

def get_device_info():
    """Get information about the connected device."""
    try:
        return {
            'table_name': arduino_table_name,
            'driver_type': arduino_driver_type,
            'firmware_version': firmware_version
        }
    except Exception as e:
        logger.error(f"Error getting device info: {str(e)}", exc_info=True)
        return {
            'table_name': None,
            'driver_type': None,
            'firmware_version': None
        }

def reset_theta():
    """Reset theta on the Arduino."""
    try:
        if not ser or not ser.is_open:
            logger.error("Cannot reset theta: Serial port not open")
            return False

        ser.write("RESET_THETA\n".encode())
        while True:
            with serial_lock:
                if ser.in_waiting > 0:
                    response = ser.readline().decode().strip()
                    logger.debug(f"Arduino response: {response}")
                    if response == "THETA_RESET":
                        logger.info("Theta successfully reset.")
                        return True
            time.sleep(0.5)  # Small delay to avoid busy waiting
    except Exception as e:
        logger.error(f"Error resetting theta: {str(e)}", exc_info=True)
        return False 