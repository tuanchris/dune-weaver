import os
import threading
import time
import random
import logging
from datetime import datetime
from tqdm import tqdm
from dune_weaver_flask.modules.serial import serial_manager
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

# Execution state
stop_requested = False
pause_requested = False
pause_condition = threading.Condition()
current_playing_file = None
execution_progress = None
current_playing_index = None
current_playlist = None
is_clearing = False
current_theta = current_rho = 0
speed = 800

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
    global pause_requested
    if not schedule_hours:
        return

    start_time, end_time = schedule_hours
    now = datetime.now().time()

    if start_time <= now < end_time:
        if pause_requested:
            logger.info("Starting execution: Within schedule")
        pause_requested = False
        with pause_condition:
            pause_condition.notify_all()
    else:
        if not pause_requested:
            logger.info("Pausing execution: Outside schedule")
        pause_requested = True
        threading.Thread(target=wait_for_start_time, args=(schedule_hours,), daemon=True).start()

def wait_for_start_time(schedule_hours):
    """Keep checking every 30 seconds if the time is within the schedule to resume execution."""
    global pause_requested
    start_time, end_time = schedule_hours

    while pause_requested:
        now = datetime.now().time()
        if start_time <= now < end_time:
            logger.info("Resuming execution: Within schedule")
            pause_requested = False
            with pause_condition:
                pause_condition.notify_all()
            break
        else:
            time.sleep(30)
            
def interpolate_path(theta, rho, speed=speed):
    global current_theta, current_rho
    delta_theta = current_theta - theta
    delta_rho = current_rho - rho
    x = (theta - current_theta)/(2*pi)*100
    y = (rho-current_rho) * 100
    offset = x/100 * 27.8260869565
    y += offset
    serial_manager.send_grbl_coordinates(x, y, speed)
    current_theta = theta
    current_rho = rho
    
def reset_theta():
    logger.info('Resetting Theta')
    global current_theta
    current_theta = 0

def set_speed(new_speed):
    global speed
    speed = new_speed

def run_theta_rho_file(file_path, schedule_hours=None):
    """Run a theta-rho file by sending data in optimized batches with tqdm ETA tracking."""
    global current_playing_file, execution_progress, stop_requested, current_theta, current_rho, speed
    coordinates = parse_theta_rho_file(file_path)
    total_coordinates = len(coordinates)

    if total_coordinates < 2:
        logger.warning("Not enough coordinates for interpolation")
        current_playing_file = None
        execution_progress = None
        return

    execution_progress = (0, total_coordinates, None)

    stop_actions()
    BATCH_SIZE = 15  # Max planner buffer size

    with serial_manager.serial_lock:
        current_playing_file = file_path
        execution_progress = (0, 0, None)
        stop_requested = False
        logger.info(f"Starting pattern execution: {file_path}")
        logger.debug(f"t: {current_theta}, r: {current_rho}")
        reset_theta()

        sent_index = 0  # Tracks how many coordinates have been sent

        while sent_index < len(coordinates):
            # Check buffer
            buffer_status = serial_manager.check_buffer()
            if buffer_status:
                buffer_left = buffer_status["planner_buffer"]
            else:
                buffer_left = 0  # Assume empty buffer if no response

            # Calculate how many new coordinates to send
            available_slots = BATCH_SIZE - buffer_left
            if available_slots > 0:
                num_to_send = min(available_slots, len(coordinates) - sent_index)
                batch = coordinates[sent_index:sent_index + num_to_send]

                for theta, rho in batch:
                    if stop_requested:
                        logger.debug("Execution stopped by user.")
                        break

                    with pause_condition:
                        while pause_requested:
                            logger.debug("Execution paused...")
                            pause_condition.wait()

                    schedule_checker(schedule_hours)
                    interpolate_path(theta, rho, speed)

                sent_index += num_to_send  # Update sent index

            # Wait before checking buffer again
            time.sleep(0.1)  # Check buffer every second

        serial_manager.check_idle()

    current_playing_file = None
    execution_progress = None
    logger.info("Pattern execution completed")

def run_theta_rho_files(file_paths, pause_time=0, clear_pattern=None, run_mode="single", shuffle=False, schedule_hours=None):
    """Run multiple .thr files in sequence with options."""
    global stop_requested, current_playlist, current_playing_index
    stop_requested = False
    
    if shuffle:
        random.shuffle(file_paths)
        logger.info("Playlist shuffled")

    current_playlist = file_paths

    while True:
        for idx, path in enumerate(file_paths):
            logger.info(f"Upcoming pattern: {path}")
            current_playing_index = idx
            schedule_checker(schedule_hours)
            if stop_requested:
                logger.info("Execution stopped before starting next pattern")
                return

            if clear_pattern:
                if stop_requested:
                    logger.info("Execution stopped before running the next clear pattern")
                    return

                clear_file_path = get_clear_pattern_file(clear_pattern, path)
                logger.info(f"Running clear pattern: {clear_file_path}")
                run_theta_rho_file(clear_file_path, schedule_hours)

            if not stop_requested:
                logger.info(f"Running pattern {idx + 1} of {len(file_paths)}: {path}")
                run_theta_rho_file(path, schedule_hours)

            if idx < len(file_paths) - 1:
                if stop_requested:
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
    global pause_requested, stop_requested, current_playing_index, current_playlist, is_clearing, current_playing_file, execution_progress
    with pause_condition:
        pause_requested = False
        stop_requested = True
        current_playing_index = None
        current_playlist = None
        is_clearing = False
        current_playing_file = None
        execution_progress = None

def get_status():
    """Get the current execution status."""
    global is_clearing
    # Update is_clearing based on current file
    if current_playing_file in CLEAR_PATTERNS.values():
        is_clearing = True
    else:
        is_clearing = False

    return {
        "ser_port": serial_manager.get_port(),
        "stop_requested": stop_requested,
        "pause_requested": pause_requested,
        "current_playing_file": current_playing_file,
        "execution_progress": execution_progress,
        "current_playing_index": current_playing_index,
        "current_playlist": current_playlist,
        "is_clearing": is_clearing
    }
