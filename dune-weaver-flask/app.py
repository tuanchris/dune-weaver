from flask import Flask, request, jsonify, render_template, send_from_directory
import os
import threading
from datetime import datetime
import logging

from modules.serial.serial_manager import (
    list_serial_ports, connect_to_serial, disconnect_serial, 
    restart_serial, get_serial_status, get_device_info,
    send_coordinate_batch
)
from modules.firmware.firmware_manager import (
    get_firmware_info, flash_firmware, check_git_updates,
    update_software
)
from modules.core.pattern_manager import (
    THETA_RHO_DIR, parse_theta_rho_file, run_theta_rho_file,
    run_theta_rho_files, get_execution_status, stop_execution,
    pause_execution, resume_execution
)
from modules.core.playlist_manager import (
    list_all_playlists, get_playlist, create_playlist,
    modify_playlist, delete_playlist, add_to_playlist
)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Ensure the patterns directory exists
os.makedirs(THETA_RHO_DIR, exist_ok=True)

# API Routes
@app.route('/')
def index():
    return render_template('index.html')

# Serial Routes
@app.route('/list_serial_ports', methods=['GET'])
def api_list_ports():
    return jsonify(list_serial_ports())

@app.route('/connect_serial', methods=['POST'])
def api_connect_serial():
    port = request.json.get('port')
    if not port:
        return jsonify({'error': 'No port provided'}), 400

    try:
        success = connect_to_serial(port)
        return jsonify({'success': success})
    except Exception as e:
        app.logger.error(f"Error connecting to serial port: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/disconnect_serial', methods=['POST'])
def api_disconnect():
    try:
        disconnect_serial()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/restart_serial', methods=['POST'])
def api_restart():
    port = request.json.get('port')
    if not port:
        return jsonify({'error': 'No port provided'}), 400

    try:
        success = restart_serial(port)
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/serial_status', methods=['GET'])
def api_serial_status():
    return jsonify(get_serial_status())

# Pattern Routes
@app.route('/list_theta_rho_files', methods=['GET'])
def api_list_theta_rho_files():
    files = []
    for root, _, filenames in os.walk(THETA_RHO_DIR):
        for file in filenames:
            relative_path = os.path.relpath(os.path.join(root, file), THETA_RHO_DIR)
            files.append(relative_path)
    return jsonify(sorted(files))

@app.route('/upload_theta_rho', methods=['POST'])
def api_upload_theta_rho():
    custom_patterns_dir = os.path.join(THETA_RHO_DIR, 'custom_patterns')
    os.makedirs(custom_patterns_dir, exist_ok=True)

    file = request.files['file']
    if file:
        file.save(os.path.join(custom_patterns_dir, file.filename))
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/run_theta_rho', methods=['POST'])
def api_run_theta_rho():
    file_name = request.json.get('file_name')
    pre_execution = request.json.get('pre_execution')

    if not file_name:
        return jsonify({'error': 'No file name provided'}), 400

    file_path = os.path.join(THETA_RHO_DIR, file_name)
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404

    try:
        files_to_run = []
        if pre_execution in ['clear_in', 'clear_out', 'clear_sideway']:
            files_to_run.append(f'./patterns/clear_from_{pre_execution.split("_")[1]}.thr')
        files_to_run.append(file_path)

        threading.Thread(
            target=run_theta_rho_files,
            args=(files_to_run,),
            kwargs={'pause_time': 0, 'clear_pattern': None}
        ).start()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/preview_thr', methods=['POST'])
def api_preview_thr():
    file_name = request.json.get('file_name')
    if not file_name:
        return jsonify({'error': 'No file name provided'}), 400

    file_path = os.path.join(THETA_RHO_DIR, file_name)
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404

    try:
        coordinates = parse_theta_rho_file(file_path)
        return jsonify({'success': True, 'coordinates': coordinates})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/send_coordinate', methods=['POST'])
def api_send_coordinate():
    try:
        data = request.json
        theta = data.get('theta')
        rho = data.get('rho')

        if theta is None or rho is None:
            return jsonify({"success": False, "error": "Theta and Rho are required"}), 400

        send_coordinate_batch([(theta, rho)])
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# Playlist Routes
@app.route("/list_all_playlists", methods=["GET"])
def api_list_all_playlists():
    playlist_names = list_all_playlists()
    return jsonify(playlist_names)

@app.route("/get_playlist", methods=["GET"])
def api_get_playlist():
    playlist_name = request.args.get("name", "")
    if not playlist_name:
        return jsonify({"error": "Missing playlist 'name' parameter"}), 400

    playlist = get_playlist(playlist_name)
    if not playlist:
        return jsonify({"error": f"Playlist '{playlist_name}' not found"}), 404

    return jsonify(playlist)

@app.route("/create_playlist", methods=["POST"])
def api_create_playlist():
    data = request.get_json()
    if not data or "name" not in data or "files" not in data:
        return jsonify({"success": False, "error": "Playlist 'name' and 'files' are required"}), 400

    success = create_playlist(data["name"], data["files"])
    return jsonify({
        "success": success,
        "message": f"Playlist '{data['name']}' created/updated"
    })

@app.route("/modify_playlist", methods=["POST"])
def api_modify_playlist():
    data = request.get_json()
    if not data or "name" not in data or "files" not in data:
        return jsonify({"success": False, "error": "Playlist 'name' and 'files' are required"}), 400

    success = modify_playlist(data["name"], data["files"])
    return jsonify({
        "success": success,
        "message": f"Playlist '{data['name']}' updated"
    })

@app.route("/delete_playlist", methods=["DELETE"])
def api_delete_playlist():
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"success": False, "error": "Missing 'name' field"}), 400

    success = delete_playlist(data["name"])
    if not success:
        return jsonify({"success": False, "error": f"Playlist '{data['name']}' not found"}), 404

    return jsonify({
        "success": True,
        "message": f"Playlist '{data['name']}' deleted"
    })

@app.route('/add_to_playlist', methods=['POST'])
def api_add_to_playlist():
    data = request.json
    playlist_name = data.get('playlist_name')
    pattern = data.get('pattern')

    success = add_to_playlist(playlist_name, pattern)
    if success:
        return jsonify(success=True)
    else:
        return jsonify(success=False, error='Playlist not found'), 404

@app.route("/run_playlist", methods=["POST"])
def api_run_playlist():
    data = request.get_json()
    if not data or "playlist_name" not in data:
        return jsonify({"success": False, "error": "Missing 'playlist_name' field"}), 400

    playlist = get_playlist(data["playlist_name"])
    if not playlist:
        return jsonify({"success": False, "error": f"Playlist '{data['playlist_name']}' not found"}), 404

    schedule_hours = None
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    if start_time and end_time:
        try:
            start_time_obj = datetime.strptime(start_time, "%H:%M").time()
            end_time_obj = datetime.strptime(end_time, "%H:%M").time()
            if start_time_obj >= end_time_obj:
                return jsonify({"success": False, "error": "'start_time' must be earlier than 'end_time'"}), 400
            schedule_hours = (start_time_obj, end_time_obj)
        except ValueError:
            return jsonify({"success": False, "error": "Invalid time format. Use HH:MM (e.g., '09:30')"}), 400

    file_paths = [os.path.join(THETA_RHO_DIR, file) for file in playlist["files"]]
    if not file_paths:
        return jsonify({"success": False, "error": f"Playlist '{data['playlist_name']}' is empty"}), 400

    try:
        threading.Thread(
            target=run_theta_rho_files,
            args=(file_paths,),
            kwargs={
                'pause_time': data.get("pause_time", 0),
                'clear_pattern': data.get("clear_pattern"),
                'run_mode': data.get("run_mode", "single"),
                'shuffle': data.get("shuffle", False),
                'schedule_hours': schedule_hours
            },
            daemon=True
        ).start()
        return jsonify({"success": True, "message": f"Playlist '{data['playlist_name']}' is now running."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# Execution Control Routes
@app.route('/stop_execution', methods=['POST'])
def api_stop_execution():
    stop_execution()
    return jsonify({'success': True})

@app.route('/pause_execution', methods=['POST'])
def api_pause_execution():
    pause_execution()
    return jsonify({'success': True, 'message': 'Execution paused'})

@app.route('/resume_execution', methods=['POST'])
def api_resume_execution():
    resume_execution()
    return jsonify({'success': True, 'message': 'Execution resumed'})

@app.route('/status', methods=['GET'])
def api_get_status():
    return jsonify(get_execution_status())

# Firmware Routes
@app.route('/get_firmware_info', methods=['GET', 'POST'])
def api_get_firmware_info():
    device_info = get_device_info()
    if request.method == "POST":
        motor_type = request.json.get("motorType")
        info, error = get_firmware_info(
            device_info['firmware_version'],
            device_info['driver_type'],
            motor_type
        )
    else:
        info, error = get_firmware_info(
            device_info['firmware_version'],
            device_info['driver_type']
        )

    if error:
        return jsonify({"success": False, "error": error}), 500
    return jsonify(info)

@app.route('/flash_firmware', methods=['POST'])
def api_flash_firmware():
    status = get_serial_status()
    if not status['connected']:
        return jsonify({"success": False, "error": "No Arduino connected or connection lost"}), 400

    motor_type = request.json.get("motorType")
    success, message = flash_firmware(status['port'], motor_type)
    
    if success:
        return jsonify({"success": True, "message": message})
    
    app.logger.error(message)
    return jsonify({"success": False, "error": message}), 500

@app.route('/check_software_update', methods=['GET'])
def api_check_updates():
    update_info = check_git_updates()
    return jsonify(update_info)

@app.route('/update_software', methods=['POST'])
def api_update_software():
    success, message, error_log = update_software()
    if success:
        return jsonify({"success": True})
        return jsonify({
            "success": False,
        "error": message,
            "details": error_log
        }), 500

# File Management Routes
@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    return send_from_directory(THETA_RHO_DIR, filename)

@app.route('/delete_theta_rho_file', methods=['POST'])
def api_delete_theta_rho_file():
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

if __name__ == '__main__':
    # Auto-connect to serial
    connect_to_serial()
    app.run(debug=True, host='0.0.0.0', port=8080)
