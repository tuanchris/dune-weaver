from flask import Flask, request, jsonify, render_template, send_from_directory
import atexit
import os
import logging
from datetime import datetime
import asyncio
import json
import threading
import time
import signal
from modules.connection import connection_manager
from modules.core import pattern_manager
from modules.core import playlist_manager
from modules.update import update_manager
from modules.core.state import state
from modules import mqtt
from modules.led.led_controller import LEDController, effect_idle
import requests  # Add this import
from modules.webcam.webcam_controller import webcam_controller  # Add this import

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

# Create a global lock and thread tracking variable
pattern_execution_lock = threading.Lock()
current_execution_thread = None

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
        state.conn = connection_manager.WebSocketConnection('ws://fluidnc.local:81')
        connection_manager.device_init()
        logger.info(f'Successfully connected to websocket ws://fluidnc.local:81')
        return jsonify({'success': True})

    try:
        state.conn = connection_manager.SerialConnection(port)
        connection_manager.device_init()
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
    
    global current_execution_thread

    if not file_name:
        logger.warning('Run theta-rho request received without file name')
        return jsonify({'error': 'No file name provided'}), 400

    file_path = os.path.join(pattern_manager.THETA_RHO_DIR, file_name)
    if not os.path.exists(file_path):
        logger.error(f'Theta-rho file not found: {file_path}')
        return jsonify({'error': 'File not found'}), 404

    # Check if a pattern is already running
    if current_execution_thread and current_execution_thread.is_alive():
        logger.warning(f'Attempted to run pattern while another is already running')
        return jsonify({'error': 'A pattern is already running. Stop it before starting a new one.'}), 409
        
    try:
        # Notify webcam controller that a pattern is starting
        webcam_controller.pattern_started()

        # Create a thread that will execute the pattern
        current_execution_thread = threading.Thread(
            target=execute_pattern,
            args=(file_name, pre_execution),
            daemon=True
        )
        
        # Start the thread
        current_execution_thread.start()
        
        return jsonify({"success": True, "message": f"Pattern {file_name} started in background"})
    except Exception as e:
        logger.error(f'Failed to run theta-rho file {file_name}: {str(e)}')
        return jsonify({'error': str(e)}), 500

def execute_pattern(file_name, pre_execution):
    if not (state.conn.is_connected() if state.conn else False):
        logger.warning("Attempted to run a pattern without a connection")
        return jsonify({"success": False, "error": "Connection not established"}), 400
    files_to_run = [os.path.join(pattern_manager.THETA_RHO_DIR, file_name)]
    logger.info(f'Running theta-rho file: {file_name} with pre_execution={pre_execution}')
    pattern_manager.run_theta_rho_files(files_to_run, clear_pattern=pre_execution)

@app.route('/stop_execution', methods=['POST'])
def stop_execution():
    if not (state.conn.is_connected() if state.conn else False):
        logger.warning("Attempted to stop without a connection")
        return jsonify({"success": False, "error": "Connection not established"}), 400
    pattern_manager.stop_actions()
    webcam_controller.pattern_stopped()
    return jsonify({'success': True})

@app.route('/send_home', methods=['POST'])
def send_home():
    try:
        if not (state.conn.is_connected() if state.conn else False):
            logger.warning("Attempted to move to home without a connection")
            return jsonify({"success": False, "error": "Connection not established"}), 400
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
        
    if not (state.conn.is_connected() if state.conn else False):
        logger.warning("Attempted to run a pattern without a connection")
        return jsonify({"success": False, "error": "Connection not established"}), 400

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
        if not (state.conn.is_connected() if state.conn else False):
            logger.warning("Attempted to move to center without a connection")
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
        if not (state.conn.is_connected() if state.conn else False):
            logger.warning("Attempted to move to perimeter without a connection")
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
    if not (state.conn.is_connected() if state.conn else False):
        logger.warning("Attempted to send coordinate without a connection")
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
    connected = state.conn.is_connected() if state.conn else False
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
    """Endpoint to get current status information."""
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
    if not data or "playlist_name" not in data or "files" not in data:
        return jsonify({"success": False, "error": "Playlist 'playlist_name' and 'files' are required"}), 400

    success = playlist_manager.create_playlist(data["playlist_name"], data["files"])
    return jsonify({
        "success": success,
        "message": f"Playlist '{data['playlist_name']}' created/updated"
    })

@app.route("/modify_playlist", methods=["POST"])
def modify_playlist():
    data = request.get_json()
    if not data or "playlist_name" not in data or "files" not in data:
        return jsonify({"success": False, "error": "Playlist 'playlist_name' and 'files' are required"}), 400

    success = playlist_manager.modify_playlist(data["playlist_name"], data["files"])
    return jsonify({"success": success, "message": f"Playlist '{data['playlist_name']}' updated"})

@app.route("/delete_playlist", methods=["DELETE"])
def delete_playlist():
    data = request.get_json()
    if not data or "playlist_name" not in data:
        return jsonify({"success": False, "error": "Missing 'playlist_name' field"}), 400

    success = playlist_manager.delete_playlist(data["playlist_name"])
    if not success:
        return jsonify({"success": False, "error": f"Playlist '{data['playlist_name']}' not found"}), 404

    return jsonify({
        "success": True,
        "message": f"Playlist '{data['playlist_name']}' deleted"
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

        
    if not (state.conn.is_connected() if state.conn else False):
        logger.warning("Attempted to run a playlist without a connection")
        return jsonify({"success": False, "error": "Connection not established"}), 400

    playlist_name = data["playlist_name"]
    pause_time = data.get("pause_time", 0)
    clear_pattern = data.get("clear_pattern", None)
    run_mode = data.get("run_mode", "single")
    shuffle = data.get("shuffle", False)
    
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    

    logger.info(f"Starting playlist '{playlist_name}' with mode={run_mode}, shuffle={shuffle}")
    success, message = playlist_manager.run_playlist(
        playlist_name,
        pause_time=pause_time,
        clear_pattern=clear_pattern,
        run_mode=run_mode,
        shuffle=shuffle,
    )

    if not success:
        logger.error(f"Failed to run playlist '{playlist_name}': {message}")
        return jsonify({"success": False, "error": message}), 500
    
    return jsonify({"success": True, "message": message})

# Firmware endpoints
@app.route('/set_speed', methods=['POST'])
def set_speed():
    try:
        if not (state.conn.is_connected() if state.conn else False):
            logger.warning("Attempted to change speed without a connection")
            return jsonify({"success": False, "error": "Connection not established"}), 400
        
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
        
@app.route('/set_wled_ip', methods=['POST'])
def set_wled_ip():
    """Save the WLED IP address to state"""
    data = request.json
    wled_ip = data.get("wled_ip")
    
    # Save to state
    state.wled_ip = wled_ip
    state.save()
    if state.wled_ip:
        state.led_controlller = LEDController(state.wled_ip)
    logger.info(f"WLED IP updated: {wled_ip}")

    return jsonify({"success": True, "wled_ip": state.wled_ip})


@app.route('/get_wled_ip', methods=['GET'])
def get_wled_ip():
    # Logic to get WLED IP address
    try:
        # Replace with your actual logic to get the WLED IP
        wled_ip = state.wled_ip if hasattr(state, 'wled_ip') else None
        if wled_ip:
            state.led_controlller = LEDController(state.wled_ip)
        return jsonify({"ip": wled_ip})
    except Exception as e:
        logger.error(f"Error getting WLED IP: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/skip_pattern', methods=['POST'])
def skip_pattern():
    if not state.current_playlist:
        return jsonify({"success": False, "error": "No playlist is currently running"})
    state.skip_requested = True
    return jsonify({"success": True})

@app.route('/generate_image', methods=['POST'])
def generate_image():
    try:
        api_key = request.json.get('apiKey')
        prompt = request.json.get('prompt')
        
        if not api_key or not prompt:
            return jsonify({'error': 'API key and prompt are required'}), 400
            
        full_prompt = f"Draw an image of the following: {prompt}. But make it a simple black silhouette on a white background, with very minimal detail and no additional content in the image, so I can use it for a computer icon."
        
        response = requests.post(
            'https://api.openai.com/v1/images/generations',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'dall-e-3',
                'prompt': full_prompt,
                'size': '1024x1024',
                'quality': 'standard',
                'response_format': 'b64_json',
                'n': 1
            }
        )
        
        if response.status_code != 200:
            return jsonify({'error': response.json().get('error', {}).get('message', 'Unknown error')}), response.status_code
            
        return jsonify(response.json())
        
    except Exception as e:
        logger.error(f'Failed to generate image: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/timelapse/status', methods=['GET'])
def timelapse_status():
    """Get current timelapse status"""
    try:
        status = webcam_controller.get_status()
        return jsonify(status)
    except Exception as e:
        logger.error(f"Error getting timelapse status: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/timelapse/cameras', methods=['GET'])
def list_cameras():
    """List available cameras"""
    try:
        cameras = webcam_controller.scan_cameras()
        return jsonify({"cameras": cameras})
    except Exception as e:
        logger.error(f"Error listing cameras: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/timelapse/start', methods=['POST'])
def start_timelapse():
    """Start timelapse capture"""
    try:
        data = request.json
        camera = data.get('camera')
        interval = data.get('interval')
        auto_mode = data.get('auto_mode')
        
        result = webcam_controller.start_timelapse(camera, interval, auto_mode)
        if result:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Failed to start timelapse"}), 400
    except Exception as e:
        logger.error(f"Error starting timelapse: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/timelapse/stop', methods=['POST'])
def stop_timelapse():
    """Stop timelapse capture"""
    try:
        result = webcam_controller.stop_timelapse()
        if result:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "No timelapse running"}), 400
    except Exception as e:
        logger.error(f"Error stopping timelapse: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/timelapse/sessions', methods=['GET'])
def list_timelapse_sessions():
    """List all timelapse sessions"""
    try:
        sessions = webcam_controller.list_sessions()
        return jsonify({"sessions": sessions})
    except Exception as e:
        logger.error(f"Error listing timelapse sessions: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/timelapse/frames/<session_id>', methods=['GET'])
def get_session_frames(session_id):
    """Get all frames for a session"""
    try:
        frames = webcam_controller.get_session_frames(session_id)
        return jsonify({"frames": frames})
    except Exception as e:
        logger.error(f"Error getting session frames: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/timelapse/create_video', methods=['POST'])
def create_timelapse_video():
    """Create a video from the captured frames"""
    try:
        data = request.json
        session_id = data.get('session_id')
        fps = data.get('fps', 10)
        
        if not session_id:
            return jsonify({"error": "Session ID is required"}), 400
        
        session_dir = os.path.join(webcam_controller.timelapse_dir, session_id)
        result = webcam_controller.create_video(session_dir, fps)
        
        if result:
            return jsonify(result)
        else:
            return jsonify({"success": False, "error": "Failed to create video"}), 400
    except Exception as e:
        logger.error(f"Error creating timelapse video: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/timelapse/image/<path:filename>', methods=['GET'])
def get_timelapse_image(filename):
    """Get a timelapse image"""
    try:
        # Split the path into directory and filename
        parts = filename.split('/')
        if len(parts) < 2:
            return jsonify({"error": "Invalid path"}), 400
        
        session_id = parts[0]
        image_file = parts[1]
        
        return send_from_directory(os.path.join(webcam_controller.timelapse_dir, session_id), image_file)
    except Exception as e:
        logger.error(f"Error getting timelapse image: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/timelapse/video/<session_id>', methods=['GET'])
def get_timelapse_video(session_id):
    """Get a timelapse video"""
    try:
        video_file = f"timelapse_{session_id}.mp4"
        return send_from_directory(os.path.join(webcam_controller.timelapse_dir, session_id), video_file)
    except Exception as e:
        logger.error(f"Error getting timelapse video: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/timelapse/test_capture', methods=['POST'])
def test_timelapse_capture():
    """Test camera capture"""
    try:
        data = request.json
        camera = data.get('camera')
        
        if not camera:
            return jsonify({"success": False, "error": "No camera selected"}), 400
        
        # Create a test directory if it doesn't exist
        test_dir = os.path.join(webcam_controller.timelapse_dir, 'test_captures')
        os.makedirs(test_dir, exist_ok=True)
        
        # Generate a unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(test_dir, f"test_capture_{timestamp}.jpg")
        
        # Temporarily set the camera
        original_camera = webcam_controller.selected_camera
        webcam_controller.selected_camera = camera
        
        try:
            # Capture a frame
            webcam_controller._capture_frame(output_file)
            
            # Check if the file was created
            if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                return jsonify({"success": False, "error": "Failed to capture image"}), 400
            
            # Return the path to the image
            relative_path = os.path.join('test_captures', f"test_capture_{timestamp}.jpg")
            return jsonify({
                "success": True, 
                "image_path": relative_path
            })
        finally:
            # Restore the original camera
            webcam_controller.selected_camera = original_camera
    except Exception as e:
        logger.error(f"Error testing camera capture: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/timelapse/delete/<session_id>', methods=['DELETE'])
def delete_timelapse_session(session_id):
    """Delete a timelapse session"""
    try:
        # Validate session_id to prevent directory traversal
        if not session_id or '..' in session_id or not session_id.startswith('timelapse_'):
            return jsonify({"success": False, "error": "Invalid session ID"}), 400
        
        session_dir = os.path.join(webcam_controller.timelapse_dir, session_id)
        
        # Check if directory exists
        if not os.path.exists(session_dir) or not os.path.isdir(session_dir):
            return jsonify({"success": False, "error": "Session not found"}), 404
        
        # Delete all files in the directory
        for file in os.listdir(session_dir):
            file_path = os.path.join(session_dir, file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                logger.error(f"Error deleting file {file_path}: {str(e)}")
        
        # Delete the directory
        os.rmdir(session_dir)
        
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error deleting timelapse session: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

def on_exit():
    """Function to execute on application shutdown."""
    logger.info("Shutting down gracefully, please wait for execution to complete")
    
    pattern_manager.stop_actions()
    state.save()
    mqtt.cleanup_mqtt()
    logger.info("Shutdown complete")

def signal_handler(sig, frame):
    logger.info(f"Received signal {sig}, shutting down...")
    on_exit()
    os._exit(0)

def entrypoint():
    logger.info("Starting Dune Weaver application...")
    
    # Register the on_exit function
    atexit.register(on_exit)
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
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
        # Run the Flask app
        app.run(debug=False, host='0.0.0.0', port=8080)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down.")
    except Exception as e:
        logger.critical(f"Unexpected error during server startup: {str(e)}")
    finally:
        on_exit()


if __name__ == "__main__":
    entrypoint()