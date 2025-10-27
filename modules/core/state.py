# state.py
import threading
import json
import os
import logging

logger = logging.getLogger(__name__)

class AppState:
    def __init__(self):
        # Private variables for properties
        self._current_playing_file = None
        self._pause_requested = False
        self._speed = 100
        self._current_playlist = None
        self._current_playlist_name = None  # New variable for playlist name
        
        # Regular state variables
        self.stop_requested = False
        self.pause_condition = threading.Condition()
        self.execution_progress = None
        self.is_clearing = False
        self.current_theta = 0
        self.current_rho = 0
        self.current_playlist_index = 0
        self.playlist_mode = "loop"
        self.pause_time_remaining = 0
        
        # Machine position variables
        self.machine_x = 0.0
        self.machine_y = 0.0
        self.x_steps_per_mm = 0.0
        self.y_steps_per_mm = 0.0
        self.gear_ratio = 10

        # Homing mode: 0 = crash homing, 1 = sensor homing ($H)
        self.homing = 0

        # Homing state tracking (for sensor mode)
        self.homed_x = False  # Set to True when [MSG:Homed:X] is received
        self.homed_y = False  # Set to True when [MSG:Homed:Y] is received

        # Angular homing compass reference point
        # This is the angular offset in degrees where the sensor is placed
        # After homing, theta will be set to this value
        self.angular_homing_offset_degrees = 0.0

        self.STATE_FILE = "state.json"
        self.mqtt_handler = None  # Will be set by the MQTT handler
        self.conn = None
        self.port = None
        self.wled_ip = None
        self.led_provider = "none"  # "wled", "dw_leds", or "none"
        self.led_controller = None

        # DW LED settings
        self.dw_led_num_leds = 60  # Number of LEDs in strip
        self.dw_led_gpio_pin = 12  # GPIO pin (12, 13, 18, or 19)
        self.dw_led_pixel_order = "GRB"  # Pixel color order for WS281x (GRB, RGB, BGR, etc.)
        self.dw_led_brightness = 35  # Brightness 0-100
        self.dw_led_speed = 128  # Effect speed 0-255
        self.dw_led_intensity = 128  # Effect intensity 0-255

        # Idle effect settings (all parameters)
        self.dw_led_idle_effect = None  # Full effect configuration dict or None

        # Playing effect settings (all parameters)
        self.dw_led_playing_effect = None  # Full effect configuration dict or None

        # Idle timeout settings
        self.dw_led_idle_timeout_enabled = False  # Enable automatic LED turn off after idle period
        self.dw_led_idle_timeout_minutes = 30  # Idle timeout duration in minutes
        self.dw_led_last_activity_time = None  # Last activity timestamp (runtime only, not persisted)

        # Ball tracking LED settings
        self.ball_tracking_enabled = False  # Enable ball tracking
        self.ball_tracking_mode = "disabled"  # "disabled", "enabled", "playing_only"
        self.ball_tracking_led_offset = 0  # LED offset (0 to num_leds-1)
        self.ball_tracking_reversed = False  # Reverse LED direction
        self.ball_tracking_spread = 3  # Number of adjacent LEDs (1-10)
        self.ball_tracking_lookback = 5  # Coordinates to look back (0-15)
        self.ball_tracking_brightness = 50  # Brightness 0-100
        self.ball_tracking_color = "#ffffff"  # Hex color for tracking
        self.ball_tracking_trail_enabled = False  # Enable fade trail
        self.ball_tracking_trail_length = 10  # Trail length in LEDs
        self.ball_tracking_manager = None  # BallTrackingManager instance (runtime only, not persisted)

        self.skip_requested = False
        self.table_type = None
        self._playlist_mode = "loop"
        self._pause_time = 0
        self._clear_pattern = "none"
        self._clear_pattern_speed = None  # None means use state.speed as default
        self.custom_clear_from_in = None  # Custom clear from center pattern
        self.custom_clear_from_out = None  # Custom clear from perimeter pattern
        
        # Application name setting
        self.app_name = "Dune Weaver"  # Default app name
        
        # auto_play mode settings
        self.auto_play_enabled = False
        self.auto_play_playlist = None  # Playlist to auto-play in auto_play mode
        self.auto_play_run_mode = "loop"  # "single" or "loop"
        self.auto_play_pause_time = 5.0  # Pause between patterns in seconds
        self.auto_play_clear_pattern = "adaptive"  # Clear pattern option
        self.auto_play_shuffle = False  # Shuffle playlist

        # Still Sands settings
        self.scheduled_pause_enabled = False
        self.scheduled_pause_time_slots = []  # List of time slot dictionaries
        self.scheduled_pause_control_wled = False  # Turn off WLED during pause periods
        
        self.load()

    @property
    def current_playing_file(self):
        return self._current_playing_file

    @current_playing_file.setter
    def current_playing_file(self, value):
        self._current_playing_file = value
        
        # force an empty string (and not None) if we need to unset
        if value == None:
            value = ""
        if self.mqtt_handler:
            is_running = bool(value and not self._pause_requested)
            self.mqtt_handler.update_state(current_file=value, is_running=is_running)

    @property
    def pause_requested(self):
        return self._pause_requested

    @pause_requested.setter
    def pause_requested(self, value):
        self._pause_requested = value
        if self.mqtt_handler:
            is_running = bool(self._current_playing_file and not value)
            self.mqtt_handler.update_state(is_running=is_running)

    @property
    def speed(self):
        return self._speed

    @speed.setter
    def speed(self, value):
        self._speed = value
        if self.mqtt_handler and self.mqtt_handler.is_enabled:
            self.mqtt_handler.client.publish(f"{self.mqtt_handler.speed_topic}/state", value, retain=True)

    @property
    def current_playlist(self):
        return self._current_playlist

    @current_playlist.setter
    def current_playlist(self, value):
        self._current_playlist = value
        
        # force an empty string (and not None) if we need to unset
        if value == None:
            value = ""
            # Also clear the playlist name when playlist is cleared
            self._current_playlist_name = None
        if self.mqtt_handler:
            self.mqtt_handler.update_state(playlist=value, playlist_name=None)

    @property
    def current_playlist_name(self):
        return self._current_playlist_name

    @current_playlist_name.setter
    def current_playlist_name(self, value):
        self._current_playlist_name = value
        if self.mqtt_handler:
            self.mqtt_handler.update_state(playlist_name=value)

    @property
    def playlist_mode(self):
        return self._playlist_mode

    @playlist_mode.setter
    def playlist_mode(self, value):
        self._playlist_mode = value

    @property
    def pause_time(self):
        return self._pause_time

    @pause_time.setter
    def pause_time(self, value):
        self._pause_time = value

    @property
    def clear_pattern(self):
        return self._clear_pattern

    @clear_pattern.setter
    def clear_pattern(self, value):
        self._clear_pattern = value
        
    @property
    def clear_pattern_speed(self):
        return self._clear_pattern_speed

    @clear_pattern_speed.setter
    def clear_pattern_speed(self, value):
        self._clear_pattern_speed = value

    def to_dict(self):
        """Return a dictionary representation of the state."""
        return {
            "stop_requested": self.stop_requested,
            "pause_requested": self._pause_requested,
            "current_playing_file": self._current_playing_file,
            "execution_progress": self.execution_progress,
            "is_clearing": self.is_clearing,
            "current_theta": self.current_theta,
            "current_rho": self.current_rho,
            "speed": self._speed,
            "machine_x": self.machine_x,
            "machine_y": self.machine_y,
            "x_steps_per_mm": self.x_steps_per_mm,
            "y_steps_per_mm": self.y_steps_per_mm,
            "gear_ratio": self.gear_ratio,
            "homing": self.homing,
            "angular_homing_offset_degrees": self.angular_homing_offset_degrees,
            "current_playlist": self._current_playlist,
            "current_playlist_name": self._current_playlist_name,
            "current_playlist_index": self.current_playlist_index,
            "playlist_mode": self._playlist_mode,
            "pause_time": self._pause_time,
            "clear_pattern": self._clear_pattern,
            "clear_pattern_speed": self._clear_pattern_speed,
            "custom_clear_from_in": self.custom_clear_from_in,
            "custom_clear_from_out": self.custom_clear_from_out,
            "port": self.port,
            "wled_ip": self.wled_ip,
            "led_provider": self.led_provider,
            "dw_led_num_leds": self.dw_led_num_leds,
            "dw_led_gpio_pin": self.dw_led_gpio_pin,
            "dw_led_pixel_order": self.dw_led_pixel_order,
            "dw_led_brightness": self.dw_led_brightness,
            "dw_led_speed": self.dw_led_speed,
            "dw_led_intensity": self.dw_led_intensity,
            "dw_led_idle_effect": self.dw_led_idle_effect,
            "dw_led_playing_effect": self.dw_led_playing_effect,
            "dw_led_idle_timeout_enabled": self.dw_led_idle_timeout_enabled,
            "dw_led_idle_timeout_minutes": self.dw_led_idle_timeout_minutes,
            "app_name": self.app_name,
            "auto_play_enabled": self.auto_play_enabled,
            "auto_play_playlist": self.auto_play_playlist,
            "auto_play_run_mode": self.auto_play_run_mode,
            "auto_play_pause_time": self.auto_play_pause_time,
            "auto_play_clear_pattern": self.auto_play_clear_pattern,
            "auto_play_shuffle": self.auto_play_shuffle,
            "scheduled_pause_enabled": self.scheduled_pause_enabled,
            "scheduled_pause_time_slots": self.scheduled_pause_time_slots,
            "scheduled_pause_control_wled": self.scheduled_pause_control_wled,
            "ball_tracking_enabled": self.ball_tracking_enabled,
            "ball_tracking_mode": self.ball_tracking_mode,
            "ball_tracking_led_offset": self.ball_tracking_led_offset,
            "ball_tracking_reversed": self.ball_tracking_reversed,
            "ball_tracking_spread": self.ball_tracking_spread,
            "ball_tracking_lookback": self.ball_tracking_lookback,
            "ball_tracking_brightness": self.ball_tracking_brightness,
            "ball_tracking_color": self.ball_tracking_color,
            "ball_tracking_trail_enabled": self.ball_tracking_trail_enabled,
            "ball_tracking_trail_length": self.ball_tracking_trail_length,
        }

    def from_dict(self, data):
        """Update state from a dictionary."""
        self.stop_requested = data.get("stop_requested", False)
        self._pause_requested = data.get("pause_requested", False)
        self._current_playing_file = data.get("current_playing_file", None)
        self.execution_progress = data.get("execution_progress")
        self.is_clearing = data.get("is_clearing", False)
        self.current_theta = data.get("current_theta", 0)
        self.current_rho = data.get("current_rho", 0)
        self._speed = data.get("speed", 150)
        self.machine_x = data.get("machine_x", 0.0)
        self.machine_y = data.get("machine_y", 0.0)
        self.x_steps_per_mm = data.get("x_steps_per_mm", 0.0)
        self.y_steps_per_mm = data.get("y_steps_per_mm", 0.0)
        self.gear_ratio = data.get('gear_ratio', 10)
        self.homing = data.get('homing', 0)
        self.angular_homing_offset_degrees = data.get('angular_homing_offset_degrees', 0.0)
        self._current_playlist = data.get("current_playlist", None)
        self._current_playlist_name = data.get("current_playlist_name", None)
        self.current_playlist_index = data.get("current_playlist_index", None)
        self._playlist_mode = data.get("playlist_mode", "loop")
        self._pause_time = data.get("pause_time", 0)
        self._clear_pattern = data.get("clear_pattern", "none")
        self._clear_pattern_speed = data.get("clear_pattern_speed", None)
        self.custom_clear_from_in = data.get("custom_clear_from_in", None)
        self.custom_clear_from_out = data.get("custom_clear_from_out", None)
        self.port = data.get("port", None)
        self.wled_ip = data.get('wled_ip', None)
        self.led_provider = data.get('led_provider', "none")
        self.dw_led_num_leds = data.get('dw_led_num_leds', 60)
        self.dw_led_gpio_pin = data.get('dw_led_gpio_pin', 12)
        self.dw_led_pixel_order = data.get('dw_led_pixel_order', "GRB")
        self.dw_led_brightness = data.get('dw_led_brightness', 35)
        self.dw_led_speed = data.get('dw_led_speed', 128)
        self.dw_led_intensity = data.get('dw_led_intensity', 128)

        # Load effect settings (handle both old string format and new dict format)
        idle_effect_data = data.get('dw_led_idle_effect', None)
        if isinstance(idle_effect_data, str):
            # Old format: just effect name
            self.dw_led_idle_effect = None if idle_effect_data == "off" else {"effect_id": 0}
        else:
            # New format: full dict or None
            self.dw_led_idle_effect = idle_effect_data

        playing_effect_data = data.get('dw_led_playing_effect', None)
        if isinstance(playing_effect_data, str):
            # Old format: just effect name
            self.dw_led_playing_effect = None if playing_effect_data == "off" else {"effect_id": 0}
        else:
            # New format: full dict or None
            self.dw_led_playing_effect = playing_effect_data

        # Load idle timeout settings
        self.dw_led_idle_timeout_enabled = data.get('dw_led_idle_timeout_enabled', False)
        self.dw_led_idle_timeout_minutes = data.get('dw_led_idle_timeout_minutes', 30)

        self.app_name = data.get("app_name", "Dune Weaver")
        self.auto_play_enabled = data.get("auto_play_enabled", False)
        self.auto_play_playlist = data.get("auto_play_playlist", None)
        self.auto_play_run_mode = data.get("auto_play_run_mode", "loop")
        self.auto_play_pause_time = data.get("auto_play_pause_time", 5.0)
        self.auto_play_clear_pattern = data.get("auto_play_clear_pattern", "adaptive")
        self.auto_play_shuffle = data.get("auto_play_shuffle", False)
        self.scheduled_pause_enabled = data.get("scheduled_pause_enabled", False)
        self.scheduled_pause_time_slots = data.get("scheduled_pause_time_slots", [])
        self.scheduled_pause_control_wled = data.get("scheduled_pause_control_wled", False)

        # Load ball tracking settings
        self.ball_tracking_enabled = data.get("ball_tracking_enabled", False)
        self.ball_tracking_mode = data.get("ball_tracking_mode", "disabled")
        self.ball_tracking_led_offset = data.get("ball_tracking_led_offset", 0)
        self.ball_tracking_reversed = data.get("ball_tracking_reversed", False)
        self.ball_tracking_spread = data.get("ball_tracking_spread", 3)
        self.ball_tracking_lookback = data.get("ball_tracking_lookback", 5)
        self.ball_tracking_brightness = data.get("ball_tracking_brightness", 50)
        self.ball_tracking_color = data.get("ball_tracking_color", "#ffffff")
        self.ball_tracking_trail_enabled = data.get("ball_tracking_trail_enabled", False)
        self.ball_tracking_trail_length = data.get("ball_tracking_trail_length", 10)

    def save(self):
        """Save the current state to a JSON file."""
        try:
            with open(self.STATE_FILE, "w") as f:
                json.dump(self.to_dict(), f)
        except Exception as e:
            print(f"Error saving state to {self.STATE_FILE}: {e}")

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

    def update_steps_per_mm(self, x_steps, y_steps):
        """Update and save steps per mm values."""
        self.x_steps_per_mm = x_steps
        self.y_steps_per_mm = y_steps
        self.save()

    def reset_state(self):
        """Reset all state variables to their default values."""
        self.__init__()  # Reinitialize the state
        self.save()


# Create a singleton instance that you can import elsewhere:
state = AppState()