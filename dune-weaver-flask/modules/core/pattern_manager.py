import os
import json
import random
import threading
from datetime import datetime
import time
from ..serial.serial_manager import send_coordinate_batch, reset_theta, send_command
import logging

logger = logging.getLogger(__name__)

# Configuration
THETA_RHO_DIR = './patterns'
CLEAR_PATTERNS = {
    "clear_from_in":  "./patterns/clear_from_in.thr",
    "clear_from_out": "./patterns/clear_from_out.thr",
    "clear_sideway":  "./patterns/clear_sideway.thr"
}
os.makedirs(THETA_RHO_DIR, exist_ok=True)

# Global variables for execution state
stop_requested = False
pause_requested = False
pause_condition = threading.Condition()
current_playing_file = None
execution_progress = None
current_playing_index = None
current_playlist = None
is_clearing = False

PLAYLISTS_FILE = os.path.join(os.getcwd(), "playlists.json")

# Ensure the playlists file exists
if not os.path.exists(PLAYLISTS_FILE):
    with open(PLAYLISTS_FILE, "w") as f:
        json.dump({}, f, indent=2)

def parse_theta_rho_file(file_path):
    """Parse a theta-rho file and return a list of (theta, rho) pairs."""
    coordinates = []
    try:
        with open(file_path, 'r') as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    theta, rho = map(float, line.split())
                    coordinates.append((theta, rho))
                except ValueError:
                    logger.warning(f"Skipping invalid line in {file_path}: {line}")
                    continue
    except FileNotFoundError:
        logger.error(f"Theta-rho file not found: {file_path}")
        return coordinates
    except Exception as e:
        logger.error(f"Error reading theta-rho file {file_path}: {str(e)}", exc_info=True)
        return coordinates

    # Normalize coordinates
    if coordinates:
        first_theta = coordinates[0][0]
        normalized = [(theta - first_theta, rho) for theta, rho in coordinates]
        coordinates = normalized

    return coordinates

def get_clear_pattern_file(pattern_name):
    """Return a .thr file path based on pattern_name."""
    if pattern_name == "random":
        return random.choice(list(CLEAR_PATTERNS.values()))
    return CLEAR_PATTERNS.get(pattern_name, CLEAR_PATTERNS["clear_from_in"])

def schedule_checker(schedule_hours):
    """Check if execution should be paused/resumed based on schedule."""
    global pause_requested
    if not schedule_hours:
        return

    start_time, end_time = schedule_hours
    now = datetime.now().time()

    if start_time <= now < end_time:
        if pause_requested:
            print("Starting execution: Within schedule.")
        pause_requested = False
        with pause_condition:
            pause_condition.notify_all()
    else:
        if not pause_requested:
            print("Pausing execution: Outside schedule.")
        pause_requested = True
        threading.Thread(target=wait_for_start_time, args=(schedule_hours,), daemon=True).start()

def wait_for_start_time(schedule_hours):
    """Keep checking if it's time to resume execution."""
    global pause_requested
    start_time, end_time = schedule_hours

    while pause_requested:
        now = datetime.now().time()
        if start_time <= now < end_time:
            print("Resuming execution: Within schedule.")
            pause_requested = False
            with pause_condition:
                pause_condition.notify_all()
            break
        else:
            time.sleep(30)

def run_theta_rho_file(file_path, schedule_hours=None):
    """Run a single theta-rho file."""
    global stop_requested, current_playing_file, execution_progress
    stop_requested = False
    current_playing_file = file_path
    execution_progress = (0, 0)

    coordinates = parse_theta_rho_file(file_path)
    total_coordinates = len(coordinates)

    if total_coordinates < 2:
        logger.error(f"Not enough coordinates for interpolation in file: {file_path}")
        current_playing_file = None
        execution_progress = None
        return

    try:
        execution_progress = (0, total_coordinates)
        batch_size = 10

        for i in range(0, total_coordinates, batch_size):
            if stop_requested:
                logger.info("Execution stopped by user after completing the current batch.")
                break

            with pause_condition:
                while pause_requested:
                    logger.info("Execution paused...")
                    pause_condition.wait()

            batch = coordinates[i:i + batch_size]
            if i == 0:
                send_coordinate_batch(batch)
                execution_progress = (i + batch_size, total_coordinates)
                continue

            while True:
                schedule_checker(schedule_hours)
                response = send_command("R")
                if response == "R":
                    send_coordinate_batch(batch)
                    execution_progress = (i + batch_size, total_coordinates)
                    break

        reset_theta()
        send_command("FINISHED")

    except Exception as e:
        logger.error(f"Error executing theta-rho file {file_path}: {str(e)}", exc_info=True)
    finally:
        current_playing_file = None
        execution_progress = None
        logger.info("Pattern execution completed.")

def run_theta_rho_files(
    file_paths,
    pause_time=0,
    clear_pattern=None,
    run_mode="single",
    shuffle=False,
    schedule_hours=None
):
    """Run multiple theta-rho files with various options."""
    global stop_requested, current_playlist, current_playing_index, is_clearing
    stop_requested = False

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

                clear_file_path = get_clear_pattern_file(clear_pattern)
                print(f"Running clear pattern: {clear_file_path}")
                is_clearing = True
                run_theta_rho_file(clear_file_path, schedule_hours)
                is_clearing = False

            if not stop_requested:
                print(f"Running pattern {idx + 1} of {len(file_paths)}: {path}")
                run_theta_rho_file(path, schedule_hours)

            if idx < len(file_paths) - 1:
                if stop_requested:
                    print("Execution stopped before running the next clear pattern.")
                    return
                if pause_time > 0:
                    print(f"Pausing for {pause_time} seconds...")
                    time.sleep(pause_time)

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

    reset_theta()
    send_command("FINISHED")
    print("All requested patterns completed (or stopped).")

def get_execution_status():
    """Get the current execution status."""
    return {
        "stop_requested": stop_requested,
        "pause_requested": pause_requested,
        "current_playing_file": current_playing_file,
        "execution_progress": execution_progress,
        "current_playing_index": current_playing_index,
        "current_playlist": current_playlist,
        "is_clearing": is_clearing
    }

def stop_execution():
    """Stop the current execution."""
    global stop_requested, pause_requested, current_playing_index
    global current_playlist, is_clearing, current_playing_file, execution_progress
    
    with pause_condition:
        pause_requested = False
        pause_condition.notify_all()
    
    stop_requested = True
    current_playing_index = None
    current_playlist = None
    is_clearing = False
    current_playing_file = None
    execution_progress = None

def pause_execution():
    """Pause the current execution."""
    global pause_requested
    with pause_condition:
        pause_requested = True

def resume_execution():
    """Resume the current execution."""
    global pause_requested
    with pause_condition:
        pause_requested = False
        pause_condition.notify_all() 