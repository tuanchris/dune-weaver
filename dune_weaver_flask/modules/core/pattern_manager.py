import os
import threading
import time
import random
from datetime import datetime
from tqdm import tqdm
from dune_weaver_flask.modules.serial.serial_manager import serial_manager

class PatternManager:
    def __init__(self):
        self.THETA_RHO_DIR = './patterns'
        self.CLEAR_PATTERNS = {
            "clear_from_in":  "./patterns/clear_from_in.thr",
            "clear_from_out": "./patterns/clear_from_out.thr",
            "clear_sideway":  "./patterns/clear_sideway.thr"
        }
        os.makedirs(self.THETA_RHO_DIR, exist_ok=True)

        # Execution state
        self.stop_requested = False
        self.pause_requested = False
        self.pause_condition = threading.Condition()
        self.current_playing_file = None
        self.execution_progress = None
        self.current_playing_index = None
        self.current_playlist = None
        self.is_clearing = False

    def parse_theta_rho_file(self, file_path):
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

    def get_clear_pattern_file(self, clear_pattern_mode, path=None):
        """Return a .thr file path based on pattern_name."""
        if not clear_pattern_mode or clear_pattern_mode == 'none':
            return
        print("Clear pattern mode: " + clear_pattern_mode)
        if clear_pattern_mode == "random":
            return random.choice(list(self.CLEAR_PATTERNS.values()))

        if clear_pattern_mode == 'adaptive':
            _, first_rho = self.parse_theta_rho_file(path)[0]
            if first_rho < 0.5:
                return self.CLEAR_PATTERNS['clear_from_out']
            else:
                return random.choice([self.CLEAR_PATTERNS['clear_from_in'], self.CLEAR_PATTERNS['clear_sideway']])
        else:
            return self.CLEAR_PATTERNS[clear_pattern_mode]

    def schedule_checker(self, schedule_hours):
        """Pauses/resumes execution based on a given time range."""
        if not schedule_hours:
            return

        start_time, end_time = schedule_hours
        now = datetime.now().time()

        if start_time <= now < end_time:
            if self.pause_requested:
                print("Starting execution: Within schedule.")
            self.pause_requested = False
            with self.pause_condition:
                self.pause_condition.notify_all()
        else:
            if not self.pause_requested:
                print("Pausing execution: Outside schedule.")
            self.pause_requested = True
            threading.Thread(target=self.wait_for_start_time, args=(schedule_hours,), daemon=True).start()

    def wait_for_start_time(self, schedule_hours):
        """Keep checking every 30 seconds if the time is within the schedule to resume execution."""
        start_time, end_time = schedule_hours

        while self.pause_requested:
            now = datetime.now().time()
            if start_time <= now < end_time:
                print("Resuming execution: Within schedule.")
                self.pause_requested = False
                with self.pause_condition:
                    self.pause_condition.notify_all()
                break
            else:
                time.sleep(30)

    def run_theta_rho_file(self, file_path, schedule_hours=None):
        """Run a theta-rho file by sending data in optimized batches with tqdm ETA tracking."""
        coordinates = self.parse_theta_rho_file(file_path)
        total_coordinates = len(coordinates)

        if total_coordinates < 2:
            print("Not enough coordinates for interpolation.")
            self.current_playing_file = None
            self.execution_progress = None
            return

        self.execution_progress = (0, total_coordinates, None)
        batch_size = 10

        self.stop_actions()
        with serial_manager.serial_lock:
            self.current_playing_file = file_path
            self.execution_progress = (0, 0, None)
            self.stop_requested = False
            with tqdm(total=total_coordinates, unit="coords", desc=f"Executing Pattern {file_path}", dynamic_ncols=True, disable=None) as pbar:
                for i in range(0, total_coordinates, batch_size):
                    if self.stop_requested:
                        print("Execution stopped by user after completing the current batch.")
                        break

                    with self.pause_condition:
                        while self.pause_requested:
                            print("Execution paused...")
                            self.pause_condition.wait()

                    batch = coordinates[i:i + batch_size]

                    if i == 0:
                        serial_manager.send_coordinate_batch(batch)
                        self.execution_progress = (i + batch_size, total_coordinates, None)
                        pbar.update(batch_size)
                        continue

                    while True:
                        self.schedule_checker(schedule_hours)
                        if serial_manager.ser.in_waiting > 0:
                            response = serial_manager.ser.readline().decode().strip()
                            if response == "R":
                                serial_manager.send_coordinate_batch(batch)
                                pbar.update(batch_size)
                                estimated_remaining_time = pbar.format_dict['elapsed'] / (i + batch_size) * (total_coordinates - (i + batch_size))
                                self.execution_progress = (i + batch_size, total_coordinates, estimated_remaining_time)
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

            self.reset_theta()
            serial_manager.ser.write("FINISHED\n".encode())

        self.current_playing_file = None
        self.execution_progress = None
        print("Pattern execution completed.")

    def run_theta_rho_files(self, file_paths, pause_time=0, clear_pattern=None, run_mode="single", shuffle=False, schedule_hours=None):
        """Run multiple .thr files in sequence with options."""
        self.stop_requested = False
        
        if shuffle:
            random.shuffle(file_paths)
            print("Playlist shuffled.")

        self.current_playlist = file_paths

        while True:
            for idx, path in enumerate(file_paths):
                print("Upcoming pattern: " + path)
                self.current_playing_index = idx
                self.schedule_checker(schedule_hours)
                if self.stop_requested:
                    print("Execution stopped before starting next pattern.")
                    return

                if clear_pattern:
                    if self.stop_requested:
                        print("Execution stopped before running the next clear pattern.")
                        return

                    clear_file_path = self.get_clear_pattern_file(clear_pattern, path)
                    print(f"Running clear pattern: {clear_file_path}")
                    self.run_theta_rho_file(clear_file_path, schedule_hours)

                if not self.stop_requested:
                    print(f"Running pattern {idx + 1} of {len(file_paths)}: {path}")
                    self.run_theta_rho_file(path, schedule_hours)

                if idx < len(file_paths) - 1:
                    if self.stop_requested:
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

        self.reset_theta()
        with serial_manager.serial_lock:
            serial_manager.ser.write("FINISHED\n".encode())
            
        print("All requested patterns completed (or stopped).")

    def reset_theta(self):
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

    def stop_actions(self):
        """Stop all current pattern execution."""
        with self.pause_condition:
            self.pause_requested = False
            self.pause_condition.notify_all()
            
        self.stop_requested = True
        self.current_playing_index = None
        self.current_playlist = None
        self.is_clearing = False
        self.current_playing_file = None
        self.execution_progress = None

    def get_status(self):
        """Get the current status of pattern execution."""
        if self.current_playing_file in self.CLEAR_PATTERNS.values():
            self.is_clearing = True
        else:
            self.is_clearing = False

        return {
            "ser_port": serial_manager.get_port(),
            "stop_requested": self.stop_requested,
            "pause_requested": self.pause_requested,
            "current_playing_file": self.current_playing_file,
            "execution_progress": self.execution_progress,
            "current_playing_index": self.current_playing_index,
            "current_playlist": self.current_playlist,
            "is_clearing": self.is_clearing
        }

# Create a global instance
pattern_manager = PatternManager()
