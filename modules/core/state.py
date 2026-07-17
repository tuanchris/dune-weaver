# state.py
import asyncio
import threading
import json
import os
import logging
import uuid
import base64
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
        
        # Regular state variables
        self.execution_progress = None  # (current, total, remaining, elapsed) mirror for MQTT
        self.current_theta = 0
        self.current_rho = 0
        self.playlist_mode = "loop"
        self.pause_time_remaining = 0
        self.original_pause_time = None

        # Homing mode: 0 = crash homing, 1 = sensor homing ($H)
        self.homing = 0
        # Track if user has explicitly set homing preference (vs auto-detected)
        # When False/None, homing mode can be auto-detected from firmware ($22 setting)
        self.homing_user_override = False

        # Homing in progress flag - blocks other movement operations
        self.is_homing = False

        # Sensor homing failure flag - set when sensor homing fails
        # This indicates to the UI that sensor homing failed and user action is needed
        self.sensor_homing_failed = False

        # Firmware info (runtime only, detected on connect, not persisted)
        self.firmware_type = None  # 'fluidnc', 'grbl', or 'unknown'
        self.firmware_version = None  # e.g., "v3.7.2"
        self.board_hostname = None  # board's network hostname, e.g. "DWMP" (fw > v0.1.7)
        self.board_locked = False  # board rejected us with 401 (password-protected)
        self.user_disconnected = False  # explicit /disconnect: suppress auto-reconnect

        # Angular homing compass reference point
        # This is the angular offset in degrees where the sensor is placed
        # After homing, theta will be set to this value
        self.angular_homing_offset_degrees = 0.0

        # Home on connect: whether to automatically home when connecting on startup
        # When False, auto-connect still works but homing must be triggered manually
        self.home_on_connect = True

        # Auto-homing settings for playlists
        # When enabled, performs homing after X patterns during playlist execution
        self.auto_home_enabled = False
        self.auto_home_after_patterns = 5  # Number of patterns after which to auto-home

        # Hard reset on theta reset (sends $Bye to FluidNC to reset machine position)
        # When False (default), only normalizes theta to [0, 2π) without machine reset
        # When True, also performs soft reset which clears all position counters
        self.hard_reset_theta = False

        self.STATE_FILE = "state.json"
        self.SETTINGS_FILE = "settings.json"
        self.mqtt_handler = None  # Will be set by the MQTT handler
        self.conn = None
        self.port = None
        # Address of the FluidNC board (e.g. "http://192.168.68.160" or a bare IP).
        # None => fall back to the DUNE_BOARD_URL env var or the built-in default.
        self.board_url = None
        # Board API password ($Sand/Password, fw >= v0.1.11) sent as X-Sand-Key.
        self.board_api_key = None
        # Board STA MAC (lowercase, from /sand_status) — stable hardware identity
        # used to re-find the board when DHCP moves it.
        self.board_mac = None
        # Board health telemetry mirrored from /sand_status (firmware API.md).
        # Not persisted — live diagnostics only, surfaced in Table Control.
        self.board_heap = None            # free heap bytes now
        self.board_heap_min = None        # lowest free heap since boot (low-water)
        self.board_heap_largest = None    # largest allocatable block (fragmentation)
        self.board_last_reset = None      # power_on|software|panic|task_wdt|brownout|...
        self.board_sd_ok = None           # boot-time SD readability probe (None=unknown)
        self.board_uptime = None          # seconds since board boot
        self.wled_ip = None
        self.led_provider = "none"  # "wled", "board", or "none"
        self.led_controller = None
        self.screen_controller = None

        # LED idle timeout settings (WLED idle-off; the board handles its own ring)
        self.dw_led_idle_timeout_enabled = False  # Enable automatic LED turn off after idle period
        self.dw_led_idle_timeout_minutes = 30  # Idle timeout duration in minutes
        self.dw_led_control_mode = "automated"  # "manual" or "automated"
        self.dw_led_last_activity_time = None  # Last activity timestamp (runtime only, not persisted)
        self._playlist_mode = "loop"
        self._pause_time = 0
        self._clear_pattern = "none"
        self._clear_pattern_speed = None  # None means use state.speed as default
        self._shuffle = False  # Shuffle playlist order
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
        self.mqtt_client_id = None  # MQTT client ID (None = auto-generate random unique id in handler)
        self.mqtt_discovery_prefix = "homeassistant"  # Home Assistant discovery prefix
        self.mqtt_device_id = "dune_weaver"  # Device ID for Home Assistant
        self.mqtt_device_name = "Dune Weaver"  # Device display name

        # Security settings
        self.security_mode = "off"  # "off", "lockdown", "play_only"
        self.security_password_hash = ""  # SHA-256 hex digest

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
        if value is None:
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
        if value is None:
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

    @property
    def led_automation_enabled(self) -> bool:
        return self.dw_led_control_mode == "automated"

    @property
    def shuffle(self):
        return self._shuffle

    @shuffle.setter
    def shuffle(self, value):
        self._shuffle = value

    def to_state_dict(self):
        """Return a dictionary of runtime/machine state (transient data)."""
        return {
            "pause_requested": self._pause_requested,
            "current_playing_file": self._current_playing_file,
            "current_playlist": self._current_playlist,
            "current_playlist_name": self._current_playlist_name,
            "current_theta": self.current_theta,
            "current_rho": self.current_rho,
            "port": self.port,
        }

    def to_settings_dict(self):
        """Return a dictionary of user-configured settings (persisted intentionally)."""
        # Base64-encode MQTT password for storage
        mqtt_password_encoded = ""
        if self.mqtt_password:
            mqtt_password_encoded = base64.b64encode(self.mqtt_password.encode('utf-8')).decode('ascii')
        board_api_key_encoded = ""
        if self.board_api_key:
            board_api_key_encoded = base64.b64encode(self.board_api_key.encode('utf-8')).decode('ascii')

        return {
            "speed": self._speed,
            "homing": self.homing,
            "homing_user_override": self.homing_user_override,
            "angular_homing_offset_degrees": self.angular_homing_offset_degrees,
            "home_on_connect": self.home_on_connect,
            "auto_home_enabled": self.auto_home_enabled,
            "auto_home_after_patterns": self.auto_home_after_patterns,
            "hard_reset_theta": self.hard_reset_theta,
            "playlist_mode": self._playlist_mode,
            "pause_time": self._pause_time,
            "clear_pattern": self._clear_pattern,
            "clear_pattern_speed": self._clear_pattern_speed,
            "shuffle": self._shuffle,
            "custom_clear_from_in": self.custom_clear_from_in,
            "custom_clear_from_out": self.custom_clear_from_out,
            "board_url": self.board_url,
            "board_api_key": board_api_key_encoded,
            "board_mac": self.board_mac,
            "wled_ip": self.wled_ip,
            "led_provider": self.led_provider,
            "dw_led_idle_timeout_enabled": self.dw_led_idle_timeout_enabled,
            "dw_led_idle_timeout_minutes": self.dw_led_idle_timeout_minutes,
            "dw_led_control_mode": self.dw_led_control_mode,
            "app_name": self.app_name,
            "table_id": self.table_id,
            "table_name": self.table_name,
            "known_tables": self.known_tables,
            "custom_logo": self.custom_logo,
            "scheduled_pause_enabled": self.scheduled_pause_enabled,
            "scheduled_pause_time_slots": self.scheduled_pause_time_slots,
            "scheduled_pause_control_wled": self.scheduled_pause_control_wled,
            "scheduled_pause_finish_pattern": self.scheduled_pause_finish_pattern,
            "scheduled_pause_timezone": self.scheduled_pause_timezone,
            "server_port": self.server_port,
            "timezone": self.timezone,
            "mqtt_enabled": self.mqtt_enabled,
            "mqtt_broker": self.mqtt_broker,
            "mqtt_port": self.mqtt_port,
            "mqtt_username": self.mqtt_username,
            "mqtt_password": mqtt_password_encoded,
            "mqtt_client_id": self.mqtt_client_id,
            "mqtt_discovery_prefix": self.mqtt_discovery_prefix,
            "mqtt_device_id": self.mqtt_device_id,
            "mqtt_device_name": self.mqtt_device_name,
            "security_mode": self.security_mode,
            "security_password_hash": self.security_password_hash,
        }

    def to_dict(self):
        """Return a combined dictionary (for backward compatibility)."""
        combined = self.to_state_dict()
        combined.update(self.to_settings_dict())
        return combined

    def from_state_dict(self, data):
        """Update runtime state from a dictionary."""
        self._pause_requested = data.get("pause_requested", False)
        self._current_playing_file = data.get("current_playing_file", None)
        self._current_playlist = data.get("current_playlist", None)
        self._current_playlist_name = data.get("current_playlist_name", None)
        self.current_theta = data.get("current_theta", 0)
        self.current_rho = data.get("current_rho", 0)
        self.port = data.get("port", None)

    @staticmethod
    def _decode_mqtt_password(stored_value):
        """Decode MQTT password from storage. Handles both base64-encoded and plain text (migration)."""
        if not stored_value:
            return ""
        # Try base64 decode — valid base64 will decode cleanly
        try:
            decoded = base64.b64decode(stored_value, validate=True).decode('utf-8')
            # Extra check: if the decoded string is printable, it was likely base64
            if decoded.isprintable():
                return decoded
        except Exception:
            pass
        # Not valid base64 — treat as plain text (old format, will be re-encoded on next save)
        return stored_value

    def from_settings_dict(self, data):
        """Update user settings from a dictionary."""
        self._speed = data.get("speed", 150)
        self.homing = data.get('homing', 0)
        self.homing_user_override = data.get('homing_user_override', False)
        self.angular_homing_offset_degrees = data.get('angular_homing_offset_degrees', 0.0)
        self.home_on_connect = data.get('home_on_connect', True)
        self.auto_home_enabled = data.get('auto_home_enabled', False)
        self.auto_home_after_patterns = data.get('auto_home_after_patterns', 5)
        self.hard_reset_theta = data.get('hard_reset_theta', False)
        self._playlist_mode = data.get("playlist_mode", "loop")
        self._pause_time = data.get("pause_time", 0)
        self._clear_pattern = data.get("clear_pattern", "none")
        self._clear_pattern_speed = data.get("clear_pattern_speed", None)
        self._shuffle = data.get("shuffle", False)
        self.custom_clear_from_in = data.get("custom_clear_from_in", None)
        self.custom_clear_from_out = data.get("custom_clear_from_out", None)
        self.board_url = data.get("board_url", None)
        # Same storage scheme as the MQTT password (base64, plain-text tolerated)
        self.board_api_key = self._decode_mqtt_password(data.get("board_api_key", "")) or None
        self.board_mac = data.get("board_mac", None)
        self.wled_ip = data.get('wled_ip', None)
        self.led_provider = data.get('led_provider', "none")

        self.dw_led_idle_timeout_enabled = data.get('dw_led_idle_timeout_enabled', False)
        self.dw_led_idle_timeout_minutes = data.get('dw_led_idle_timeout_minutes', 30)
        self.dw_led_control_mode = data.get('dw_led_control_mode', "automated")

        self.app_name = data.get("app_name", "Dune Weaver")
        self.table_id = data.get("table_id", None)
        if self.table_id is None:
            self.table_id = str(uuid.uuid4())
        self.table_name = data.get("table_name", "Dune Weaver")
        self.known_tables = data.get("known_tables", [])
        self.custom_logo = data.get("custom_logo", None)
        self.scheduled_pause_enabled = data.get("scheduled_pause_enabled", False)
        self.scheduled_pause_time_slots = data.get("scheduled_pause_time_slots", [])
        self.scheduled_pause_control_wled = data.get("scheduled_pause_control_wled", False)
        self.scheduled_pause_finish_pattern = data.get("scheduled_pause_finish_pattern", False)
        self.scheduled_pause_timezone = data.get("scheduled_pause_timezone", None)
        self.server_port = data.get("server_port", 8080)
        self.timezone = data.get("timezone", "UTC")
        self.mqtt_enabled = data.get("mqtt_enabled", False)
        self.mqtt_broker = data.get("mqtt_broker", "")
        self.mqtt_port = data.get("mqtt_port", 1883)
        self.mqtt_username = data.get("mqtt_username", "")
        self.mqtt_password = self._decode_mqtt_password(data.get("mqtt_password", ""))
        # Auto-migrate the legacy literal default — it was never user-configurable
        # via the UI, so any stored "dune_weaver" is a stale default, not an
        # explicit choice. Treat it as unset so the handler generates a unique id.
        stored_client_id = data.get("mqtt_client_id")
        self.mqtt_client_id = None if stored_client_id in (None, "", "dune_weaver") else stored_client_id
        self.mqtt_discovery_prefix = data.get("mqtt_discovery_prefix", "homeassistant")
        self.mqtt_device_id = data.get("mqtt_device_id", "dune_weaver")
        self.mqtt_device_name = data.get("mqtt_device_name", "Dune Weaver")
        self.security_mode = data.get("security_mode", "off")
        self.security_password_hash = data.get("security_password_hash", "")

    def from_dict(self, data):
        """Update state from a combined dictionary (backward compatibility / migration)."""
        self.from_state_dict(data)
        self.from_settings_dict(data)

    def save(self):
        """Save current state and settings to their respective JSON files."""
        try:
            with open(self.STATE_FILE, "w") as f:
                json.dump(self.to_state_dict(), f)
        except Exception as e:
            print(f"Error saving state to {self.STATE_FILE}: {e}")
        try:
            with open(self.SETTINGS_FILE, "w") as f:
                json.dump(self.to_settings_dict(), f)
        except Exception as e:
            print(f"Error saving settings to {self.SETTINGS_FILE}: {e}")

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
        """Load state and settings from their JSON files, with migration from old single-file format."""
        settings_exists = os.path.exists(self.SETTINGS_FILE)
        state_exists = os.path.exists(self.STATE_FILE)

        if not settings_exists and not state_exists:
            # Fresh install: create both files with defaults
            self.save()
            return

        if not settings_exists and state_exists:
            # Migration: old single-file format — read settings fields from state.json
            try:
                with open(self.STATE_FILE, "r") as f:
                    old_data = json.load(f)
                # Load everything from the combined old format
                self.from_dict(old_data)
                # Save to split into both files
                self.save()
                logger.info("Migrated settings from state.json to settings.json")
                return
            except Exception as e:
                print(f"Error migrating state from {self.STATE_FILE}: {e}")
                self.save()
                return

        # Normal load: read both files
        if state_exists:
            try:
                with open(self.STATE_FILE, "r") as f:
                    state_data = json.load(f)
                self.from_state_dict(state_data)
            except Exception as e:
                print(f"Error loading state from {self.STATE_FILE}: {e}")

        if settings_exists:
            try:
                with open(self.SETTINGS_FILE, "r") as f:
                    settings_data = json.load(f)
                self.from_settings_dict(settings_data)
            except Exception as e:
                print(f"Error loading settings from {self.SETTINGS_FILE}: {e}")

    def reset_state(self):
        """Reset all state variables to their default values."""
        self.__init__()  # Reinitialize the state
        self.save()


# Create a singleton instance that you can import elsewhere:
state = AppState()