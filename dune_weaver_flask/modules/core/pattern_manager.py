import os
import threading
import time
import random
from datetime import datetime
from tqdm import tqdm
from dune_weaver_flask.modules.serial import serial_manager

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
                    print(f"Skipping invalid line: {line}")
                    continue
    except Exception as e:
        print(f"Error reading file: {e}")
        return coordinates

    # Normalization Step
    if coordinates:
        first_theta = coordinates[0][0]
        normalized = [(theta - first_theta, rho) for theta, rho in coordinates]
        coordinates = normalized

    return coordinates

def get_clear_pattern_file(clear_pattern_mode, path=None):
    """Return a .thr file path based on pattern_name."""
    if not clear_pattern_mode or clear_pattern_mode == 'none':
        return
    print("Clear pattern mode: " + clear_pattern_mode)
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
    """Keep checking every 30 seconds if the time is within the schedule to resume execution."""
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
    """Run a theta-rho file by sending data in optimized batches with tqdm ETA tracking."""
    global current_playing_file, execution_progress, stop_requested
    coordinates = parse_theta_rho_file(file_path)
    total_coordinates = len(coordinates)

    if total_coordinates < 2:
        print("Not enough coordinates for interpolation.")
        current_playing_file = None
        execution_progress = None
        return

    execution_progress = (0, total_coordinates, None)
    batch_size = 10

    stop_actions()
    with serial_manager.serial_lock:
        current_playing_file = file_path
        execution_progress = (0, 0, None)
        stop_requested = False
        with tqdm(total=total_coordinates, unit="coords", desc=f"Executing Pattern {file_path}", dynamic_ncols=True, disable=None) as pbar:
            for i in range(0, total_coordinates, batch_size):
                if stop_requested:
                    print("Execution stopped by user after completing the current batch.")
                    break

                with pause_condition:
                    while pause_requested:
                        print("Execution paused...")
                        pause_condition.wait()

                batch = coordinates[i:i + batch_size]

                if i == 0:
                    serial_manager.send_coordinate_batch(batch)
                    execution_progress = (i + batch_size, total_coordinates, None)
                    pbar.update(batch_size)
                    continue

                while True:
                    schedule_checker(schedule_hours)
                    if serial_manager.ser.in_waiting > 0:
                        response = serial_manager.ser.readline().decode().strip()
                        if response == "R":
                            serial_manager.send_coordinate_batch(batch)
                            pbar.update(batch_size)
                            estimated_remaining_time = pbar.format_dict['elapsed'] / (i + batch_size) * (total_coordinates - (i + batch_size))
                            execution_progress = (i + batch_size, total_coordinates, estimated_remaining_time)
                            break
                        elif response != "IGNORED: FINISHED" and response.startswith("IGNORE"):
                            print("Received IGNORE. Resending the previous batch...")
                            print(response)
                            prev_start = max(0, i - batch_size)
                            prev_end = i
                            previous_batch = coordinates[prev_start:prev_end]
                            serial_manager.send_coordinate_batch(previous_batch)
                            break
                        else:
                            print(f"Arduino response: {response}")

        reset_theta()
        serial_manager.ser.write("FINISHED\n".encode())

    current_playing_file = None
    execution_progress = None
    print("Pattern execution completed.")

def run_theta_rho_files(file_paths, pause_time=0, clear_pattern=None, run_mode="single", shuffle=False, schedule_hours=None):
    """Run multiple .thr files in sequence with options."""
    global stop_requested, current_playlist, current_playing_index
    stop_requested = False
    
    if shuffle:
        random.shuffle(file_paths)
        print("Playlist shuffled.")

    current_playlist = file_paths

    while True:
        for idx, path in enumerate(file_paths):
            print("Upcoming pattern: " + path)
            current_playing_index = idx
            schedule_checker(schedule_hours)
            if stop_requested:
                print("Execution stopped before starting next pattern.")
                return

            if clear_pattern:
                if stop_requested:
                    print("Execution stopped before running the next clear pattern.")
                    return

                clear_file_path = get_clear_pattern_file(clear_pattern, path)
                print(f"Running clear pattern: {clear_file_path}")
                run_theta_rho_file(clear_file_path, schedule_hours)

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
    with serial_manager.serial_lock:
        serial_manager.ser.write("FINISHED\n".encode())
        
    print("All requested patterns completed (or stopped).")

def reset_theta():
    """Reset theta on the Arduino."""
    with serial_manager.serial_lock:
        serial_manager.ser.write("RESET_THETA\n".encode())
        while True:
            with serial_manager.serial_lock:
                if serial_manager.ser.in_waiting > 0:
                    response = serial_manager.ser.readline().decode().strip()
                    print(f"Arduino response: {response}")
                    if response == "THETA_RESET":
                        print("Theta successfully reset.")
                        break
            time.sleep(0.5)

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
