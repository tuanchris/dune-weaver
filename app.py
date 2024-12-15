from flask import Flask, request, jsonify, render_template
import os
import serial
import time
import threading
import serial.tools.list_ports
import math

app = Flask(__name__)

# Theta-rho directory
THETA_RHO_DIR = './patterns'
IGNORE_PORTS = ['/dev/cu.debug-console', '/dev/cu.Bluetooth-Incoming-Port']
os.makedirs(THETA_RHO_DIR, exist_ok=True)

# Serial connection (default None, will be set by user)
ser = None
ser_port = None  # Global variable to store the serial port name
stop_requested = False


def list_serial_ports():
    """Return a list of available serial ports."""
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports if port.device not in IGNORE_PORTS]

def connect_to_serial(port, baudrate=115200):
    """Connect to the specified serial port."""
    global ser, ser_port
    if ser and ser.is_open:
        ser.close()
    ser = serial.Serial(port, baudrate)
    ser_port = port  # Store the connected port globally
    time.sleep(2)  # Allow time for the connection to establish

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
    connect_to_serial(port, baudrate)

def parse_theta_rho_file(file_path, apply_transformations=False):
    """
    Parse a theta-rho file and return a list of (theta, rho) pairs.
    Optionally apply transformations (rotation and mirroring).
    """
    coordinates = []
    try:
        with open(file_path, 'r') as file:
            for line in file:
                line = line.strip()
                # Skip header or comment lines (starting with '#' or empty lines)
                if not line or line.startswith("#"):
                    continue

                # Parse lines with theta and rho separated by spaces
                try:
                    theta, rho = map(float, line.split())
                    if apply_transformations:
                        # Rotate 90 degrees clockwise
                        theta_rotated = theta - (math.pi / 2)
                        if theta_rotated < 0:  # Ensure theta stays within [0, 2π)
                            theta_rotated += 2 * math.pi

                        # Apply vertical mirror (negate theta)
                        theta_mirrored = -theta_rotated
                        if theta_mirrored < 0:  # Ensure theta stays within [0, 2π)
                            theta_mirrored += 2 * math.pi

                        coordinates.append((theta_mirrored, rho))
                    else:
                        coordinates.append((theta, rho))
                except ValueError:
                    print(f"Skipping invalid line: {line}")
    except Exception as e:
        print(f"Error reading file: {e}")
    return coordinates

def send_coordinate_batch(ser, coordinates):
    """Send a batch of theta-rho pairs to the Arduino."""
    # print("Sending batch:", coordinates)
    batch_str = ";".join(f"{theta:.3f},{rho:.3f}" for theta, rho in coordinates) + ";\n"
    ser.write(batch_str.encode())

def send_command(command):
    """Send a single command to the Arduino."""
    ser.write(f"{command}\n".encode())
    print(f"Sent: {command}")
    
    # Wait for "DONE" acknowledgment from Arduino
    while True:
        if ser.in_waiting > 0:
            response = ser.readline().decode().strip()
            print(f"Arduino response: {response}")
            if response == "DONE":
                print("Command execution completed.")
                break
        # time.sleep(0.5)  # Small delay to avoid busy waiting

def run_theta_rho_file(file_path):
    """Run a theta-rho file by sending data in optimized batches."""
    global stop_requested
    stop_requested = False

    coordinates = parse_theta_rho_file(file_path, True)
    if len(coordinates) < 2:
        print("Not enough coordinates for interpolation.")
        return

    # Optimize batch size for smoother execution
    batch_size = 1  # Smaller batches may smooth movement further
    for i in range(0, len(coordinates), batch_size):
        # Check stop_requested flag after sending the batch
        if stop_requested:
            print("Execution stopped by user after completing the current batch.")
            break
        batch = coordinates[i:i + batch_size]
        if i == 0:
            send_coordinate_batch(ser, batch)
            continue
        # Wait until Arduino is READY before sending the batch
        while True:
            if ser.in_waiting > 0:
                response = ser.readline().decode().strip()
                if response == "R":
                    send_coordinate_batch(ser, batch)
                    break
                else:
                    print(f"Arduino response: {response}")
                
    # Reset theta after execution or stopping
    reset_theta()
    ser.write("FINISHED\n".encode())
                
def reset_theta():
    ser.write("RESET_THETA\n".encode())
    while True:
        if ser.in_waiting > 0:
            response = ser.readline().decode().strip()
            print(f"Arduino response: {response}")
            if response == "THETA_RESET":
                print("Theta successfully reset.")
                break
        time.sleep(0.5)  # Small delay to avoid busy waiting
        
def read_serial_responses():
    """Continuously read and print all responses from the Arduino."""
    global ser
    if ser is None or not ser.is_open:
        print("Serial connection not established.")
        return
    
    while True:
        try:
            if ser.in_waiting > 0:
                response = ser.readline().decode().strip()
                print(f"Arduino response: {response}")
        except Exception as e:
            print(f"Error reading from serial: {e}")
            break

# Flask endpoints
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/list_serial_ports', methods=['GET'])
def list_ports():
    return jsonify(list_serial_ports())

@app.route('/connect_serial', methods=['POST'])
def connect_serial():
    port = request.json.get('port')
    if not port:
        return jsonify({'error': 'No port provided'}), 400

    try:
        connect_to_serial(port)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/disconnect_serial', methods=['POST'])
def disconnect():
    try:
        disconnect_serial()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/restart_serial', methods=['POST'])
def restart():
    port = request.json.get('port')
    if not port:
        return jsonify({'error': 'No port provided'}), 400

    try:
        restart_serial(port)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/list_theta_rho_files', methods=['GET'])
def list_theta_rho_files():
    files = []
    for root, _, filenames in os.walk(THETA_RHO_DIR):
        for file in filenames:
            # Construct the relative file path
            relative_path = os.path.relpath(os.path.join(root, file), THETA_RHO_DIR)
            files.append(relative_path)
    return jsonify(sorted(files))

@app.route('/upload_theta_rho', methods=['POST'])
def upload_theta_rho():
    custom_patterns_dir = os.path.join(THETA_RHO_DIR, 'custom_patterns')
    os.makedirs(custom_patterns_dir, exist_ok=True)  # Ensure the directory exists

    file = request.files['file']
    if file:
        file.save(os.path.join(custom_patterns_dir, file.filename))
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/run_theta_rho', methods=['POST'])
def run_theta_rho():
    file_name = request.json.get('file_name')
    pre_execution = request.json.get('pre_execution')  # New parameter for pre-execution action

    if not file_name:
        return jsonify({'error': 'No file name provided'}), 400

    file_path = os.path.join(THETA_RHO_DIR, file_name)
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404

    try:
        # Handle pre-execution actions
        if pre_execution == 'clear_in':
            clear_in_thread = threading.Thread(target=run_theta_rho_file, args=('./patterns/clear_from_in.thr',))
            clear_in_thread.start()
            clear_in_thread.join()  # Wait for completion before proceeding
        elif pre_execution == 'clear_out':
            clear_out_thread = threading.Thread(target=run_theta_rho_file, args=('./patterns/clear_from_out.thr',))
            clear_out_thread.start()
            clear_out_thread.join()  # Wait for completion before proceeding
        elif pre_execution == 'none':
            pass  # No pre-execution action required

        # Start the main pattern execution
        threading.Thread(target=run_theta_rho_file, args=(file_path,)).start()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    

@app.route('/stop_execution', methods=['POST'])
def stop_execution():
    global stop_requested
    stop_requested = True
    return jsonify({'success': True})

@app.route('/send_home', methods=['POST'])
def send_home():
    """Send the HOME command to the Arduino."""
    try:
        send_command("HOME")
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/run_theta_rho_file/<file_name>', methods=['POST'])
def run_specific_theta_rho_file(file_name):
    """Run a specific theta-rho file."""
    file_path = os.path.join(THETA_RHO_DIR, file_name)
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404

    threading.Thread(target=run_theta_rho_file, args=(file_path,)).start()
    return jsonify({'success': True})

@app.route('/delete_theta_rho_file', methods=['POST'])
def delete_theta_rho_file():
    data = request.json
    file_name = data.get('file_name')

    if not file_name:
        return jsonify({"success": False, "error": "No file name provided"}), 400

    file_path = os.path.join(THETA_RHO_DIR, file_name)

    if not os.path.exists(file_path):
        return jsonify({"success": False, "error": "File not found"}), 404

    try:
        os.remove(file_path)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/move_to_center', methods=['POST'])
def move_to_center():
    """Move the sand table to the center position."""
    try:
        if ser is None or not ser.is_open:
            return jsonify({"success": False, "error": "Serial connection not established"}), 400

        coordinates = [(0, 0)]  # Center position
        send_coordinate_batch(ser, coordinates)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    
@app.route('/move_to_perimeter', methods=['POST'])
def move_to_perimeter():
    """Move the sand table to the perimeter position."""
    try:
        if ser is None or not ser.is_open:
            return jsonify({"success": False, "error": "Serial connection not established"}), 400

        MAX_RHO = 1
        coordinates = [(0, MAX_RHO)]  # Perimeter position
        send_coordinate_batch(ser, coordinates)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    
@app.route('/preview_thr', methods=['POST'])
def preview_thr():
    file_name = request.json.get('file_name')
    
    if not file_name:
        return jsonify({'error': 'No file name provided'}), 400

    file_path = os.path.join(THETA_RHO_DIR, file_name)
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404

    try:
        # Parse the .thr file with transformations
        coordinates = parse_theta_rho_file(file_path, apply_transformations=True)
        return jsonify({'success': True, 'coordinates': coordinates})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/send_coordinate', methods=['POST'])
def send_coordinate():
    """Send a single (theta, rho) coordinate to the Arduino."""
    global ser
    if ser is None or not ser.is_open:
        return jsonify({"success": False, "error": "Serial connection not established"}), 400

    try:
        data = request.json
        theta = data.get('theta')
        rho = data.get('rho')

        if theta is None or rho is None:
            return jsonify({"success": False, "error": "Theta and Rho are required"}), 400

        # Send the coordinate to the Arduino
        send_coordinate_batch(ser, [(theta, rho)])
        reset_theta()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# Expose files for download if needed
@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    """Download a file from the theta-rho directory."""
    return send_from_directory(THETA_RHO_DIR, filename)

@app.route('/serial_status', methods=['GET'])
def serial_status():
    global ser, ser_port
    return jsonify({
        'connected': ser.is_open if ser else False,
        'port': ser_port  # Include the port name
    })
    
@app.route('/set_speed', methods=['POST'])
def set_speed():
    """Set the speed for the Arduino."""
    global ser
    if ser is None or not ser.is_open:
        return jsonify({"success": False, "error": "Serial connection not established"}), 400

    try:
        # Parse the speed value from the request
        data = request.json
        speed = data.get('speed')

        if speed is None:
            return jsonify({"success": False, "error": "Speed is required"}), 400

        if not isinstance(speed, (int, float)) or speed <= 0:
            return jsonify({"success": False, "error": "Invalid speed value"}), 400

        # Send the SET_SPEED command to the Arduino
        command = f"SET_SPEED {speed}"
        send_command(command)
        return jsonify({"success": True, "speed": speed})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    # Start the thread for reading Arduino responses
    threading.Thread(target=read_serial_responses, daemon=True).start()
    
    app.run(debug=True, host='0.0.0.0', port=8080)
