import serial
import serial.tools.list_ports
import threading
import time

class SerialManager:
    def __init__(self):
        self.ser = None
        self.ser_port = None
        self.serial_lock = threading.RLock()
        self.IGNORE_PORTS = ['/dev/cu.debug-console', '/dev/cu.Bluetooth-Incoming-Port']
        
        # Device information
        self.arduino_table_name = None
        self.arduino_driver_type = 'Unknown'
        self.firmware_version = 'Unknown'

    def list_serial_ports(self):
        """Return a list of available serial ports."""
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports if port.device not in self.IGNORE_PORTS]

    def connect_to_serial(self, port=None, baudrate=115200):
        """Automatically connect to the first available serial port or a specified port."""
        try:
            if port is None:
                ports = self.list_serial_ports()
                if not ports:
                    print("No serial port connected")
                    return False
                port = ports[0]  # Auto-select the first available port

            with self.serial_lock:
                if self.ser and self.ser.is_open:
                    self.ser.close()
                self.ser = serial.Serial(port, baudrate, timeout=2)
                self.ser_port = port

            print(f"Connected to serial port: {port}")
            time.sleep(2)  # Allow time for the connection to establish

            # Read initial startup messages from Arduino
            while self.ser.in_waiting > 0:
                line = self.ser.readline().decode().strip()
                print(f"Arduino: {line}")

                # Store the device details based on the expected messages
                if "Table:" in line:
                    self.arduino_table_name = line.replace("Table: ", "").strip()
                elif "Drivers:" in line:
                    self.arduino_driver_type = line.replace("Drivers: ", "").strip()
                elif "Version:" in line:
                    self.firmware_version = line.replace("Version: ", "").strip()

            print(f"Detected Table: {self.arduino_table_name or 'Unknown'}")
            print(f"Detected Drivers: {self.arduino_driver_type or 'Unknown'}")

            return True
        except serial.SerialException as e:
            print(f"Failed to connect to serial port {port}: {e}")
            self.ser_port = None

        print("Max retries reached. Could not connect to a serial port.")
        return False

    def disconnect_serial(self):
        """Disconnect the current serial connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.ser = None
        self.ser_port = None

    def restart_serial(self, port, baudrate=115200):
        """Restart the serial connection."""
        self.disconnect_serial()
        return self.connect_to_serial(port, baudrate)

    def send_coordinate_batch(self, coordinates):
        """Send a batch of theta-rho pairs to the Arduino."""
        batch_str = ";".join(f"{theta:.5f},{rho:.5f}" for theta, rho in coordinates) + ";\n"
        with self.serial_lock:
            self.ser.write(batch_str.encode())

    def send_command(self, command):
        """Send a single command to the Arduino."""
        with self.serial_lock:
            self.ser.write(f"{command}\n".encode())
            print(f"Sent: {command}")

            # Wait for "R" acknowledgment from Arduino
            while True:
                with self.serial_lock:
                    if self.ser.in_waiting > 0:
                        response = self.ser.readline().decode().strip()
                        print(f"Arduino response: {response}")
                        if response == "R":
                            print("Command execution completed.")
                            break

    def is_connected(self):
        """Check if serial connection is established and open."""
        return self.ser is not None and self.ser.is_open

    def get_port(self):
        """Get the current serial port."""
        return self.ser_port

# Create a global instance
serial_manager = SerialManager()
