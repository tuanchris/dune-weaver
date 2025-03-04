import os
import threading
import time
import random
import logging
from datetime import datetime
from tqdm import tqdm
from modules.connection import connection_manager
from modules.core.state import state
from math import pi
from modules.led.led_controller import effect_playing, effect_idle

# Configure logging
logger = logging.getLogger(__name__)

# Global state
THETA_RHO_DIR = './patterns'
os.makedirs(THETA_RHO_DIR, exist_ok=True)

# Threading events
pause_event = threading.Event()
pause_event.set()  # Initially not paused

def list_theta_rho_files():
    files = []
    for root, _, filenames in os.walk(THETA_RHO_DIR):
        for file in filenames:
            # Get the relative path and normalize it to use forward slashes
            relative_path = os.path.relpath(os.path.join(root, file), THETA_RHO_DIR)
            # Convert Windows backslashes to forward slashes for consistency
            normalized_path = relative_path.replace(os.path.sep, '/')
            files.append(normalized_path)
    logger.debug(f"Found {len(files)} theta-rho files")
    return files

def parse_theta_rho_file(file_path):
    """Parse a theta-rho file and return a list of (theta, rho) pairs."""
    coordinates = []
    try:
        logger.debug(f"Parsing theta-rho file: {file_path}")
        with open(file_path, 'r') as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    theta, rho = map(float, line.split())
                    coordinates.append((theta, rho))
                except ValueError:
                    logger.warning(f"Skipping invalid line: {line}")
                    continue
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        return coordinates

    # Normalization Step
    if coordinates:
        first_theta = coordinates[0][0]
        normalized = [(theta - first_theta, rho) for theta, rho in coordinates]
        coordinates = normalized
        logger.debug(f"Parsed {len(coordinates)} coordinates from {file_path}")

    return coordinates

def get_clear_pattern_file(clear_pattern_mode, path=None):
    """Return a .thr file path based on pattern_name and table type."""
    if not clear_pattern_mode or clear_pattern_mode == 'none':
        return
    
    # Define patterns for each table type
    clear_patterns = {
        'dune_weaver': {
            'clear_from_out': './patterns/clear_from_out.thr',
            'clear_from_in': './patterns/clear_from_in.thr',
            'clear_sideway': './patterns/clear_sideway.thr'
        },
        'dune_weaver_mini': {
            'clear_from_out': './patterns/clear_from_out_mini.thr',
            'clear_from_in': './patterns/clear_from_in_mini.thr',
            'clear_sideway': './patterns/clear_sideway_mini.thr'
        },
        'dune_weaver_pro': {
            'clear_from_out': './patterns/clear_from_out_pro.thr',
            'clear_from_in': './patterns/clear_from_in_pro.thr',
            'clear_sideway': './patterns/clear_sideway_pro.thr'
        }
    }
    
    # Get patterns for current table type, fallback to standard patterns if type not found
    table_patterns = clear_patterns.get(state.table_type, clear_patterns['dune_weaver'])
    
    logger.debug(f"Clear pattern mode: {clear_pattern_mode} for table type: {state.table_type}")
    
    if clear_pattern_mode == "random":
        return random.choice(list(table_patterns.values()))

    if clear_pattern_mode == 'adaptive':
        if not path:
            logger.warning("No path provided for adaptive clear pattern")
            return random.choice(list(table_patterns.values()))
            
        coordinates = parse_theta_rho_file(path)
        if not coordinates:
            logger.warning("No valid coordinates found in file for adaptive clear pattern")
            return random.choice(list(table_patterns.values()))
            
        first_rho = coordinates[0][1]
        if first_rho < 0.5:
            return table_patterns['clear_from_out']
        else:
            return random.choice([table_patterns['clear_from_in'], table_patterns['clear_sideway']])
    else:
        if clear_pattern_mode not in table_patterns:
            return False
        return table_patterns[clear_pattern_mode]
            
            
def move_polar(theta, rho):
    """
    This functions take in a pair of theta rho coordinate, compute the distance to travel based on current theta, rho,
    and translate the motion to gcode jog command and sent to grbl. 
    
    Since having similar steps_per_mm will make x and y axis moves at around the same speed, we have to scale the 
    x_steps_per_mm and y_steps_per_mm so that they are roughly the same. Here's the range of motion:
    
    X axis (angular): 50mm = 1 revolution
    Y axis (radial): 0 => 20mm = theta 0 (center) => 1 (perimeter)
    
    Args:
        theta (_type_): _description_
        rho (_type_): _description_
    """
    # Adding soft limit to reduce hardware sound
    soft_limit_inner = 0.01
    if rho < soft_limit_inner:
        rho = soft_limit_inner
    
    soft_limit_outter = 0.015
    if rho > (1-soft_limit_outter):
        rho = (1-soft_limit_outter)
    
    if state.gear_ratio == 6.25:
        x_scaling_factor = 2
        y_scaling_factor = 3.7
    else:
        x_scaling_factor = 2
        y_scaling_factor = 5
    
    delta_theta = theta - state.current_theta
    delta_rho = rho - state.current_rho
    x_increment = delta_theta * 100 / (2 * pi * x_scaling_factor)  # Added -1 to reverse direction
    y_increment = delta_rho * 100 / y_scaling_factor
    
    x_total_steps = state.x_steps_per_mm * (100/x_scaling_factor)
    y_total_steps = state.y_steps_per_mm * (100/y_scaling_factor)
        
    offset = x_increment * (x_total_steps * x_scaling_factor / (state.gear_ratio * y_total_steps * y_scaling_factor))

    if state.gear_ratio == 6.25:
        y_increment -= offset
    else:
        y_increment += offset
    
    new_x_abs = state.machine_x + x_increment
    new_y_abs = state.machine_y + y_increment
    
    # dynamic_speed = compute_dynamic_speed(rho, max_speed=state.speed)
    
    connection_manager.send_grbl_coordinates(round(new_x_abs, 3), round(new_y_abs,3), state.speed)
    state.current_theta = theta
    state.current_rho = rho
    state.machine_x = new_x_abs
    state.machine_y = new_y_abs
    
def pause_execution():
    logger.info("Pausing pattern execution")
    with state.pause_condition:
        state.pause_requested = True
    pause_event.clear()  # Clear event to block execution
    return True

def resume_execution():
    logger.info("Resuming pattern execution")
    with state.pause_condition:
        state.pause_requested = False
        state.pause_condition.notify_all()
    pause_event.set()  # Set event to allow execution to continue
    return True
    
def reset_theta():
    logger.info('Resetting Theta')
    state.current_theta = 0
    connection_manager.update_machine_position()

def set_speed(new_speed):
    state.speed = new_speed
    logger.info(f'Set new state.speed {new_speed}')

def run_theta_rho_file(file_path):
    """Run a theta-rho file by sending data in optimized batches with tqdm ETA tracking."""
    
    # Check if connection is still valid, if not, restart
    # if not connection_manager.get_status_response() and isinstance(state.conn, connection_manager.WebSocketConnection):
    #     logger.info('Cannot get status response, restarting connection')
    #     connection_manager.restart_connection(home=False)
    # if (state.conn.is_connected() if state.conn else False):
    #     logger.error('Connection not established')
    #     return
    # if not file_path:
    #     return
    
    state.current_playing_file = file_path
    coordinates = parse_theta_rho_file(file_path)
    total_coordinates = len(coordinates)

    if total_coordinates < 2:
        logger.warning("Not enough coordinates for interpolation")
        state.current_playing_file = None
        state.execution_progress = None
        return


    # stop actions without resetting the playlist
    state.execution_progress = (0, total_coordinates, None, 0)
    state.stop_requested = False
    logger.info(f"Starting pattern execution: {file_path}")
    logger.info(f"t: {state.current_theta}, r: {state.current_rho}")
    reset_theta()
    
    if state.led_controller:
        effect_playing(state.led_controller)
    
    # Track last status update time for time-based updates
    last_status_update = time.time()
    status_update_interval = 0.5  # Update status every 0.5 seconds
    
    with tqdm(
        total=total_coordinates,
        unit="coords",
        desc=f"Executing Pattern {file_path}",
        dynamic_ncols=True,
        disable=False,  # Force enable the progress bar
        mininterval=1.0  # Optional: reduce update frequency to prevent flooding
    ) as pbar:
        for i, coordinate in enumerate(coordinates):
            theta, rho = coordinate

            if state.stop_requested:
                logger.info("Execution stopped by user")
                if state.led_controller:
                    effect_idle(state.led_controller)
                # Make sure to clear current_playing_file when stopping
                state.current_playing_file = None
                break
            
            if state.skip_requested:
                logger.info("Skipping pattern...")
                connection_manager.check_idle()
                if state.led_controller:
                    effect_idle(state.led_controller)
                # Make sure to clear current_playing_file when skipping
                state.current_playing_file = None
                break

            # Wait for resume if paused
            if state.pause_requested:
                logger.info("Execution paused...")
                if state.led_controller:
                    effect_idle(state.led_controller)
                pause_event.wait()
                logger.info("Execution resumed...")
                if state.led_controller:
                    effect_playing(state.led_controller)

            move_polar(theta, rho)
            
            if i != 0:
                pbar.update(1)
                estimated_remaining_time = (total_coordinates - i) / pbar.format_dict['rate'] if pbar.format_dict['rate'] and total_coordinates else 0
                elapsed_time = pbar.format_dict['elapsed']
                state.execution_progress = (i, total_coordinates, estimated_remaining_time, elapsed_time)
                
                # Send status updates based on time interval
                current_time = time.time()
                if current_time - last_status_update >= status_update_interval:
                    last_status_update = current_time

    connection_manager.check_idle()

    # Clear pattern state atomically

    state.current_playing_file = None
    state.execution_progress = None

    # Save state to persist changes to state.json
    state.save()
    
    logger.info("Pattern execution completed")

def run_theta_rho_files(file_paths, pause_time=0, clear_pattern=None, run_mode="single", shuffle=False):
    """Run multiple .thr files in sequence with options."""
    state.stop_requested = False
    
    # Set initial playlist state
    state.playlist_mode = run_mode
    state.current_playlist_index = 0


    try:
        while True:
            # Construct the complete pattern sequence
            pattern_sequence = []
            for path in file_paths:
                # Add clear pattern if specified
                if clear_pattern and clear_pattern != 'none':
                    clear_file_path = get_clear_pattern_file(clear_pattern, path)
                    if clear_file_path:
                        pattern_sequence.append(clear_file_path)
                
                # Add main pattern
                pattern_sequence.append(path)

            # Shuffle if requested
            if shuffle:
                # Get pairs of patterns (clear + main) to keep them together
                pairs = [pattern_sequence[i:i+2] for i in range(0, len(pattern_sequence), 2)]
                random.shuffle(pairs)
                # Flatten the pairs back into a single list
                pattern_sequence = [pattern for pair in pairs for pattern in pair]
                logger.info("Playlist shuffled")

            # Set the playlist to the first pattern
            state.current_playlist = pattern_sequence

            # Execute the pattern sequence
            for idx, file_path in enumerate(pattern_sequence):
                state.current_playlist_index = idx

                
                if state.stop_requested:
                    logger.info("Execution stopped")

                    return

                # Update state for main patterns only
                logger.info(f"Running pattern {file_path}")
                
                # Execute the pattern
                run_theta_rho_file(file_path)

                # Handle pause between patterns
                if idx < len(pattern_sequence) - 1 and not state.stop_requested and pause_time > 0 and not state.skip_requested:
                    logger.info(f"Pausing for {pause_time} seconds")
                    pause_start = time.time()
                    last_status_update = time.time()
                    while time.time() - pause_start < pause_time:
                        if state.skip_requested:
                            logger.info("Pause interrupted by stop/skip request")
                            break
                        
                        # Periodically send status updates during long pauses
                        current_time = time.time()
                        if current_time - last_status_update >= 0.5:  # Update every 0.5 seconds
                            last_status_update = current_time
                            
                        time.sleep(0.1)  # Use shorter sleep to check for skip more frequently
                    
                state.skip_requested = False


            if run_mode == "indefinite":
                logger.info("Playlist completed. Restarting as per 'indefinite' run mode")
                if pause_time > 0:
                    logger.debug(f"Pausing for {pause_time} seconds before restarting")
                    time.sleep(pause_time)
                continue
            else:
                logger.info("Playlist completed")
                break

    finally:

        state.current_playing_file = None
        state.execution_progress = None
        state.current_playlist = None
        state.current_playlist_index = None
        state.playlist_mode = None
        state.current_playlist_name = None  # Clear the playlist name in MQTT state
        
        if state.led_controller:
            effect_idle(state.led_controller)

        # Save state to persist changes to state.json
        state.save()
            
        logger.info("All requested patterns completed (or stopped) and state cleared")

def stop_actions(clear_playlist = True):
    """Stop all current actions."""
    with state.pause_condition:
        state.pause_requested = False
        state.stop_requested = True
        state.current_playing_file = None
        state.execution_progress = None
        state.is_clearing = False
        if clear_playlist:
            # Clear playlist state
            state.current_playlist = None
            state.current_playlist_index = None
            state.playlist_mode = None
            state.current_playlist_name = None  # Also clear the playlist name for MQTT updates
        state.pause_condition.notify_all()
        connection_manager.update_machine_position()

def get_status():
    """Get the current status of pattern execution."""
    status = {
        "current_file": state.current_playing_file,
        "is_paused": state.pause_requested,
        "is_running": bool(state.current_playing_file and not state.stop_requested),
        "progress": None,
        "playlist": None,
        "speed": state.speed
    }
    
    # Add playlist information if available
    if state.current_playlist and state.current_playlist_index is not None:
        next_index = state.current_playlist_index + 1
        status["playlist"] = {
            "current_index": state.current_playlist_index,
            "total_files": len(state.current_playlist),
            "mode": state.playlist_mode,
            "next_file": state.current_playlist[next_index] if next_index < len(state.current_playlist) else None
        }
    
    # Only include progress information if a file is actually playing
    if state.execution_progress and state.current_playing_file:
        current, total, remaining_time, elapsed_time = state.execution_progress
        status["progress"] = {
            "current": current,
            "total": total,
            "remaining_time": remaining_time,
            "elapsed_time": elapsed_time,
            "percentage": (current / total * 100) if total > 0 else 0
        }
    return status
