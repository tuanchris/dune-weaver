from flask import Flask, request, jsonify, render_template, send_from_directory
import atexit
import os
import logging
from datetime import datetime
from .modules.connection import connection_manager
from dune_weaver_flask.modules.core import pattern_manager
from dune_weaver_flask.modules.core import playlist_manager
from .modules.update import update_manager
from dune_weaver_flask.modules.core.state import state
from dune_weaver_flask.modules import mqtt


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        # disable file logging for now, to not gobble up resources
        # logging.FileHandler('dune_weaver.log')
    ]
)

logger = logging.getLogger(__name__)

app = Flask(__name__)

# Flask API Endpoints
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/list_serial_ports', methods=['GET'])
def list_ports():
    logger.debug("Listing available serial ports")
    return jsonify(connection_manager.list_serial_ports())

@app.route('/connect', methods=['POST'])
def connect():
    port = request.json.get('port')
    if not port:
        state.conn = WebSocketConnection('ws://fluidnc.local:81')
        logger.info(f'Successfully connected to websocket ws://fluidnc.local:81')
        return jsonify({'success': True})

    try:
        state.conn = SerialConnection(port)
        logger.info(f'Successfully connected to serial port {port}')
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f'Failed to connect to serial port {port}: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/disconnect', methods=['POST'])
def disconnect():
    try:
        state.conn.close()
        logger.info('Successfully disconnected from serial port')
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f'Failed to disconnect serial: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/restart_connection', methods=['POST'])
def restart():
    port = request.json.get('port')
    if not port:
        logger.warning("Restart serial request received without port")
        return jsonify({'error': 'No port provided'}), 400

    try:
        logger.info(f"Restarting connection on port {port}")
        connection_manager.restart_connection()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Failed to restart serial on port {port}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/list_theta_rho_files', methods=['GET'])
def list_theta_rho_files():
    logger.debug("Listing theta-rho files")
    files = pattern_manager.list_theta_rho_files()
    return jsonify(sorted(files))

@app.route('/upload_theta_rho', methods=['POST'])
def upload_theta_rho():
    custom_patterns_dir = os.path.join(pattern_manager.THETA_RHO_DIR, 'custom_patterns')
    os.makedirs(custom_patterns_dir, exist_ok=True)
    logger.debug(f'Ensuring custom patterns directory exists: {custom_patterns_dir}')

    file = request.files['file']
    if file:
        file_path = os.path.join(custom_patterns_dir, file.filename)
        file.save(file_path)
        logger.info(f'Successfully uploaded theta-rho file: {file.filename}')
        return jsonify({'success': True})
    
    logger.warning('Upload theta-rho request received without file')
    return jsonify({'success': False})

@app.route('/run_theta_rho', methods=['POST'])
def run_theta_rho():
    file_name = request.json.get('file_name')
    pre_execution = request.json.get('pre_execution')

    if not file_name:
        logger.warning('Run theta-rho request received without file name')
        return jsonify({'error': 'No file name provided'}), 400

    file_path = os.path.join(pattern_manager.THETA_RHO_DIR, file_name)
    if not os.path.exists(file_path):
        logger.error(f'Theta-rho file not found: {file_path}')
        return jsonify({'error': 'File not found'}), 404

    try:
        files_to_run = [file_path]
        logger.info(f'Running theta-rho file: {file_name} with pre_execution={pre_execution}')
        pattern_manager.run_theta_rho_files(files_to_run, clear_pattern=pre_execution)
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f'Failed to run theta-rho file {file_name}: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/stop_execution', methods=['POST'])
def stop_execution():
    pattern_manager.stop_actions()
    return jsonify({'success': True})

@app.route('/send_home', methods=['POST'])
def send_home():
    try:
        connection_manager.home()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Failed to send home command: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/run_theta_rho_file/<file_name>', methods=['POST'])
def run_specific_theta_rho_file(file_name):
    file_path = os.path.join(pattern_manager.THETA_RHO_DIR, file_name)
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404

    pattern_manager.run_theta_rho_file(file_path)
    return jsonify({'success': True})

@app.route('/delete_theta_rho_file', methods=['POST'])
def delete_theta_rho_file():
    file_name = request.json.get('file_name')
    if not file_name:
        logger.warning("Delete theta-rho file request received without filename")
        return jsonify({"success": False, "error": "No file name provided"}), 400

    file_path = os.path.join(pattern_manager.THETA_RHO_DIR, file_name)
    if not os.path.exists(file_path):
        logger.error(f"Attempted to delete non-existent file: {file_path}")
        return jsonify({"success": False, "error": "File not found"}), 404

    try:
        os.remove(file_path)
        logger.info(f"Successfully deleted theta-rho file: {file_name}")
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Failed to delete theta-rho file {file_name}: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/move_to_center', methods=['POST'])
def move_to_center():
    global current_theta
    try:
        if not state.conn.is_connected():
            logger.warning("Attempted to move to center without connection")
            return jsonify({"success": False, "error": "Connection not established"}), 400

        logger.info("Moving device to center position")
        pattern_manager.reset_theta()
        pattern_manager.move_polar(0, 0)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Failed to move to center: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/move_to_perimeter', methods=['POST'])
def move_to_perimeter():
    global current_theta
    try:
        if not state.conn.is_connected():
            logger.warning("Attempted to move to perimeter without connection")
            return jsonify({"success": False, "error": "Connection not established"}), 400
        pattern_manager.reset_theta()
        pattern_manager.move_polar(0,1)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Failed to move to perimeter: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/preview_thr', methods=['POST'])
def preview_thr():
    file_name = request.json.get('file_name')
    if not file_name:
        logger.warning("Preview theta-rho request received without filename")
        return jsonify({'error': 'No file name provided'}), 400

    file_path = os.path.join(pattern_manager.THETA_RHO_DIR, file_name)
    if not os.path.exists(file_path):
        logger.error(f"Attempted to preview non-existent file: {file_path}")
        return jsonify({'error': 'File not found'}), 404

    try:
        coordinates = pattern_manager.parse_theta_rho_file(file_path)
        return jsonify({'success': True, 'coordinates': coordinates})
    except Exception as e:
        logger.error(f"Failed to generate preview for {file_name}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/send_coordinate', methods=['POST'])
def send_coordinate():
    if not state.conn.is_connected():
        logger.warning("Attempted to send coordinate without connection")
        return jsonify({"success": False, "error": "connection not established"}), 400

    try:
        data = request.json
        theta = data.get('theta')
        rho = data.get('rho')

        if theta is None or rho is None:
            logger.warning("Send coordinate request missing theta or rho values")
            return jsonify({"success": False, "error": "Theta and Rho are required"}), 400

        logger.debug(f"Sending coordinate: theta={theta}, rho={rho}")
        pattern_manager.move_polar(theta, rho)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Failed to send coordinate: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    return send_from_directory(pattern_manager.THETA_RHO_DIR, filename)

@app.route('/serial_status', methods=['GET'])
def serial_status():
    connected = state.conn.is_connected()
    port = state.port
    logger.debug(f"Serial status check - connected: {connected}, port: {port}")
    return jsonify({
        'connected': connected,
        'port': port
    })

@app.route('/pause_execution', methods=['POST'])
def pause_execution():
    if pattern_manager.pause_execution():
        return jsonify({'success': True, 'message': 'Execution paused'})

@app.route('/status', methods=['GET'])
def get_status():
    return jsonify(pattern_manager.get_status())

@app.route('/resume_execution', methods=['POST'])
def resume_execution():
    if pattern_manager.resume_execution():
        return jsonify({'success': True, 'message': 'Execution resumed'})

# Playlist endpoints
@app.route("/list_all_playlists", methods=["GET"])
def list_all_playlists():
    playlist_names = playlist_manager.list_all_playlists()
    return jsonify(playlist_names)

@app.route("/get_playlist", methods=["GET"])
def get_playlist():
    playlist_name = request.args.get("name", "")
    if not playlist_name:
        return jsonify({"error": "Missing playlist 'name' parameter"}), 400

    playlist = playlist_manager.get_playlist(playlist_name)
    if not playlist:
        return jsonify({"error": f"Playlist '{playlist_name}' not found"}), 404

    return jsonify(playlist)

@app.route("/create_playlist", methods=["POST"])
def create_playlist():
    data = request.get_json()
    if not data or "name" not in data or "files" not in data:
        return jsonify({"success": False, "error": "Playlist 'name' and 'files' are required"}), 400

    success = playlist_manager.create_playlist(data["name"], data["files"])
    return jsonify({
        "success": success,
        "message": f"Playlist '{data['name']}' created/updated"
    })

@app.route("/modify_playlist", methods=["POST"])
def modify_playlist():
    data = request.get_json()
    if not data or "name" not in data or "files" not in data:
        return jsonify({"success": False, "error": "Playlist 'name' and 'files' are required"}), 400

    success = playlist_manager.modify_playlist(data["name"], data["files"])
    return jsonify({"success": success, "message": f"Playlist '{data['name']}' updated"})

@app.route("/delete_playlist", methods=["DELETE"])
def delete_playlist():
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"success": False, "error": "Missing 'name' field"}), 400

    success = playlist_manager.delete_playlist(data["name"])
    if not success:
        return jsonify({"success": False, "error": f"Playlist '{data['name']}' not found"}), 404

    return jsonify({
        "success": True,
        "message": f"Playlist '{data['name']}' deleted"
    })

@app.route('/add_to_playlist', methods=['POST'])
def add_to_playlist():
    data = request.json
    playlist_name = data.get('playlist_name')
    pattern = data.get('pattern')

    success = playlist_manager.add_to_playlist(playlist_name, pattern)
    if not success:
        return jsonify(success=False, error='Playlist not found'), 404
    return jsonify(success=True)

@app.route("/run_playlist", methods=["POST"])
def run_playlist():
    data = request.get_json()
    if not data or "playlist_name" not in data:
        logger.warning("Run playlist request received without playlist name")
        return jsonify({"success": False, "error": "Missing 'playlist_name' field"}), 400

    playlist_name = data["playlist_name"]
    pause_time = data.get("pause_time", 0)
    clear_pattern = data.get("clear_pattern", None)
    run_mode = data.get("run_mode", "single")
    shuffle = data.get("shuffle", False)
    
    schedule_hours = None
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    
    if start_time and end_time:
        try:
            start_time_obj = datetime.strptime(start_time, "%H:%M").time()
            end_time_obj = datetime.strptime(end_time, "%H:%M").time()
            if start_time_obj >= end_time_obj:
                logger.error(f"Invalid schedule times: start_time {start_time} >= end_time {end_time}")
                return jsonify({"success": False, "error": "'start_time' must be earlier than 'end_time'"}), 400
            schedule_hours = (start_time_obj, end_time_obj)
            logger.info(f"Playlist {playlist_name} scheduled to run between {start_time} and {end_time}")
        except ValueError:
            logger.error(f"Invalid time format provided: start_time={start_time}, end_time={end_time}")
            return jsonify({"success": False, "error": "Invalid time format. Use HH:MM (e.g., '09:30')"}), 400

    logger.info(f"Starting playlist '{playlist_name}' with mode={run_mode}, shuffle={shuffle}")
    success, message = playlist_manager.run_playlist(
        playlist_name,
        pause_time=pause_time,
        clear_pattern=clear_pattern,
        run_mode=run_mode,
        shuffle=shuffle,
        schedule_hours=schedule_hours
    )

    if not success:
        logger.error(f"Failed to run playlist '{playlist_name}': {message}")
        return jsonify({"success": False, "error": message}), 500
    
    return jsonify({"success": True, "message": message})

# Firmware endpoints
@app.route('/set_speed', methods=['POST'])
def set_speed():
    try:
        data = request.json
        new_speed = data.get('speed')

        if new_speed is None:
            logger.warning("Set speed request received without speed value")
            return jsonify({"success": False, "error": "Speed is required"}), 400

        if not isinstance(new_speed, (int, float)) or new_speed <= 0:
            logger.warning(f"Invalid speed value received: {new_speed}")
            return jsonify({"success": False, "error": "Invalid speed value"}), 400
        state.speed = new_speed
        return jsonify({"success": True, "speed": new_speed})
    except Exception as e:
        logger.error(f"Failed to set speed: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/check_software_update', methods=['GET'])
def check_updates():
    update_info = update_manager.check_git_updates()
    return jsonify(update_info)

@app.route('/update_software', methods=['POST'])
def update_software():
    logger.info("Starting software update process")
    success, error_message, error_log = update_manager.update_software()
    
    if success:
        logger.info("Software update completed successfully")
        return jsonify({"success": True})
    else:
        logger.error(f"Software update failed: {error_message}\nDetails: {error_log}")
        return jsonify({
            "success": False,
            "error": error_message,
            "details": error_log
        }), 500

def on_exit():
    """Function to execute on application shutdown."""
    logger.info("Shutting down gracefully, please wait for execution to complete")
    pattern_manager.stop_actions()
    state.save()
    mqtt.cleanup_mqtt()

def entrypoint():
    logger.info("Starting Dune Weaver application...")
    
    # Register the on_exit function
    atexit.register(on_exit)
    # Auto-connect to serial
    try:
        connection_manager.connect_device()
    except Exception as e:
        logger.warning(f"Failed to auto-connect to serial port: {str(e)}")
        
    try:
        mqtt_handler = mqtt.init_mqtt()
    except Exception as e:
        logger.warning(f"Failed to initialize MQTT: {str(e)}")

    try:
        logger.info("Starting Flask server on port 8080...")
        app.run(debug=False, host='0.0.0.0', port=8080)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down.")
    except Exception as e:
        logger.critical(f"Unexpected error during server startup: {str(e)}")
    finally:
        on_exit()
