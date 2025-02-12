# state.py
import threading
import json
import os

class AppState:
    def __init__(self):
        # Execution state variables
        self.stop_requested = False
        self.pause_requested = False
        self.pause_condition = threading.Condition()
        self.current_playing_file = None
        self.execution_progress = None
        self.is_clearing = False
        self.current_theta = 0
        self.current_rho = 0
        self.speed = 250
        
        # Machine position variables
        self.machine_x = 0.0
        self.machine_y = 0.0
        
        # Playlist state variables
        self.current_playlist = None
        self.current_playlist_index = None
        self.playlist_mode = None  # single, loop, etc.
        
        self.STATE_FILE = "state.json"
        self.load()

    def to_dict(self):
        """Return a dictionary representation of the state."""
        return {
            "stop_requested": self.stop_requested,
            "pause_requested": self.pause_requested,
            "current_playing_file": self.current_playing_file,
            "execution_progress": self.execution_progress,
            "is_clearing": self.is_clearing,
            "current_theta": self.current_theta,
            "current_rho": self.current_rho,
            "speed": self.speed,
            "machine_x": self.machine_x,
            "machine_y": self.machine_y,
            "current_playlist": self.current_playlist,
            "current_playlist_index": self.current_playlist_index,
            "playlist_mode": self.playlist_mode
        }

    def from_dict(self, data):
        """Update state from a dictionary."""
        self.stop_requested = data.get("stop_requested", False)
        self.pause_requested = data.get("pause_requested", False)
        self.current_playing_file = data.get("current_playing_file")
        self.execution_progress = data.get("execution_progress")
        self.is_clearing = data.get("is_clearing", False)
        self.current_theta = data.get("current_theta", 0)
        self.current_rho = data.get("current_rho", 0)
        self.speed = data.get("speed", 250)
        self.machine_x = data.get("machine_x", 0.0)
        self.machine_y = data.get("machine_y", 0.0)
        self.current_playlist = data.get("current_playlist")
        self.current_playlist_index = data.get("current_playlist_index")
        self.playlist_mode = data.get("playlist_mode")

    def save(self):
        """Save the current state to a JSON file."""
        with open(self.STATE_FILE, "w") as f:
            json.dump(self.to_dict(), f)

    def load(self):
        """Load state from a JSON file. If the file doesn't exist, create it with default values."""
        if not os.path.exists(self.STATE_FILE):
            # File doesn't exist: create one with the current (default) state.
            self.save()
            return
        try:
            with open(self.STATE_FILE, "r") as f:
                data = json.load(f)
            self.from_dict(data)
        except Exception as e:
            print(f"Error loading state from {self.STATE_FILE}: {e}")

# Create a singleton instance that you can import elsewhere:
state = AppState()