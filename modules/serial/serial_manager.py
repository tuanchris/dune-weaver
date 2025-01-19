import serial
import serial.tools.list_ports
import threading
import time

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
            ser = serial.Serial(port, baudrate, timeout=2)  # Set timeout to avoid infinite waits
            ser_port = port  # Store the connected port globally

        print(f"Connected to serial port: {port}")
        time.sleep(2)  # Allow time for the connection to establish

        # Read initial startup messages from Arduino
        arduino_table_name = None
        arduino_driver_type = None

        while ser.in_waiting > 0:
            line = ser.readline().decode().strip()
            print(f"Arduino: {line}")  # Print the received message

            # Store the device details based on the expected messages
            if "Table:" in line:
                arduino_table_name = line.replace("Table: ", "").strip()
            elif "Drivers:" in line:
                arduino_driver_type = line.replace("Drivers: ", "").strip()
            elif "Version:" in line:
                firmware_version = line.replace("Version: ", "").strip()

        # Display stored values
        print(f"Detected Table: {arduino_table_name or 'Unknown'}")
        print(f"Detected Drivers: {arduino_driver_type or 'Unknown'}")

        return True  # Successfully connected
    except serial.SerialException as e:
        print(f"Failed to connect to serial port {port}: {e}")
        port = None  # Reset the port to try the next available one

    print("Max retries reached. Could not connect to a serial port.")
    return False

def disconnect_serial():
    """Disconnect the current serial connection."""
    global ser, ser_port
    if ser and ser.is_open:
        ser.close()
        ser = None
    ser_port = None  # Reset the port name

def restart_serial(port, baudrate=115200):
    """Restart the serial connection."""
    disconnect_serial()
    return connect_to_serial(port, baudrate)

def send_command(command):
    """Send a single command to the Arduino."""
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

def send_coordinate_batch(coordinates):
    """Send a batch of theta-rho pairs to the Arduino."""
    batch_str = ";".join(f"{theta:.5f},{rho:.5f}" for theta, rho in coordinates) + ";\n"
    ser.write(batch_str.encode())

def get_serial_status():
    """Get the current status of the serial connection."""
    return {
        'connected': ser.is_open if ser else False,
        'port': ser_port
    }

def get_device_info():
    """Get information about the connected device."""
    return {
        'table_name': arduino_table_name,
        'driver_type': arduino_driver_type,
        'firmware_version': firmware_version
    }

def reset_theta():
    """Reset theta on the Arduino."""
    ser.write("RESET_THETA\n".encode())
    while True:
        with serial_lock:
            if ser.in_waiting > 0:
                response = ser.readline().decode().strip()
                print(f"Arduino response: {response}")
                if response == "THETA_RESET":
                    print("Theta successfully reset.")
                    break
        time.sleep(0.5)  # Small delay to avoid busy waiting 