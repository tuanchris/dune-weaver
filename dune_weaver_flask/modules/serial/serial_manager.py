import serial
import serial.tools.list_ports
import threading
import time

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
    return [port.device for port in ports if port.device not in IGNORE_PORTS]

def connect_to_serial(port=None, baudrate=115200):
    """Automatically connect to the first available serial port or a specified port."""
    global ser, ser_port, arduino_table_name, arduino_driver_type, firmware_version
    try:
        if port is None:
            ports = list_serial_ports()
            if not ports:
                print("No serial port connected")
                return False
            port = ports[0]  # Auto-select the first available port

        with serial_lock:
            if ser and ser.is_open:
                ser.close()
            ser = serial.Serial(port, baudrate, timeout=2)
            ser_port = port

        print(f"Connected to serial port: {port}")
        time.sleep(2)  # Allow time for the connection to establish

        # Read initial startup messages from Arduino
        while ser.in_waiting > 0:
            line = ser.readline().decode().strip()
            print(f"Arduino: {line}")

            # Store the device details based on the expected messages
            if "Table:" in line:
                arduino_table_name = line.replace("Table: ", "").strip()
            elif "Drivers:" in line:
                arduino_driver_type = line.replace("Drivers: ", "").strip()
            elif "Version:" in line:
                firmware_version = line.replace("Version: ", "").strip()

        print(f"Detected Table: {arduino_table_name or 'Unknown'}")
        print(f"Detected Drivers: {arduino_driver_type or 'Unknown'}")

        return True
    except serial.SerialException as e:
        print(f"Failed to connect to serial port {port}: {e}")
        ser_port = None

    print("Max retries reached. Could not connect to a serial port.")
    return False

def disconnect_serial():
    """Disconnect the current serial connection."""
    global ser, ser_port
    if ser and ser.is_open:
        ser.close()
        ser = None
    ser_port = None

def restart_serial(port, baudrate=115200):
    """Restart the serial connection."""
    disconnect_serial()
    return connect_to_serial(port, baudrate)

def send_coordinate_batch(coordinates):
    """Send a batch of theta-rho pairs to the Arduino."""
    batch_str = ";".join(f"{theta:.5f},{rho:.5f}" for theta, rho in coordinates) + ";\n"
    with serial_lock:
        ser.write(batch_str.encode())

def send_command(command):
    """Send a single command to the Arduino."""
    with serial_lock:
        ser.write(f"{command}\n".encode())
        print(f"Sent: {command}")

        # Wait for "R" acknowledgment from Arduino
        while True:
            with serial_lock:
                if ser.in_waiting > 0:
                    response = ser.readline().decode().strip()
                    print(f"Arduino response: {response}")
                    if response == "R":
                        print("Command execution completed.")
                        break

def is_connected():
    """Check if serial connection is established and open."""
    return ser is not None and ser.is_open

def get_port():
    """Get the current serial port."""
    return ser_port
