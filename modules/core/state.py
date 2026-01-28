# state.py
import asyncio
import threading
import json
import os
import logging
import uuid
from typing import Optional, Literal

logger = logging.getLogger(__name__)

# Debounce timer for state saves (reduces SD card wear on Pi)
_save_timer = None
_save_lock = threading.Lock()

class AppState:
    def __init__(self):
        # Private variables for properties
        self._current_playing_file = None
        self._current_coordinates = None  # Cache parsed coordinates for current file (avoids re-parsing large files)
        self._current_preview = None  # Cache (file_name, base64_data) for current pattern preview
        self._next_preview = None  # Cache (file_name, base64_data) for next pattern preview
        self._pause_requested = False
        self._speed = 100
        self._current_playlist = None
        self._current_playlist_name = None  # New variable for playlist name
        
        # Execution control flags (with event support for async waiting)
        self._stop_requested = False
        self._skip_requested = False
        self._stop_event: Optional[asyncio.Event] = None
        self._skip_event: Optional[asyncio.Event] = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None

        # Regular state variables
        self.pause_condition = threading.Condition()
        self.execution_progress = None
        self.is_clearing = False
        self.current_theta = 0
        self.current_rho = 0
        self.current_playlist_index = 0
        self.playlist_mode = "loop"
        self.pause_time_remaining = 0
        self.active_clear_pattern = None  # Runtime: clear pattern mode for current playlist (not persisted)
        
        # Machine position variables
        self.machine_x = 0.0
        self.machine_y = 0.0
        self.x_steps_per_mm = 0.0
        self.y_steps_per_mm = 0.0
        self.gear_ratio = 10

        # Homing mode: 0 = crash homing, 1 = sensor homing ($H)
        self.homing = 0
        # Track if user has explicitly set homing preference (vs auto-detected)
        # When False/None, homing mode can be auto-detected from firmware ($22 setting)
        self.homing_user_override = False

        # Homing state tracking (for sensor mode)
        self.homed_x = False  # Set to True when [MSG:Homed:X] is received
        self.homed_y = False  # Set to True when [MSG:Homed:Y] is received

        # Homing in progress flag - blocks other movement operations
        self.is_homing = False

        # Sensor homing failure flag - set when sensor homing fails
        # This indicates to the UI that sensor homing failed and user action is needed
        self.sensor_homing_failed = False

        # Angular homing compass reference point
        # This is the angular offset in degrees where the sensor is placed
        # After homing, theta will be set to this value
        self.angular_homing_offset_degrees = 0.0

        # Auto-homing settings for playlists
        # When enabled, performs homing after X patterns during playlist execution
        self.auto_home_enabled = False
        self.auto_home_after_patterns = 5  # Number of patterns after which to auto-home
        self.patterns_since_last_home = 0  # Counter for patterns played since last home

        # Hard reset on theta reset (sends $Bye to FluidNC to reset machine position)
        # When False (default), only normalizes theta to [0, 2π) without machine reset
        # When True, also performs soft reset which clears all position counters
        self.hard_reset_theta = False

        self.STATE_FILE = "state.json"
        self.mqtt_handler = None  # Will be set by the MQTT handler
        self.conn = None
        self.port = None
        self.preferred_port = None  # User's preferred port for auto-connect
        self.wled_ip = None
        self.led_provider = "none"  # "wled", "dw_leds", or "none"
        self.led_controller = None

        # DW LED settings
        self.dw_led_num_leds = 60  # Number of LEDs in strip
        self.dw_led_gpio_pin = 18  # GPIO pin (12, 13, 18, or 19)
        self.dw_led_pixel_order = "RGB"  # Pixel color order for WS281x (RGB for WS2815, GRB for WS2812)
        self.dw_led_brightness = 35  # Brightness 0-100
        self.dw_led_speed = 50  # Effect speed 0-255
        self.dw_led_intensity = 128  # Effect intensity 0-255

        # Idle effect settings (all parameters)
        self.dw_led_idle_effect = None  # Full effect configuration dict or None

        # Playing effect settings (all parameters)
        self.dw_led_playing_effect = None  # Full effect configuration dict or None

        # Idle timeout settings
        self.dw_led_idle_timeout_enabled = False  # Enable automatic LED turn off after idle period
        self.dw_led_idle_timeout_minutes = 30  # Idle timeout duration in minutes
        self.dw_led_last_activity_time = None  # Last activity timestamp (runtime only, not persisted)
        self.table_type = None
        self.table_type_override = None  # User override for table type detection
        self._playlist_mode = "loop"
        self._pause_time = 0
        self._clear_pattern = "none"
        self._clear_pattern_speed = None  # None means use state.speed as default
        self.custom_clear_from_in = None  # Custom clear from center pattern
        self.custom_clear_from_out = None  # Custom clear from perimeter pattern
        
        # Application name setting
        self.app_name = "Dune Weaver"  # Default app name

        # Multi-table identity (for network discovery)
        self.table_id = str(uuid.uuid4())  # UUID generated on first run, persistent across restarts
        self.table_name = "Dune Weaver"  # User-customizable table name

        # Known remote tables (for multi-table management)
        # List of dicts: [{id, name, url, host?, port?, version?}, ...]
        self.known_tables = []

        # Custom branding settings (filenames only, files stored in static/custom/)
        # Favicon is auto-generated from logo as logo-favicon.ico
        self.custom_logo = None  # Custom logo filename (e.g., "logo-abc123.png")
        
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
        self.scheduled_pause_finish_pattern = False  # Finish current pattern before pausing
        self.scheduled_pause_timezone = None  # User-selected timezone (None = use system timezone)

        # Server port setting (requires restart to take effect)
        self.server_port = 8080  # Default server port

        # Machine timezone setting (IANA timezone, e.g., "America/New_York", "UTC")
        # Used for logging timestamps and scheduling features
        self.timezone = "UTC"  # Default to UTC

        # MQTT settings (UI-configurable, overrides .env if set)
        self.mqtt_enabled = False  # Master enable/disable for MQTT
        self.mqtt_broker = ""  # MQTT broker IP/hostname
        self.mqtt_port = 1883  # MQTT broker port
        self.mqtt_username = ""  # MQTT authentication username
        self.mqtt_password = ""  # MQTT authentication password
        self.mqtt_client_id = "dune_weaver"  # MQTT client ID
        self.mqtt_discovery_prefix = "homeassistant"  # Home Assistant discovery prefix
        self.mqtt_device_id = "dune_weaver"  # Device ID for Home Assistant
        self.mqtt_device_name = "Dune Weaver"  # Device display name

        self.load()

    @property
    def current_playing_file(self):
        return self._current_playing_file

    @current_playing_file.setter
    def current_playing_file(self, value):
        # Clear cached data when file changes or is unset
        if value != self._current_playing_file or value is None:
            self._current_coordinates = None
            self._current_preview = None
            self._next_preview = None

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

    # --- Execution Control Properties (stop/skip with event support) ---

    def _ensure_events(self):
        """Lazily create asyncio.Event objects in the current event loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop - skip event creation (sync code path)
            return

        # Recreate events if the event loop changed
        if self._event_loop != loop:
            self._event_loop = loop
            self._stop_event = asyncio.Event()
            self._skip_event = asyncio.Event()
            # Sync event state with current flags
            if self._stop_requested:
                self._stop_event.set()
            if self._skip_requested:
                self._skip_event.set()

    @property
    def stop_requested(self) -> bool:
        return self._stop_requested

    @stop_requested.setter
    def stop_requested(self, value: bool):
        self._stop_requested = value
        self._ensure_events()
        if self._stop_event and self._event_loop:
            # asyncio.Event.set()/clear() are NOT thread-safe
            # Use call_soon_threadsafe when called from non-async threads (e.g., motion thread)
            try:
                if asyncio.get_running_loop() == self._event_loop:
                    # Same loop - safe to call directly
                    if value:
                        self._stop_event.set()
                    else:
                        self._stop_event.clear()
                else:
                    # Different loop - use thread-safe call
                    if value:
                        self._event_loop.call_soon_threadsafe(self._stop_event.set)
                    else:
                        self._event_loop.call_soon_threadsafe(self._stop_event.clear)
            except RuntimeError:
                # No running loop (sync context) - use thread-safe call
                if self._event_loop.is_running():
                    if value:
                        self._event_loop.call_soon_threadsafe(self._stop_event.set)
                    else:
                        self._event_loop.call_soon_threadsafe(self._stop_event.clear)

    @property
    def skip_requested(self) -> bool:
        return self._skip_requested

    @skip_requested.setter
    def skip_requested(self, value: bool):
        self._skip_requested = value
        self._ensure_events()
        if self._skip_event and self._event_loop:
            # asyncio.Event.set()/clear() are NOT thread-safe
            # Use call_soon_threadsafe when called from non-async threads (e.g., motion thread)
            try:
                if asyncio.get_running_loop() == self._event_loop:
                    # Same loop - safe to call directly
                    if value:
                        self._skip_event.set()
                    else:
                        self._skip_event.clear()
                else:
                    # Different loop - use thread-safe call
                    if value:
                        self._event_loop.call_soon_threadsafe(self._skip_event.set)
                    else:
                        self._event_loop.call_soon_threadsafe(self._skip_event.clear)
            except RuntimeError:
                # No running loop (sync context) - use thread-safe call
                if self._event_loop.is_running():
                    if value:
                        self._event_loop.call_soon_threadsafe(self._skip_event.set)
                    else:
                        self._event_loop.call_soon_threadsafe(self._skip_event.clear)

    def get_stop_event(self) -> Optional[asyncio.Event]:
        """Get the stop event for async waiting. Returns None if no event loop."""
        self._ensure_events()
        return self._stop_event

    def get_skip_event(self) -> Optional[asyncio.Event]:
        """Get the skip event for async waiting. Returns None if no event loop."""
        self._ensure_events()
        return self._skip_event

    async def wait_for_interrupt(
        self,
        timeout: float = 1.0,
        check_stop: bool = True,
        check_skip: bool = True,
    ) -> Literal['timeout', 'stopped', 'skipped']:
        """
        Wait for a stop/skip interrupt or timeout.

        This provides instant response to stop/skip requests by waiting on
        asyncio.Event objects rather than polling flags.

        Args:
            timeout: Maximum time to wait in seconds
            check_stop: Whether to check for stop requests
            check_skip: Whether to check for skip requests

        Returns:
            'stopped' if stop was requested
            'skipped' if skip was requested
            'timeout' if timeout elapsed without interrupt
        """
        # Quick flag check first (handles edge cases and sync code)
        if check_stop and self._stop_requested:
            return 'stopped'
        if check_skip and self._skip_requested:
            return 'skipped'

        self._ensure_events()

        # Build list of event wait tasks
        tasks = []
        if check_stop and self._stop_event:
            tasks.append(asyncio.create_task(self._stop_event.wait(), name='stop'))
        if check_skip and self._skip_event:
            tasks.append(asyncio.create_task(self._skip_event.wait(), name='skip'))

        if not tasks:
            # No events available, fall back to simple sleep
            await asyncio.sleep(timeout)
            return 'timeout'

        # Add timeout task
        timeout_task = asyncio.create_task(asyncio.sleep(timeout), name='timeout')
        tasks.append(timeout_task)

        pending = set()  # Initialize to empty set to avoid UnboundLocalError
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            # Cancel all pending tasks
            for task in pending:
                task.cancel()
            # Await cancelled tasks to suppress warnings
            for task in pending:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Check which event fired (flags are authoritative)
        if check_stop and self._stop_requested:
            return 'stopped'
        if check_skip and self._skip_requested:
            return 'skipped'
        return 'timeout'

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
            "homing_user_override": self.homing_user_override,
            "angular_homing_offset_degrees": self.angular_homing_offset_degrees,
            "auto_home_enabled": self.auto_home_enabled,
            "auto_home_after_patterns": self.auto_home_after_patterns,
            "hard_reset_theta": self.hard_reset_theta,
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
            "preferred_port": self.preferred_port,
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
            "table_id": self.table_id,
            "table_name": self.table_name,
            "known_tables": self.known_tables,
            "custom_logo": self.custom_logo,
            "auto_play_enabled": self.auto_play_enabled,
            "auto_play_playlist": self.auto_play_playlist,
            "auto_play_run_mode": self.auto_play_run_mode,
            "auto_play_pause_time": self.auto_play_pause_time,
            "auto_play_clear_pattern": self.auto_play_clear_pattern,
            "auto_play_shuffle": self.auto_play_shuffle,
            "scheduled_pause_enabled": self.scheduled_pause_enabled,
            "scheduled_pause_time_slots": self.scheduled_pause_time_slots,
            "scheduled_pause_control_wled": self.scheduled_pause_control_wled,
            "scheduled_pause_finish_pattern": self.scheduled_pause_finish_pattern,
            "scheduled_pause_timezone": self.scheduled_pause_timezone,
            "timezone": self.timezone,
            "mqtt_enabled": self.mqtt_enabled,
            "mqtt_broker": self.mqtt_broker,
            "mqtt_port": self.mqtt_port,
            "mqtt_username": self.mqtt_username,
            "mqtt_password": self.mqtt_password,
            "mqtt_client_id": self.mqtt_client_id,
            "mqtt_discovery_prefix": self.mqtt_discovery_prefix,
            "mqtt_device_id": self.mqtt_device_id,
            "mqtt_device_name": self.mqtt_device_name,
            "table_type_override": self.table_type_override,
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
        self.homing_user_override = data.get('homing_user_override', False)
        self.angular_homing_offset_degrees = data.get('angular_homing_offset_degrees', 0.0)
        self.auto_home_enabled = data.get('auto_home_enabled', False)
        self.auto_home_after_patterns = data.get('auto_home_after_patterns', 5)
        self.hard_reset_theta = data.get('hard_reset_theta', False)
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
        self.preferred_port = data.get("preferred_port", None)
        self.wled_ip = data.get('wled_ip', None)
        self.led_provider = data.get('led_provider', "none")
        self.dw_led_num_leds = data.get('dw_led_num_leds', 60)
        self.dw_led_gpio_pin = data.get('dw_led_gpio_pin', 18)
        self.dw_led_pixel_order = data.get('dw_led_pixel_order', "RGB")
        self.dw_led_brightness = data.get('dw_led_brightness', 35)
        self.dw_led_speed = data.get('dw_led_speed', 50)
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
        # Load or generate table_id (UUID persisted once generated)
        self.table_id = data.get("table_id", None)
        if self.table_id is None:
            self.table_id = str(uuid.uuid4())
        self.table_name = data.get("table_name", "Dune Weaver")
        self.known_tables = data.get("known_tables", [])
        self.custom_logo = data.get("custom_logo", None)
        self.auto_play_enabled = data.get("auto_play_enabled", False)
        self.auto_play_playlist = data.get("auto_play_playlist", None)
        self.auto_play_run_mode = data.get("auto_play_run_mode", "loop")
        self.auto_play_pause_time = data.get("auto_play_pause_time", 5.0)
        self.auto_play_clear_pattern = data.get("auto_play_clear_pattern", "adaptive")
        self.auto_play_shuffle = data.get("auto_play_shuffle", False)
        self.scheduled_pause_enabled = data.get("scheduled_pause_enabled", False)
        self.scheduled_pause_time_slots = data.get("scheduled_pause_time_slots", [])
        self.scheduled_pause_control_wled = data.get("scheduled_pause_control_wled", False)
        self.scheduled_pause_finish_pattern = data.get("scheduled_pause_finish_pattern", False)
        self.scheduled_pause_timezone = data.get("scheduled_pause_timezone", None)
        self.timezone = data.get("timezone", "UTC")
        self.mqtt_enabled = data.get("mqtt_enabled", False)
        self.mqtt_broker = data.get("mqtt_broker", "")
        self.mqtt_port = data.get("mqtt_port", 1883)
        self.mqtt_username = data.get("mqtt_username", "")
        self.mqtt_password = data.get("mqtt_password", "")
        self.mqtt_client_id = data.get("mqtt_client_id", "dune_weaver")
        self.mqtt_discovery_prefix = data.get("mqtt_discovery_prefix", "homeassistant")
        self.mqtt_device_id = data.get("mqtt_device_id", "dune_weaver")
        self.mqtt_device_name = data.get("mqtt_device_name", "Dune Weaver")
        self.table_type_override = data.get("table_type_override", None)

    def save(self):
        """Save the current state to a JSON file."""
        try:
            with open(self.STATE_FILE, "w") as f:
                json.dump(self.to_dict(), f)
        except Exception as e:
            print(f"Error saving state to {self.STATE_FILE}: {e}")

    def save_debounced(self, delay: float = 2.0):
        """
        Schedule a state save after a delay, coalescing multiple rapid saves.
        This reduces SD card writes on Raspberry Pi.

        Args:
            delay: Seconds to wait before saving (default 2.0)
        """
        global _save_timer
        with _save_lock:
            # Cancel any pending save
            if _save_timer is not None:
                _save_timer.cancel()
            # Schedule new save
            _save_timer = threading.Timer(delay, self._do_debounced_save)
            _save_timer.daemon = True  # Don't block shutdown
            _save_timer.start()

    def _do_debounced_save(self):
        """Internal method called by debounce timer."""
        global _save_timer
        with _save_lock:
            _save_timer = None
        self.save()
        logger.debug("Debounced state save completed")

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