from flask import Flask, request, jsonify, render_template
import os
import serial
import time
import random
import threading
import serial.tools.list_ports
import math
import json
from datetime import datetime
import subprocess

app = Flask(__name__)

# Configuration
THETA_RHO_DIR = './patterns'
IGNORE_PORTS = ['/dev/cu.debug-console', '/dev/cu.Bluetooth-Incoming-Port']
CLEAR_PATTERNS = {
    "clear_from_in":  "./patterns/clear_from_in.thr",
    "clear_from_out": "./patterns/clear_from_out.thr",
    "clear_sideway":  "./patterns/clear_sideway.thr"
}
os.makedirs(THETA_RHO_DIR, exist_ok=True)

# Serial connection (First available will be selected by default)
ser = None
ser_port = None  # Global variable to store the serial port name
stop_requested = False
pause_requested = False
pause_condition = threading.Condition()

# Global variables to store device information
arduino_table_name = None
arduino_driver_type = 'Unknown'

# Table status
current_playing_file = None
execution_progress = None
firmware_version = 'Unknown'
current_playing_index = None
current_playlist = None
is_clearing = False

serial_lock = threading.Lock()

PLAYLISTS_FILE = os.path.join(os.getcwd(), "playlists.json")

MOTOR_TYPE_MAPPING = {
    "TMC2209": "./firmware/arduino_code_TMC2209/arduino_code_TMC2209.ino",
    "DRV8825": "./firmware/arduino_code/arduino_code.ino",
    "esp32": "./firmware/esp32/esp32.ino"
}

# Ensure the file exists and contains at least an empty JSON object
if not os.path.exists(PLAYLISTS_FILE):
    with open(PLAYLISTS_FILE, "w") as f:
        json.dump({}, f, indent=2)

def get_ino_firmware_details(ino_file_path):
    """
    Extract firmware details, including version and motor type, from the given .ino file.

    Args:
        ino_file_path (str): Path to the .ino file.

    Returns:
        dict: Dictionary containing firmware details such as version and motor type, or None if not found.
    """
    try:
        if not ino_file_path:
            raise ValueError("Invalid path: ino_file_path is None or empty.")

        firmware_details = {"version": None, "motorType": None}

        with open(ino_file_path, "r") as file:
            for line in file:
                # Extract firmware version
                if "firmwareVersion" in line:
                    start = line.find('"') + 1
                    end = line.rfind('"')
                    if start != -1 and end != -1 and start < end:
                        firmware_details["version"] = line[start:end]

                # Extract motor type
                if "motorType" in line:
                    start = line.find('"') + 1
                    end = line.rfind('"')
                    if start != -1 and end != -1 and start < end:
                        firmware_details["motorType"] = line[start:end]

        if not firmware_details["version"]:
            print(f"Firmware version not found in file: {ino_file_path}")
        if not firmware_details["motorType"]:
            print(f"Motor type not found in file: {ino_file_path}")

        return firmware_details if any(firmware_details.values()) else None

    except FileNotFoundError:
        print(f"File not found: {ino_file_path}")
        return None
    except Exception as e:
        print(f"Error reading .ino file: {str(e)}")
        return None

def check_git_updates():
    try:
        # Fetch the latest updates from the remote repository
        subprocess.run(["git", "fetch", "--tags", "--force"], check=True)

        # Get the latest tag from the remote
        latest_remote_tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0", "origin/main"]
        ).strip().decode()

        # Get the latest tag from the local branch
        latest_local_tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0"]
        ).strip().decode()

        # Count how many tags the local branch is behind
        tag_behind_count = 0
        if latest_local_tag != latest_remote_tag:
            tags = subprocess.check_output(
                ["git", "tag", "--merged", "origin/main"], text=True
            ).splitlines()

            found_local = False
            for tag in tags:
                if tag == latest_local_tag:
                    found_local = True
                elif found_local:
                    tag_behind_count += 1
                    if tag == latest_remote_tag:
                        break


        # Check if there are new commits
        updates_available = latest_remote_tag != latest_local_tag

        return {
            "updates_available": updates_available,
            "tag_behind_count": tag_behind_count,  # Tags behind
            "latest_remote_tag": latest_remote_tag,
            "latest_local_tag": latest_local_tag,
        }
    except subprocess.CalledProcessError as e:
        print(f"Error checking Git updates: {e}")
        return {
            "updates_available": False,
            "tag_behind_count": 0,
            "latest_remote_tag": None,
            "latest_local_tag": None,
        }



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
    connect_to_serial(port, baudrate)

def parse_theta_rho_file(file_path):
    """
    Parse a theta-rho file and return a list of (theta, rho) pairs.
    Normalizes the list so the first theta is always 0.
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
                    coordinates.append((theta, rho))
                except ValueError:
                    print(f"Skipping invalid line: {line}")
                    continue
    except Exception as e:
        print(f"Error reading file: {e}")
        return coordinates

    # ---- Normalization Step ----
    if coordinates:
        # Take the first coordinate's theta
        first_theta = coordinates[0][0]

        # Shift all thetas so the first coordinate has theta=0
        normalized = []
        for (theta, rho) in coordinates:
            normalized.append((theta - first_theta, rho))

        # Replace original list with normalized data
        coordinates = normalized

    return coordinates

def send_coordinate_batch(ser, coordinates):
    """Send a batch of theta-rho pairs to the Arduino."""
    # print("Sending batch:", coordinates)
    batch_str = ";".join(f"{theta:.5f},{rho:.5f}" for theta, rho in coordinates) + ";\n"
    ser.write(batch_str.encode())

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

def wait_for_start_time(schedule_hours):
    """
    Keep checking every 30 seconds if the time is within the schedule to resume execution.
    """
    global pause_requested
    start_time, end_time = schedule_hours

    while pause_requested:
        now = datetime.now().time()
        if start_time <= now < end_time:
            print("Resuming execution: Within schedule.")
            pause_requested = False
            with pause_condition:
                pause_condition.notify_all()
            break  # Exit the loop once resumed
        else:
            time.sleep(30)  # Wait for 30 seconds before checking again

# Function to check schedule based on start and end time
def schedule_checker(schedule_hours):
    """
    Pauses/resumes execution based on a given time range.

    Parameters:
    - schedule_hours (tuple): (start_time, end_time) as `datetime.time` objects.
    """
    global pause_requested
    if not schedule_hours:
        return  # No scheduling restriction

    start_time, end_time = schedule_hours
    now = datetime.now().time()  # Get the current time as `datetime.time`

    # Check if we are currently within the scheduled time
    if start_time <= now < end_time:
        if pause_requested:
            print("Starting execution: Within schedule.")
        pause_requested = False  # Resume execution
        with pause_condition:
            pause_condition.notify_all()
    else:
        if not pause_requested:
            print("Pausing execution: Outside schedule.")
        pause_requested = True  # Pause execution

        # Start a background thread to periodically check for start time
        threading.Thread(target=wait_for_start_time, args=(schedule_hours,), daemon=True).start()

def run_theta_rho_file(file_path, schedule_hours=None):
    """Run a theta-rho file by sending data in optimized batches."""
    global stop_requested, current_playing_file, execution_progress
    stop_requested = False
    current_playing_file = file_path  # Track current playing file
    execution_progress = (0, 0)  # Reset progress

    coordinates = parse_theta_rho_file(file_path)
    total_coordinates = len(coordinates)

    if total_coordinates < 2:
        print("Not enough coordinates for interpolation.")
        current_playing_file = None  # Clear tracking if failed
        execution_progress = None
        return

    execution_progress = (0, total_coordinates)  # Update total coordinates
    batch_size = 10  # Smaller batches may smooth movement further

    for i in range(0, total_coordinates, batch_size):
        if stop_requested:
            print("Execution stopped by user after completing the current batch.")
            break

        with pause_condition:
            while pause_requested:
                print("Execution paused...")
                pause_condition.wait()  # This will block execution until notified

        batch = coordinates[i:i + batch_size]
        if i == 0:
            send_coordinate_batch(ser, batch)
            execution_progress = (i + batch_size, total_coordinates)  # Update progress
            continue

        while True:
            schedule_checker(schedule_hours)  # Check if within schedule
            with serial_lock:
                if ser.in_waiting > 0:
                    response = ser.readline().decode().strip()
                    if response == "R":
                        send_coordinate_batch(ser, batch)
                        execution_progress = (i + batch_size, total_coordinates)  # Update progress
                        break
                    else:
                        print(f"Arduino response: {response}")

    reset_theta()
    ser.write("FINISHED\n".encode())

    # Clear tracking variables when done
    current_playing_file = None
    execution_progress = None
    print("Pattern execution completed.")

def get_clear_pattern_file(pattern_name):
    """Return a .thr file path based on pattern_name."""
    if pattern_name == "random":
        # Randomly pick one of the three known patterns
        return random.choice(list(CLEAR_PATTERNS.values()))
    # If pattern_name is invalid or absent, default to 'clear_from_in'
    return CLEAR_PATTERNS.get(pattern_name, CLEAR_PATTERNS["clear_from_in"])

def run_theta_rho_files(
    file_paths,
    pause_time=0,
    clear_pattern=None,
    run_mode="single",
    shuffle=False,
    schedule_hours=None
):
    """
    Runs multiple .thr files in sequence with options for pausing, clearing, shuffling, and looping.

    Parameters:
    - file_paths (list): List of file paths to run.
    - pause_time (float): Seconds to pause between patterns.
    - clear_pattern (str): Specific clear pattern to run ("clear_in", "clear_out", "clear_sideway", or "random").
    - run_mode (str): "single" for one-time run or "indefinite" for looping.
    - shuffle (bool): Whether to shuffle the playlist before running.
    """
    global stop_requested
    global current_playlist
    global current_playing_index
    stop_requested = False  # Reset stop flag at the start

    if shuffle:
        random.shuffle(file_paths)
        print("Playlist shuffled.")

    current_playlist = file_paths

    while True:
        for idx, path in enumerate(file_paths):
            current_playing_index = idx
            schedule_checker(schedule_hours)
            if stop_requested:
                print("Execution stopped before starting next pattern.")
                return

            if clear_pattern:
                if stop_requested:
                    print("Execution stopped before running the next clear pattern.")
                    return

                # Determine the clear pattern to run
                clear_file_path = get_clear_pattern_file(clear_pattern)
                print(f"Running clear pattern: {clear_file_path}")
                run_theta_rho_file(clear_file_path, schedule_hours)

            if not stop_requested:
                # Run the main pattern
                print(f"Running pattern {idx + 1} of {len(file_paths)}: {path}")
                run_theta_rho_file(path, schedule_hours)

            if idx < len(file_paths) -1:
                if stop_requested:
                    print("Execution stopped before running the next clear pattern.")
                    return
                # Pause after each pattern if requested
                if pause_time > 0:
                    print(f"Pausing for {pause_time} seconds...")
                    time.sleep(pause_time)

        # After completing the playlist
        if run_mode == "indefinite":
            print("Playlist completed. Restarting as per 'indefinite' run mode.")
            if pause_time > 0:
                print(f"Pausing for {pause_time} seconds before restarting...")
                time.sleep(pause_time)
            if shuffle:
                random.shuffle(file_paths)
                print("Playlist reshuffled for the next loop.")
            continue
        else:
            print("Playlist completed.")
            break

    # Reset theta after execution or stopping
    reset_theta()
    ser.write("FINISHED\n".encode())
    print("All requested patterns completed (or stopped).")

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

# Flask API Endpoints
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
    pre_execution = request.json.get('pre_execution')  # 'clear_in', 'clear_out', 'clear_sideway', or 'none'

    if not file_name:
        return jsonify({'error': 'No file name provided'}), 400

    file_path = os.path.join(THETA_RHO_DIR, file_name)
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404

    try:
        # Build a list of files to run in sequence
        files_to_run = []

        if pre_execution == 'clear_in':
            files_to_run.append('./patterns/clear_from_in.thr')
        elif pre_execution == 'clear_out':
            files_to_run.append('./patterns/clear_from_out.thr')
        elif pre_execution == 'clear_sideway':
            files_to_run.append('./patterns/clear_sideway.thr')
        elif pre_execution == 'none':
            pass  # No pre-execution action required

        # Finally, add the main file
        files_to_run.append(file_path)

        # Run them in one shot using run_theta_rho_files (blocking call)
        threading.Thread(
            target=run_theta_rho_files,
            args=(files_to_run,),
            kwargs={
                'pause_time': 0,
                'clear_pattern': None
            }
        ).start()
        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/stop_execution', methods=['POST'])
def stop_execution():
    global pause_requested
    with pause_condition:
        pause_requested = False
        pause_condition.notify_all()
        
    global stop_requested, current_playing_index, current_playlist, is_clearing, current_playing_file, execution_progress
    stop_requested = True
    current_playing_index = None
    current_playlist = None
    is_clearing = False
    current_playing_file = None
    execution_progress = None

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
        coordinates = parse_theta_rho_file(file_path)
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

@app.route('/pause_execution', methods=['POST'])
def pause_execution():
    """Pause the current execution."""
    global pause_requested
    with pause_condition:
        pause_requested = True
    return jsonify({'success': True, 'message': 'Execution paused'})

@app.route('/status', methods=['GET'])
def get_status():
    """Returns the current status of the sand table."""
    global is_clearing
    if current_playing_file in CLEAR_PATTERNS.values():
        is_clearing = True
    else:
        is_clearing = False

    return jsonify({
        "ser_port": ser_port,
        "stop_requested": stop_requested,
        "pause_requested": pause_requested,
        "current_playing_file": current_playing_file,
        "execution_progress": execution_progress,
        "current_playing_index": current_playing_index,
        "current_playlist": current_playlist,
        "is_clearing": is_clearing
    })

@app.route('/resume_execution', methods=['POST'])
def resume_execution():
    """Resume execution after pausing."""
    global pause_requested
    with pause_condition:
        pause_requested = False
        pause_condition.notify_all()  # Unblock the waiting thread
    return jsonify({'success': True, 'message': 'Execution resumed'})

def load_playlists():
    """
    Load the entire playlists dictionary from the JSON file.
    Returns something like: {
        "My Playlist": ["file1.thr", "file2.thr"],
        "Another": ["x.thr"]
    }
    """
    with open(PLAYLISTS_FILE, "r") as f:
        return json.load(f)

def save_playlists(playlists_dict):
    """
    Save the entire playlists dictionary back to the JSON file.
    """
    with open(PLAYLISTS_FILE, "w") as f:
        json.dump(playlists_dict, f, indent=2)

@app.route("/list_all_playlists", methods=["GET"])
def list_all_playlists():
    """
    Returns a list of all playlist names.
    Example return: ["My Playlist", "Another Playlist"]
    """
    playlists_dict = load_playlists()
    playlist_names = list(playlists_dict.keys())
    return jsonify(playlist_names)

@app.route("/get_playlist", methods=["GET"])
def get_playlist():
    """
    GET /get_playlist?name=My%20Playlist
    Returns: { "name": "My Playlist", "files": [... ] }
    """
    playlist_name = request.args.get("name", "")
    if not playlist_name:
        return jsonify({"error": "Missing playlist 'name' parameter"}), 400

    playlists_dict = load_playlists()
    if playlist_name not in playlists_dict:
        return jsonify({"error": f"Playlist '{playlist_name}' not found"}), 404

    files = playlists_dict[playlist_name]  # e.g. ["file1.thr", "file2.thr"]
    return jsonify({
        "name": playlist_name,
        "files": files
    })

@app.route("/create_playlist", methods=["POST"])
def create_playlist():
    """
    POST /create_playlist
    Body: { "name": "My Playlist", "files": ["file1.thr", "file2.thr"] }
    Creates or overwrites a playlist with the given name.
    """
    data = request.get_json()
    if not data or "name" not in data or "files" not in data:
        return jsonify({"success": False, "error": "Playlist 'name' and 'files' are required"}), 400

    playlist_name = data["name"]
    files = data["files"]

    # Load all playlists
    playlists_dict = load_playlists()

    # Overwrite or create new
    playlists_dict[playlist_name] = files

    # Save changes
    save_playlists(playlists_dict)

    return jsonify({
        "success": True,
        "message": f"Playlist '{playlist_name}' created/updated"
    })

@app.route("/modify_playlist", methods=["POST"])
def modify_playlist():
    """
    POST /modify_playlist
    Body: { "name": "My Playlist", "files": ["file1.thr", "file2.thr"] }
    Updates (or creates) the existing playlist with a new file list.
    You can 404 if you only want to allow modifications to existing playlists.
    """
    data = request.get_json()
    if not data or "name" not in data or "files" not in data:
        return jsonify({"success": False, "error": "Playlist 'name' and 'files' are required"}), 400

    playlist_name = data["name"]
    files = data["files"]

    # Load all playlists
    playlists_dict = load_playlists()

    # Optional: If you want to disallow creating a new playlist here:
    # if playlist_name not in playlists_dict:
    #     return jsonify({"success": False, "error": f"Playlist '{playlist_name}' not found"}), 404

    # Overwrite or create new
    playlists_dict[playlist_name] = files

    # Save
    save_playlists(playlists_dict)

    return jsonify({"success": True, "message": f"Playlist '{playlist_name}' updated"})

@app.route("/delete_playlist", methods=["DELETE"])
def delete_playlist():
    """
    DELETE /delete_playlist
    Body: { "name": "My Playlist" }
    Removes the playlist from the single JSON file.
    """
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"success": False, "error": "Missing 'name' field"}), 400

    playlist_name = data["name"]

    playlists_dict = load_playlists()
    if playlist_name not in playlists_dict:
        return jsonify({"success": False, "error": f"Playlist '{playlist_name}' not found"}), 404

    # Remove from dict
    del playlists_dict[playlist_name]
    save_playlists(playlists_dict)

    return jsonify({
        "success": True,
        "message": f"Playlist '{playlist_name}' deleted"
    })

@app.route('/add_to_playlist', methods=['POST'])
def add_to_playlist():
    data = request.json
    playlist_name = data.get('playlist_name')
    pattern = data.get('pattern')

    # Load existing playlists
    with open('playlists.json', 'r') as f:
        playlists = json.load(f)

    # Add pattern to the selected playlist
    if playlist_name in playlists:
        playlists[playlist_name].append(pattern)
        with open('playlists.json', 'w') as f:
            json.dump(playlists, f)
        return jsonify(success=True)
    else:
        return jsonify(success=False, error='Playlist not found'), 404

@app.route("/run_playlist", methods=["POST"])
def run_playlist():
    """
    POST /run_playlist
    Body (JSON):
    {
        "playlist_name": "My Playlist",
        "pause_time": 1.0,                # Optional: seconds to pause between patterns
        "clear_pattern": "random",         # Optional: "clear_in", "clear_out", "clear_sideway", or "random"
        "run_mode": "single",              # 'single' or 'indefinite'
        "shuffle": True                    # true or false
        "start_time": ""
        "end_time": ""
    }
    """
    data = request.get_json()

    # Validate input
    if not data or "playlist_name" not in data:
        return jsonify({"success": False, "error": "Missing 'playlist_name' field"}), 400

    playlist_name = data["playlist_name"]
    pause_time = data.get("pause_time", 0)
    clear_pattern = data.get("clear_pattern", None)
    run_mode = data.get("run_mode", "single")  # Default to 'single' run
    shuffle = data.get("shuffle", False)       # Default to no shuffle
    start_time = data.get("start_time", None)
    end_time = data.get("end_time", None)

    # Validate pause_time
    if not isinstance(pause_time, (int, float)) or pause_time < 0:
        return jsonify({"success": False, "error": "'pause_time' must be a non-negative number"}), 400

    # Validate clear_pattern
    valid_patterns = ["clear_in", "clear_out", "clear_sideway", "random"]
    if clear_pattern not in valid_patterns:
        clear_pattern = None

    # Validate run_mode
    if run_mode not in ["single", "indefinite"]:
        return jsonify({"success": False, "error": "'run_mode' must be 'single' or 'indefinite'"}), 400

    # Validate shuffle
    if not isinstance(shuffle, bool):
        return jsonify({"success": False, "error": "'shuffle' must be a boolean value"}), 400

    schedule_hours = None
    if start_time and end_time:
        try:
            # Convert HH:MM to datetime.time objects
            start_time_obj = datetime.strptime(start_time, "%H:%M").time()
            end_time_obj = datetime.strptime(end_time, "%H:%M").time()

            # Ensure start_time is before end_time
            if start_time_obj >= end_time_obj:
                return jsonify({"success": False, "error": "'start_time' must be earlier than 'end_time'"}), 400

            # Create schedule tuple with full time
            schedule_hours = (start_time_obj, end_time_obj)
        except ValueError:
            return jsonify({"success": False, "error": "Invalid time format. Use HH:MM (e.g., '09:30')"}), 400


    # Load playlists
    playlists = load_playlists()

    if playlist_name not in playlists:
        return jsonify({"success": False, "error": f"Playlist '{playlist_name}' not found"}), 404

    file_paths = playlists[playlist_name]
    file_paths = [os.path.join(THETA_RHO_DIR, file) for file in file_paths]

    if not file_paths:
        return jsonify({"success": False, "error": f"Playlist '{playlist_name}' is empty"}), 400

    # Start the playlist execution in a separate thread
    try:
        threading.Thread(
            target=run_theta_rho_files,
            args=(file_paths,),
            kwargs={
                'pause_time': pause_time,
                'clear_pattern': clear_pattern,
                'run_mode': run_mode,
                'shuffle': shuffle,
                'schedule_hours': schedule_hours
            },
            daemon=True  # Daemonize thread to exit with the main program
        ).start()
        return jsonify({"success": True, "message": f"Playlist '{playlist_name}' is now running."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

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
        command = f"SET_SPEEzD {speed}"
        send_command(command)
        return jsonify({"success": True, "speed": speed})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/get_firmware_info', methods=['GET', 'POST'])
def get_firmware_info():
    """
    Compare the installed firmware version and motor type with the one in the .ino file.
    """
    global firmware_version, arduino_driver_type, ser

    if ser is None or not ser.is_open:
        return jsonify({"success": False, "error": "Arduino not connected or serial port not open"}), 400

    try:
        if request.method == "GET":
            # Attempt to retrieve installed firmware details from the Arduino
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            ser.write(b"GET_VERSION\n")
            time.sleep(0.5)

            installed_version = firmware_version
            installed_type = arduino_driver_type

            # If Arduino provides valid details, proceed with comparison
            if installed_version != 'Unknown' and installed_type != 'Unknown':
                ino_path = MOTOR_TYPE_MAPPING.get(installed_type)
                firmware_details = get_ino_firmware_details(ino_path)

                if not firmware_details or not firmware_details.get("version") or not firmware_details.get("motorType"):
                    return jsonify({"success": False, "error": "Failed to retrieve .ino firmware details"}), 500

                update_available = (
                    installed_version != firmware_details["version"] or
                    installed_type != firmware_details["motorType"]
                )

                return jsonify({
                    "success": True,
                    "installedVersion": installed_version,
                    "installedType": installed_type,
                    "inoVersion": firmware_details["version"],
                    "inoType": firmware_details["motorType"],
                    "updateAvailable": update_available
                })

            # If Arduino details are unknown, indicate the need for POST
            return jsonify({
                "success": True,
                "installedVersion": installed_version,
                "installedType": installed_type,
                "updateAvailable": False
            })

        elif request.method == "POST":
            motor_type = request.json.get("motorType", None)
            if not motor_type or motor_type not in MOTOR_TYPE_MAPPING:
                return jsonify({
                    "success": False,
                    "error": "Invalid or missing motor type"
                }), 400

            # Fetch firmware details for the given motor type
            ino_path = MOTOR_TYPE_MAPPING[motor_type]
            firmware_details = get_ino_firmware_details(ino_path)

            if not firmware_details:
                return jsonify({
                    "success": False,
                    "error": "Failed to retrieve .ino firmware details"
                }), 500

            return jsonify({
                "success": True,
                "installedVersion": 'Unknown',
                "installedType": motor_type,
                "inoVersion": firmware_details["version"],
                "inoType": firmware_details["motorType"],
                "updateAvailable": True
            })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/flash_firmware', methods=['POST'])
def flash_firmware():
    """
    Compile and flash the firmware to the connected Arduino.
    """
    global ser_port

    # Ensure the Arduino is connected
    if ser_port is None or ser is None or not ser.is_open:
        return jsonify({"success": False, "error": "No Arduino connected or connection lost"}), 400

    build_dir = "/tmp/arduino_build"  # Temporary build directory

    try:
        data = request.json
        motor_type = data.get("motorType", None)

        # Validate motor type
        if not motor_type or motor_type not in MOTOR_TYPE_MAPPING:
            return jsonify({"success": False, "error": "Invalid or missing motor type"}), 400

        # Get the .ino file path based on the motor type
        ino_file_path = MOTOR_TYPE_MAPPING[motor_type]
        ino_file_name = os.path.basename(ino_file_path)

        # Install required libraries
        required_libraries = ["AccelStepper"]  # AccelStepper includes MultiStepper
        for library in required_libraries:
            library_install_command = ["arduino-cli", "lib", "install", library]
            install_process = subprocess.run(library_install_command, capture_output=True, text=True)
            if install_process.returncode != 0:
                return jsonify({
                    "success": False,
                    "error": f"Library installation failed for {library}: {install_process.stderr}"
                }), 500

        # Step 1: Compile the .ino file to a .hex file
        compile_command = [
            "arduino-cli",
            "compile",
            "--fqbn", "arduino:avr:uno",  # Use the detected FQBN
            "--output-dir", build_dir,
            ino_file_path
        ]

        compile_process = subprocess.run(compile_command, capture_output=True, text=True)
        if compile_process.returncode != 0:
            return jsonify({
                "success": False,
                "error": compile_process.stderr
            }), 500

        # Step 2: Flash the .hex file to the Arduino
        hex_file_path = os.path.join(build_dir, ino_file_name+".hex")
        flash_command = [
            "avrdude",
            "-v",
            "-c", "arduino",  # Programmer type
            "-p", "atmega328p",  # Microcontroller type
            "-P", ser_port,  # Use the dynamic serial port
            "-b", "115200",  # Baud rate
            "-D",
            "-U", f"flash:w:{hex_file_path}:i"  # Flash memory write command
        ]

        flash_process = subprocess.run(flash_command, capture_output=True, text=True)
        if flash_process.returncode != 0:
            return jsonify({
                "success": False,
                "error": flash_process.stderr
            }), 500

        return jsonify({"success": True, "message": "Firmware flashed successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        # Clean up temporary files
        if os.path.exists(build_dir):
            for file in os.listdir(build_dir):
                os.remove(os.path.join(build_dir, file))
            os.rmdir(build_dir)

@app.route('/check_software_update', methods=['GET'])
def check_updates():
    update_info = check_git_updates()
    return jsonify(update_info)

@app.route('/update_software', methods=['POST'])
def update_software():
    error_log = []

    def run_command(command, error_message):
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as e:
            print(f"{error_message}: {e}")
            error_log.append(error_message)

    # Fetch the latest version tag from remote
    try:
        subprocess.run(["git", "fetch", "--tags"], check=True)
        latest_remote_tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0", "origin/main"]
        ).strip().decode()
    except subprocess.CalledProcessError as e:
        error_log.append(f"Failed to fetch tags or get latest remote tag: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to fetch tags or determine the latest version.",
            "details": error_log
        }), 500

    # Checkout the latest tag
    run_command(["git", "checkout", latest_remote_tag, '--force'], f"Failed to checkout version {latest_remote_tag}")

    # Restart Docker containers
    run_command(["docker", "compose", "up", "-d"], "Failed to restart Docker containers")

    # Check if the update was successful
    update_status = check_git_updates()

    if (
        update_status["updates_available"] is False
        and update_status["latest_local_tag"] == update_status["latest_remote_tag"]
    ):
        # Update was successful
        return jsonify({"success": True})
    else:
        # Update failed; include the errors in the response
        return jsonify({
            "success": False,
            "error": "Update incomplete",
            "details": error_log
        }), 500
if __name__ == '__main__':
    # Auto-connect to serial
    connect_to_serial()
    app.run(debug=False, host='0.0.0.0', port=8080)
