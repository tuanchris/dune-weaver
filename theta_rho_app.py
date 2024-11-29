from flask import Flask, request, jsonify, render_template
import os
import serial
import time
import threading
import serial.tools.list_ports
import math

app = Flask(__name__)

# Theta-rho directory
THETA_RHO_DIR = './theta_rho_files'
os.makedirs(THETA_RHO_DIR, exist_ok=True)

# Serial connection (default None, will be set by user)
ser = None
stop_requested = False

def list_serial_ports():
    """Return a list of available serial ports."""
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports]

def connect_to_serial(port, baudrate=115200):
    """Connect to the specified serial port."""
    global ser
    if ser and ser.is_open:
        ser.close()
    ser = serial.Serial(port, baudrate)
    time.sleep(2)  # Allow time for the connection to establish

def disconnect_serial():
    """Disconnect the current serial connection."""
    global ser
    if ser and ser.is_open:
        ser.close()
        ser = None

def restart_serial(port, baudrate=115200):
    """Restart the serial connection."""
    disconnect_serial()
    connect_to_serial(port, baudrate)

def parse_theta_rho_file(file_path):
    """Parse a theta-rho file and return a list of (theta, rho) pairs."""
    coordinates = []
    with open(file_path, 'r') as file:
        for line in file:
            line = line.strip()
            
            # Skip header or comment lines (starting with '#' or empty lines)
            if not line or line.startswith("#"):
                print(f"Skipping invalid line: {line}")
                continue

            # Parse lines with theta and rho separated by spaces
            try:
                theta, rho = map(float, line.split())
                coordinates.append((theta, rho))
            except ValueError:
                print(f"Skipping invalid line: {line}")
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
        time.sleep(0.5)  # Small delay to avoid busy waiting

def run_theta_rho_file(file_path):
    """Run a theta-rho file by interpolating straight paths and sending data in optimized batches."""
    global stop_requested
    stop_requested = False

    coordinates = parse_theta_rho_file(file_path)
    if len(coordinates) < 2:
        print("Not enough coordinates for interpolation.")
        return

    # Optimize batch size for smoother execution
    batch_size = 10  # Smaller batches may smooth movement further
    for i in range(0, len(coordinates), batch_size):
        batch = coordinates[i:i + batch_size]

        # Wait until Arduino is READY before sending the batch
        while True:
            if ser.in_waiting > 0:
                response = ser.readline().decode().strip()
                if response == "READY":
                    send_coordinate_batch(ser, batch)
                    break
                else:
                    print(f"Arduino response: {response}")
        
        # Check stop_requested flag after sending the batch
        if stop_requested:
            print("Execution stopped by user after completing the current batch.")
            break

    # Reset theta after execution or stopping
    reset_theta()
                
def reset_theta():
    ser.write(b"RESET_THETA\n")
    while True:
        if ser.in_waiting > 0:
            response = ser.readline().decode().strip()
            print(f"Arduino response: {response}")
            if response == "THETA_RESET":
                print("Theta successfully reset.")
                break
        time.sleep(0.5)  # Small delay to avoid busy waiting

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
    files = os.listdir(THETA_RHO_DIR)
    return jsonify(files)

@app.route('/upload_theta_rho', methods=['POST'])
def upload_theta_rho():
    file = request.files['file']
    if file:
        file.save(os.path.join(THETA_RHO_DIR, file.filename))
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/run_theta_rho', methods=['POST'])
def run_theta_rho():
    file_name = request.json.get('file_name')
    if not file_name:
        return jsonify({'error': 'No file name provided'}), 400

    file_path = os.path.join(THETA_RHO_DIR, file_name)
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404

    threading.Thread(target=run_theta_rho_file, args=(file_path,)).start()
    return jsonify({'success': True})

@app.route('/stop_execution', methods=['POST'])
def stop_execution():
    global stop_requested
    stop_requested = True
    reset_theta()
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

# Expose files for download if needed
@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    """Download a file from the theta-rho directory."""
    return send_from_directory(THETA_RHO_DIR, filename)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
