import os
import threading
import time
import random
import logging
from datetime import datetime
from tqdm import tqdm
from dune_weaver_flask.modules.serial import serial_manager
from dune_weaver_flask.modules.core.state import state
from math import pi

# Configure logging
logger = logging.getLogger(__name__)

# Global state
THETA_RHO_DIR = './patterns'
CLEAR_PATTERNS = {
    "clear_from_in":  "./patterns/clear_from_in.thr",
    "clear_from_out": "./patterns/clear_from_out.thr",
    "clear_sideway":  "./patterns/clear_sideway.thr"
}
os.makedirs(THETA_RHO_DIR, exist_ok=True)
current_playlist = []
current_playing_index = None

def list_theta_rho_files():
    files = []
    for root, _, filenames in os.walk(THETA_RHO_DIR):
        for file in filenames:
            relative_path = os.path.relpath(os.path.join(root, file), THETA_RHO_DIR)
            files.append(relative_path)
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
    """Return a .thr file path based on pattern_name."""
    if not clear_pattern_mode or clear_pattern_mode == 'none':
        return
    logger.info("Clear pattern mode: " + clear_pattern_mode)
    if clear_pattern_mode == "random":
        return random.choice(list(CLEAR_PATTERNS.values()))

    if clear_pattern_mode == 'adaptive':
        _, first_rho = parse_theta_rho_file(path)[0]
        if first_rho < 0.5:
            return CLEAR_PATTERNS['clear_from_out']
        else:
            return random.choice([CLEAR_PATTERNS['clear_from_in'], CLEAR_PATTERNS['clear_sideway']])
    else:
        return CLEAR_PATTERNS[clear_pattern_mode]

def schedule_checker(schedule_hours):
    """Pauses/resumes execution based on a given time range."""
    if not schedule_hours:
        return

    start_time, end_time = schedule_hours
    now = datetime.now().time()

    if start_time <= now < end_time:
        if state.pause_requested:
            logger.info("Starting execution: Within schedule")
            serial_manager.update_machine_position()
        state.pause_requested = False
        with state.pause_condition:
            state.pause_condition.notify_all()
    else:
        if not state.pause_requested:
            logger.info("Pausing execution: Outside schedule")
        state.pause_requested = True
        serial_manager.update_machine_position()
        threading.Thread(target=wait_for_start_time, args=(schedule_hours,), daemon=True).start()

def wait_for_start_time(schedule_hours):
    """Keep checking every 30 seconds if the time is within the schedule to resume execution."""
    start_time, end_time = schedule_hours

    while state.pause_requested:
        now = datetime.now().time()
        if start_time <= now < end_time:
            logger.info("Resuming execution: Within schedule")
            state.pause_requested = False
            with state.pause_condition:
                state.pause_condition.notify_all()
            break
        else:
            time.sleep(30)
            
            
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
    
    x_scaling_factor = 2
    y_scaling_factor = 5
    
    delta_theta = theta - state.current_theta
    delta_rho = rho - state.current_rho
    x_increment = delta_theta * 100 / (2 * pi * x_scaling_factor) # Scale down x from 100mm to 50mm per revolution
    y_increment = delta_rho * 100 / y_scaling_factor # Scale down y from 100mm to 20mm from center to perimeter
    
    x_total_steps = state.x_steps_per_mm * (100/x_scaling_factor)
    y_total_steps = state.y_steps_per_mm * (100/y_scaling_factor)
        
    x_increment / 50 * (x_total_steps)
    offset = x_increment * (x_total_steps * x_scaling_factor / (state.gear_ratio * y_total_steps * y_scaling_factor))
    y_increment += offset
    
    new_x_abs = state.machine_x + x_increment
    new_y_abs = state.machine_y + y_increment
    
    # dynamic_speed = compute_dynamic_speed(rho, max_speed=state.speed)
    
    serial_manager.send_grbl_coordinates(round(new_x_abs, 3), round(new_y_abs,3), state.speed)
    state.current_theta = theta
    state.current_rho = rho
    state.machine_x = new_x_abs
    state.machine_y = new_y_abs
    
def reset_theta():
    logger.info('Resetting Theta')
    state.current_theta = 0
    serial_manager.update_machine_position()

def set_speed(new_speed):
    state.speed = new_speed
    logger.info(f'Set new state.speed {new_speed}')

def run_theta_rho_file(file_path, schedule_hours=None):
    """Run a theta-rho file by sending data in optimized batches with tqdm ETA tracking."""
    if not file_path:
        return
    coordinates = parse_theta_rho_file(file_path)
    total_coordinates = len(coordinates)

    if total_coordinates < 2:
        logger.warning("Not enough coordinates for interpolation")
        state.current_playing_file = None
        state.execution_progress = None
        return

    state.execution_progress = (0, total_coordinates, None)

    stop_actions()

    with serial_manager.serial_lock:
        state.current_playing_file = file_path
        state.execution_progress = (0, 0, None)
        state.stop_requested = False
        logger.info(f"Starting pattern execution: {file_path}")
        logger.info(f"t: {state.current_theta}, r: {state.current_rho}")
        reset_theta()
        with tqdm(total=total_coordinates, unit="coords", desc=f"Executing Pattern {file_path}", dynamic_ncols=True, disable=None) as pbar:
            for i, coordinate in enumerate(coordinates):
                theta, rho = coordinate
                if state.stop_requested:
                    logger.info("Execution stopped by user after completing the current batch")
                    break

                with state.pause_condition:
                    while state.pause_requested:
                        logger.info("Execution paused...")
                        state.pause_condition.wait()

                schedule_checker(schedule_hours)
                move_polar(theta, rho)
                
                if i != 0:
                    pbar.update(1)
                    estimated_remaining_time = pbar.format_dict['elapsed'] / i * total_coordinates
                    state.execution_progress = (i, total_coordinates, estimated_remaining_time)

        serial_manager.check_idle()

    state.current_playing_file = None
    state.execution_progress = None
    logger.info("Pattern execution completed")

def run_theta_rho_files(file_paths, pause_time=0, clear_pattern=None, run_mode="single", shuffle=False, schedule_hours=None):
    """Run multiple .thr files in sequence with options."""
    global current_playing_index, current_playlist
    state.stop_requested = False
    
    if shuffle:
        random.shuffle(file_paths)
        logger.info("Playlist shuffled")

    current_playlist = file_paths

    while True:
        for idx, path in enumerate(file_paths):
            logger.info(f"Upcoming pattern: {path}")
            logger.info(idx)
            current_playing_index = idx
            schedule_checker(schedule_hours)
            if state.stop_requested:
                logger.info("Execution stopped before starting next pattern")
                return

            if clear_pattern:
                if state.stop_requested:
                    logger.info("Execution stopped before running the next clear pattern")
                    return

                clear_file_path = get_clear_pattern_file(clear_pattern, path)
                logger.info(f"Running clear pattern: {clear_file_path}")
                run_theta_rho_file(clear_file_path, schedule_hours)

            if not state.stop_requested:
                logger.info(f"Running pattern {idx + 1} of {len(file_paths)}: {path}")
                run_theta_rho_file(path, schedule_hours)

            if idx < len(file_paths) - 1:
                if state.stop_requested:
                    logger.info("Execution stopped before running the next clear pattern")
                    return
                if pause_time > 0:
                    logger.debug(f"Pausing for {pause_time} seconds")
                    time.sleep(pause_time)

        if run_mode == "indefinite":
            logger.info("Playlist completed. Restarting as per 'indefinite' run mode")
            if pause_time > 0:
                logger.debug(f"Pausing for {pause_time} seconds before restarting")
                time.sleep(pause_time)
            if shuffle:
                random.shuffle(file_paths)
                logger.info("Playlist reshuffled for the next loop")
            continue
        else:
            logger.info("Playlist completed")
            break
    logger.info("All requested patterns completed (or stopped)")

def stop_actions():
    """Stop all current pattern execution."""
    with state.pause_condition:
        state.pause_requested = False
        state.stop_requested = True
        current_playing_index = None
        current_playlist = None
        state.is_clearing = False
        state.current_playing_file = None
        state.execution_progress = None
    serial_manager.update_machine_position()

def get_status():
    """Get the current execution status."""
    # Update state.is_clearing based on current file
    if state.current_playing_file in CLEAR_PATTERNS.values():
        state.is_clearing = True
    else:
        state.is_clearing = False

    return {
        "ser_port": serial_manager.get_port(),
        "stop_requested": state.stop_requested,
        "pause_requested": state.pause_requested,
        "current_playing_file": state.current_playing_file,
        "execution_progress": state.execution_progress,
        "current_playing_index": current_playing_index,
        "current_playlist": current_playlist,
        "is_clearing": state.is_clearing
    }
