"""Real MQTT handler implementation."""
import os
import threading
import time
import json
from typing import Dict, Callable
import paho.mqtt.client as mqtt
import logging
import asyncio

from .base import BaseMQTTHandler
from modules.core.state import state
from modules.core.pattern_manager import list_theta_rho_files
from modules.core.playlist_manager import list_all_playlists

logger = logging.getLogger(__name__)

class MQTTHandler(BaseMQTTHandler):
    """Real implementation of MQTT handler."""

    def __init__(self, callback_registry: Dict[str, Callable]):
        # MQTT Configuration - prioritize state config over environment variables
        # This allows UI configuration to override .env settings
        self.broker = state.mqtt_broker if state.mqtt_broker else os.getenv('MQTT_BROKER')
        self.port = state.mqtt_port if state.mqtt_port else int(os.getenv('MQTT_PORT', '1883'))
        self.username = state.mqtt_username if state.mqtt_username else os.getenv('MQTT_USERNAME')
        self.password = state.mqtt_password if state.mqtt_password else os.getenv('MQTT_PASSWORD')
        self.client_id = state.mqtt_client_id if state.mqtt_client_id else os.getenv('MQTT_CLIENT_ID', 'dune_weaver')
        self.status_topic = os.getenv('MQTT_STATUS_TOPIC', 'dune_weaver/status')
        self.command_topic = os.getenv('MQTT_COMMAND_TOPIC', 'dune_weaver/command')
        self.status_interval = int(os.getenv('MQTT_STATUS_INTERVAL', '30'))

        # Store callback registry
        self.callback_registry = callback_registry

        # Threading control
        self.running = False
        self.status_thread = None

        # Home Assistant MQTT Discovery settings - prioritize state config
        self.discovery_prefix = state.mqtt_discovery_prefix if state.mqtt_discovery_prefix else os.getenv('MQTT_DISCOVERY_PREFIX', 'homeassistant')
        self.device_name = state.mqtt_device_name if state.mqtt_device_name else os.getenv('HA_DEVICE_NAME', 'Dune Weaver')
        self.device_id = state.mqtt_device_id if state.mqtt_device_id else os.getenv('HA_DEVICE_ID', 'dune_weaver')
        
        # Additional topics for state
        self.running_state_topic = f"{self.device_id}/state/running"
        self.serial_state_topic = f"{self.device_id}/state/serial"
        self.pattern_select_topic = f"{self.device_id}/pattern/set"
        self.playlist_select_topic = f"{self.device_id}/playlist/set"
        self.speed_topic = f"{self.device_id}/speed/set"
        self.completion_topic = f"{self.device_id}/state/completion"
        self.time_remaining_topic = f"{self.device_id}/state/time_remaining"

        # LED control topics
        self.led_power_topic = f"{self.device_id}/led/power/set"
        self.led_brightness_topic = f"{self.device_id}/led/brightness/set"
        self.led_effect_topic = f"{self.device_id}/led/effect/set"
        self.led_speed_topic = f"{self.device_id}/led/speed/set"
        self.led_intensity_topic = f"{self.device_id}/led/intensity/set"
        self.led_color_topic = f"{self.device_id}/led/color/set"

        # Store current state
        self.current_file = ""
        self.is_running_state = False
        self.serial_state = ""
        self.patterns = []
        self.playlists = []

        # Track connection state
        self._connected = False

        # Initialize MQTT client if broker is configured
        if self.broker:
            self.client = mqtt.Client(client_id=self.client_id)
            self.client.on_connect = self.on_connect
            self.client.on_disconnect = self.on_disconnect
            self.client.on_message = self.on_message

            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)

        self.state = state
        self.state.mqtt_handler = self  # Set reference to self in state, needed so that state setters can update the state

        # Store the main event loop during initialization
        self.main_loop = asyncio.get_event_loop()

    def setup_ha_discovery(self):
        """Publish Home Assistant MQTT discovery configurations."""
        if not self.is_enabled:
            return

        base_device = {
            "identifiers": [self.device_id],
            "name": self.device_name,
            "model": "Dune Weaver",
            "manufacturer": "DIY"
        }
        
        # Serial State Sensor
        serial_config = {
            "name": f"{self.device_name} Serial State",
            "unique_id": f"{self.device_id}_serial_state",
            "state_topic": self.serial_state_topic,
            "device": base_device,
            "icon": "mdi:serial-port",
            "entity_category": "diagnostic"
        }
        self._publish_discovery("sensor", "serial_state", serial_config)

        # Running State Sensor
        running_config = {
            "name": f"{self.device_name} Running State",
            "unique_id": f"{self.device_id}_running_state",
            "state_topic": self.running_state_topic,
            "device": base_device,
            "icon": "mdi:machine",
            "entity_category": "diagnostic"
        }
        self._publish_discovery("sensor", "running_state", running_config)

        # Stop Button
        stop_config = {
            "name": "Stop pattern execution",
            "unique_id": f"{self.device_id}_stop",
            "command_topic": f"{self.device_id}/command/stop",
            "device": base_device,
            "icon": "mdi:stop",
            "entity_category": "config"
        }
        self._publish_discovery("button", "stop", stop_config)

        # Pause Button
        pause_config = {
            "name": "Pause pattern execution",
            "unique_id": f"{self.device_id}_pause",
            "command_topic": f"{self.device_id}/command/pause",
            "state_topic": f"{self.device_id}/command/pause/state",
            "device": base_device,
            "icon": "mdi:pause",
            "entity_category": "config",
            "enabled_by_default": True,
            "availability": {
                "topic": f"{self.device_id}/command/pause/available",
                "payload_available": "true",
                "payload_not_available": "false"
            }
        }
        self._publish_discovery("button", "pause", pause_config)

        # Play Button
        play_config = {
            "name": "Resume pattern execution",
            "unique_id": f"{self.device_id}_play",
            "command_topic": f"{self.device_id}/command/play",
            "state_topic": f"{self.device_id}/command/play/state",
            "device": base_device,
            "icon": "mdi:play",
            "entity_category": "config",
            "enabled_by_default": True,
            "availability": {
                "topic": f"{self.device_id}/command/play/available",
                "payload_available": "true",
                "payload_not_available": "false"
            }
        }
        self._publish_discovery("button", "play", play_config)

        # Speed Control
        speed_config = {
            "name": f"{self.device_name} Speed",
            "unique_id": f"{self.device_id}_speed",
            "command_topic": self.speed_topic,
            "state_topic": f"{self.speed_topic}/state",
            "device": base_device,
            "icon": "mdi:speedometer",
            "mode": "box",
            "min": 50,
            "max": 2000,
            "step": 50
        }
        self._publish_discovery("number", "speed", speed_config)

        # Pattern Select
        pattern_config = {
            "name": f"{self.device_name} Pattern",
            "unique_id": f"{self.device_id}_pattern",
            "command_topic": self.pattern_select_topic,
            "state_topic": f"{self.pattern_select_topic}/state",
            "options": self.patterns,
            "device": base_device,
            "icon": "mdi:draw"
        }
        self._publish_discovery("select", "pattern", pattern_config)

        # Playlist Select
        playlist_config = {
            "name": f"{self.device_name} Playlist",
            "unique_id": f"{self.device_id}_playlist",
            "command_topic": self.playlist_select_topic,
            "state_topic": f"{self.playlist_select_topic}/state",
            "options": self.playlists,
            "device": base_device,
            "icon": "mdi:playlist-play"
        }
        self._publish_discovery("select", "playlist", playlist_config)

        # Playlist Run Mode Select
        playlist_mode_config = {
            "name": f"{self.device_name} Playlist Mode",
            "unique_id": f"{self.device_id}_playlist_mode",
            "command_topic": f"{self.device_id}/playlist/mode/set",
            "state_topic": f"{self.device_id}/playlist/mode/state",
            "options": ["single", "loop"],
            "device": base_device,
            "icon": "mdi:repeat",
            "entity_category": "config"
        }
        self._publish_discovery("select", "playlist_mode", playlist_mode_config)

        # Playlist Pause Time Number Input
        pause_time_config = {
            "name": f"{self.device_name} Playlist Pause Time",
            "unique_id": f"{self.device_id}_pause_time",
            "command_topic": f"{self.device_id}/playlist/pause_time/set",
            "state_topic": f"{self.device_id}/playlist/pause_time/state",
            "device": base_device,
            "icon": "mdi:timer",
            "entity_category": "config",
            "mode": "box",
            "unit_of_measurement": "seconds",
            "min": 0,
            "max": 86400,
        }
        self._publish_discovery("number", "pause_time", pause_time_config)

        # Clear Pattern Select
        clear_pattern_config = {
            "name": f"{self.device_name} Clear Pattern",
            "unique_id": f"{self.device_id}_clear_pattern",
            "command_topic": f"{self.device_id}/playlist/clear_pattern/set",
            "state_topic": f"{self.device_id}/playlist/clear_pattern/state",
            "options": ["none", "random", "adaptive", "clear_from_in", "clear_from_out", "clear_sideway"],
            "device": base_device,
            "icon": "mdi:eraser",
            "entity_category": "config"
        }
        self._publish_discovery("select", "clear_pattern", clear_pattern_config)

        # Shuffle Switch
        shuffle_config = {
            "name": f"{self.device_name} Shuffle",
            "unique_id": f"{self.device_id}_shuffle",
            "command_topic": f"{self.device_id}/playlist/shuffle/set",
            "state_topic": f"{self.device_id}/playlist/shuffle/state",
            "payload_on": "ON",
            "payload_off": "OFF",
            "device": base_device,
            "icon": "mdi:shuffle-variant",
            "entity_category": "config"
        }
        self._publish_discovery("switch", "shuffle", shuffle_config)

        # Completion Percentage Sensor
        completion_config = {
            "name": f"{self.device_name} Completion",
            "unique_id": f"{self.device_id}_completion",
            "state_topic": self.completion_topic,
            "device": base_device,
            "icon": "mdi:progress-clock",
            "unit_of_measurement": "%",
            "state_class": "measurement",
            "entity_category": "diagnostic"
        }
        self._publish_discovery("sensor", "completion", completion_config)

        # Time Remaining Sensor
        time_remaining_config = {
            "name": f"{self.device_name} Time Remaining",
            "unique_id": f"{self.device_id}_time_remaining",
            "state_topic": self.time_remaining_topic,
            "device": base_device,
            "icon": "mdi:timer-sand",
            "unit_of_measurement": "s",
            "device_class": "duration",
            "state_class": "measurement",
            "entity_category": "diagnostic"
        }
        self._publish_discovery("sensor", "time_remaining", time_remaining_config)

        # LED Control Entities (only for DW LEDs - WLED has its own MQTT integration)
        if state.led_provider == "dw_leds":
            # LED Power Switch
            led_power_config = {
                "name": f"{self.device_name} LED Power",
                "unique_id": f"{self.device_id}_led_power",
                "command_topic": self.led_power_topic,
                "state_topic": f"{self.device_id}/led/power/state",
                "payload_on": "ON",
                "payload_off": "OFF",
                "device": base_device,
                "icon": "mdi:lightbulb",
                "optimistic": False
            }
            self._publish_discovery("switch", "led_power", led_power_config)

            # LED Brightness Control
            led_brightness_config = {
                "name": f"{self.device_name} LED Brightness",
                "unique_id": f"{self.device_id}_led_brightness",
                "command_topic": self.led_brightness_topic,
                "state_topic": f"{self.device_id}/led/brightness/state",
                "device": base_device,
                "icon": "mdi:brightness-6",
                "min": 0,
                "max": 100,
                "mode": "slider"
            }
            self._publish_discovery("number", "led_brightness", led_brightness_config)

            # LED Effect Selector
            led_effect_options = [
                "Static", "Blink", "Breathe", "Wipe", "Fade", "Scan", "Dual Scan",
                "Rainbow Cycle", "Rainbow", "Theater Chase", "Running Lights",
                "Random Color", "Dynamic", "Twinkle", "Sparkle", "Strobe", "Fire",
                "Comet", "Chase", "Police", "Lightning", "Fireworks", "Ripple", "Flow",
                "Colorloop", "Palette Flow", "Gradient", "Multi Strobe", "Waves", "BPM",
                "Juggle", "Meteor", "Pride", "Pacifica", "Plasma", "Dissolve", "Glitter",
                "Confetti", "Sinelon", "Candle", "Aurora", "Rain", "Halloween", "Noise",
                "Funky Plank"
            ]
            led_effect_config = {
                "name": f"{self.device_name} LED Effect",
                "unique_id": f"{self.device_id}_led_effect",
                "command_topic": self.led_effect_topic,
                "state_topic": f"{self.device_id}/led/effect/state",
                "options": led_effect_options,
                "device": base_device,
                "icon": "mdi:palette"
            }
            self._publish_discovery("select", "led_effect", led_effect_config)

            # LED Speed Control
            led_speed_config = {
                "name": f"{self.device_name} LED Speed",
                "unique_id": f"{self.device_id}_led_speed",
                "command_topic": self.led_speed_topic,
                "state_topic": f"{self.device_id}/led/speed/state",
                "device": base_device,
                "icon": "mdi:speedometer",
                "min": 0,
                "max": 255,
                "mode": "slider"
            }
            self._publish_discovery("number", "led_speed", led_speed_config)

            # LED Intensity Control
            led_intensity_config = {
                "name": f"{self.device_name} LED Intensity",
                "unique_id": f"{self.device_id}_led_intensity",
                "command_topic": self.led_intensity_topic,
                "state_topic": f"{self.device_id}/led/intensity/state",
                "device": base_device,
                "icon": "mdi:brightness-7",
                "min": 0,
                "max": 255,
                "mode": "slider"
            }
            self._publish_discovery("number", "led_intensity", led_intensity_config)

            # LED RGB Color Control
            led_color_config = {
                "name": f"{self.device_name} LED Color",
                "unique_id": f"{self.device_id}_led_color",
                "command_topic": self.led_color_topic,
                "state_topic": f"{self.device_id}/led/color/state",
                "rgb_command_topic": self.led_color_topic,
                "rgb_state_topic": f"{self.device_id}/led/color/state",
                "device": base_device,
                "icon": "mdi:palette-swatch",
                "schema": "json",
                "rgb": True
            }
            self._publish_discovery("light", "led_color", led_color_config)

    def _publish_discovery(self, component: str, config_type: str, config: dict):
        """Helper method to publish HA discovery configs."""
        if not self.is_enabled:
            return
            
        discovery_topic = f"{self.discovery_prefix}/{component}/{self.device_id}/{config_type}/config"
        self.client.publish(discovery_topic, json.dumps(config), retain=True)

    def _publish_running_state(self, running_state=None):
        """Helper to publish running state and button availability."""
        if running_state is None:
            if not self.state.current_playing_file:
                running_state = "idle"
            elif self.state.pause_requested:
                running_state = "paused"
            else:
                running_state = "running"
                
        self.client.publish(self.running_state_topic, running_state, retain=True)
        
        # Update button availability based on state
        self.client.publish(f"{self.device_id}/command/pause/available", 
                          "true" if running_state == "running" else "false", 
                          retain=True)
        self.client.publish(f"{self.device_id}/command/play/available", 
                          "true" if running_state == "paused" else "false", 
                          retain=True)
                          
    def _publish_pattern_state(self, current_file=None):
        """Helper to publish pattern state."""
        if current_file is None:
            current_file = self.state.current_playing_file
            
        if current_file:
            if current_file.startswith('./patterns/'):
                current_file = current_file[len('./patterns/'):]
            else:
                current_file = current_file.split("/")[-1].split("\\")[-1]
            self.client.publish(f"{self.pattern_select_topic}/state", current_file, retain=True)
        else:
            # Clear the pattern selection
            self.client.publish(f"{self.pattern_select_topic}/state", "None", retain=True)
            
    def _publish_playlist_state(self, playlist_name=None):
        """Helper to publish playlist state."""
        if playlist_name is None:
            playlist_name = self.state.current_playlist_name
            
        if playlist_name:
            self.client.publish(f"{self.playlist_select_topic}/state", playlist_name, retain=True)
        else:
            # Clear the playlist selection
            self.client.publish(f"{self.playlist_select_topic}/state", "None", retain=True)
            
    def _publish_serial_state(self):
        """Helper to publish serial state."""
        serial_connected = (state.conn.is_connected() if state.conn else False)
        serial_port = state.port if serial_connected else None
        serial_status = f"connected to {serial_port}" if serial_connected else "disconnected"
        self.client.publish(self.serial_state_topic, serial_status, retain=True)
        
    def _publish_progress_state(self):
        """Helper to publish completion percentage and time remaining."""
        if state.execution_progress:
            current, total, remaining_time, elapsed_time = state.execution_progress
            completion_percentage = (current / total * 100) if total > 0 else 0
            
            # Publish completion percentage (rounded to 1 decimal place)
            self.client.publish(self.completion_topic, round(completion_percentage, 1), retain=True)
            
            # Publish time remaining (rounded to nearest second, defaulting to 0 if None)
            time_remaining_seconds = round(remaining_time) if remaining_time is not None else 0
            self.client.publish(self.time_remaining_topic, max(0, time_remaining_seconds), retain=True)
        else:
            # No pattern running, publish zeros
            self.client.publish(self.completion_topic, 0, retain=True)
            self.client.publish(self.time_remaining_topic, 0, retain=True)

    def _publish_playlist_settings_state(self):
        """Helper to publish playlist settings state (mode, pause_time, clear_pattern, shuffle)."""
        self.client.publish(f"{self.device_id}/playlist/mode/state", state.playlist_mode, retain=True)
        self.client.publish(f"{self.device_id}/playlist/pause_time/state", state.pause_time, retain=True)
        self.client.publish(f"{self.device_id}/playlist/clear_pattern/state", state.clear_pattern, retain=True)
        shuffle_state = "ON" if state.shuffle else "OFF"
        self.client.publish(f"{self.device_id}/playlist/shuffle/state", shuffle_state, retain=True)

    def _publish_led_state(self):
        """Helper to publish LED state to MQTT (DW LEDs only - WLED has its own MQTT)."""
        if not state.led_controller or state.led_provider != "dw_leds":
            return

        try:
            status = state.led_controller.check_status()
            if not status.get("connected", False):
                return

            # Publish power state (check both "power" for WLED compatibility and "power_on" for DW LEDs)
            is_powered = status.get("power_on", status.get("power", False))
            power_state = "ON" if is_powered else "OFF"
            self.client.publish(f"{self.device_id}/led/power/state", power_state, retain=True)

            # Publish brightness (convert from 0-1 to 0-100)
            if "brightness" in status:
                brightness = int(status["brightness"] * 100)
                self.client.publish(f"{self.device_id}/led/brightness/state", brightness, retain=True)

            # Publish effect
            if "effect_id" in status:
                effect_map = {
                    0: "Static", 1: "Blink", 2: "Breathe", 3: "Wipe", 4: "Fade",
                    5: "Scan", 6: "Dual Scan", 7: "Rainbow Cycle", 8: "Rainbow",
                    9: "Theater Chase", 10: "Running Lights", 11: "Random Color",
                    12: "Dynamic", 13: "Twinkle", 14: "Sparkle", 15: "Strobe",
                    16: "Fire", 17: "Comet", 18: "Chase", 19: "Police", 20: "Lightning",
                    21: "Fireworks", 22: "Ripple", 23: "Flow", 24: "Colorloop",
                    25: "Palette Flow", 26: "Gradient", 27: "Multi Strobe", 28: "Waves",
                    29: "BPM", 30: "Juggle", 31: "Meteor", 32: "Pride", 33: "Pacifica",
                    34: "Plasma", 35: "Dissolve", 36: "Glitter", 37: "Confetti",
                    38: "Sinelon", 39: "Candle", 40: "Aurora", 41: "Rain",
                    42: "Halloween", 43: "Noise", 44: "Funky Plank"
                }
                effect_name = effect_map.get(status["effect_id"], "Static")
                self.client.publish(f"{self.device_id}/led/effect/state", effect_name, retain=True)

            # Publish speed
            if "speed" in status:
                self.client.publish(f"{self.device_id}/led/speed/state", status["speed"], retain=True)

            # Publish intensity
            if "intensity" in status:
                self.client.publish(f"{self.device_id}/led/intensity/state", status["intensity"], retain=True)

            # Publish color (RGB)
            if "colors" in status and len(status["colors"]) > 0:
                # colors is array of hex strings like ["#ff0000", "#00ff00", "#0000ff"]
                # Convert first color to RGB dict
                color_hex = status["colors"][0]
                if color_hex and color_hex.startswith('#') and len(color_hex) == 7:
                    r = int(color_hex[1:3], 16)
                    g = int(color_hex[3:5], 16)
                    b = int(color_hex[5:7], 16)
                    self.client.publish(f"{self.device_id}/led/color/state",
                                      json.dumps({"r": r, "g": g, "b": b}), retain=True)

        except Exception as e:
            logger.error(f"Error publishing LED state: {e}")

    def update_state(self, current_file=None, is_running=None, playlist=None, playlist_name=None):
        """Update state in Home Assistant. Only publishes the attributes that are explicitly passed."""
        if not self.is_enabled:
            return

        # Update pattern state if current_file is provided
        if current_file is not None:
            self._publish_pattern_state(current_file)
        
        # Update running state and button availability if is_running is provided
        if is_running is not None:
            running_state = "running" if is_running else "paused" if self.state.current_playing_file else "idle"
            self._publish_running_state(running_state)
        
        # Update playlist state if playlist info is provided
        if playlist_name is not None:
            self._publish_playlist_state(playlist_name)

    def on_connect(self, client, userdata, flags, rc):
        """Callback when connected to MQTT broker."""
        if rc == 0:
            self._connected = True
            logger.info("MQTT Connection Accepted.")
            # Subscribe to command topics
            client.subscribe([
                (self.command_topic, 0),
                (self.pattern_select_topic, 0),
                (self.playlist_select_topic, 0),
                (self.speed_topic, 0),
                (f"{self.device_id}/command/stop", 0),
                (f"{self.device_id}/command/pause", 0),
                (f"{self.device_id}/command/play", 0),
                (f"{self.device_id}/playlist/mode/set", 0),
                (f"{self.device_id}/playlist/pause_time/set", 0),
                (f"{self.device_id}/playlist/clear_pattern/set", 0),
                (f"{self.device_id}/playlist/shuffle/set", 0),
                (self.led_power_topic, 0),
                (self.led_brightness_topic, 0),
                (self.led_effect_topic, 0),
                (self.led_speed_topic, 0),
                (self.led_intensity_topic, 0),
                (self.led_color_topic, 0),
            ])
            # Publish discovery configurations
            self.setup_ha_discovery()
        else:
            self._connected = False
            error_messages = {
                1: "Protocol level not supported",
                2: "The client-identifier is not allowed by the server",
                3: "The MQTT service is not available",
                4: "The data in the username or password is malformed",
                5: "The client is not authorized to connect"
            }
            error_msg = error_messages.get(rc, f"Unknown error code: {rc}")
            logger.error(f"MQTT Connection Refused. {error_msg}")

    def on_disconnect(self, client, userdata, rc):
        """Callback when disconnected from MQTT broker."""
        self._connected = False
        if rc == 0:
            logger.info("MQTT disconnected cleanly")
        else:
            logger.warning(f"MQTT disconnected unexpectedly with code: {rc}")

    def on_message(self, client, userdata, msg):
        """Callback when message is received."""
        try:
            if msg.topic == self.pattern_select_topic:
                from modules.core.pattern_manager import THETA_RHO_DIR
                # Handle pattern selection
                pattern_name = msg.payload.decode()
                if pattern_name in self.patterns:
                    # Schedule the coroutine to run in the main event loop
                    asyncio.run_coroutine_threadsafe(
                        self.callback_registry['run_pattern'](file_path=f"{THETA_RHO_DIR}/{pattern_name}"),
                        self.main_loop
                    ).add_done_callback(
                        lambda _: self._publish_pattern_state(None)  # Clear pattern after execution
                    )
                    self.client.publish(f"{self.pattern_select_topic}/state", pattern_name, retain=True)
            elif msg.topic == self.playlist_select_topic:
                # Handle playlist selection
                playlist_name = msg.payload.decode()
                if playlist_name in self.playlists:
                    # Schedule the coroutine to run in the main event loop
                    asyncio.run_coroutine_threadsafe(
                        self.callback_registry['run_playlist'](
                            playlist_name=playlist_name,
                            run_mode=self.state.playlist_mode,
                            pause_time=self.state.pause_time,
                            clear_pattern=self.state.clear_pattern,
                            shuffle=self.state.shuffle
                        ),
                        self.main_loop
                    ).add_done_callback(
                        lambda _: self._publish_playlist_state(None)  # Clear playlist after execution
                    )
                    self.client.publish(f"{self.playlist_select_topic}/state", playlist_name, retain=True)
            elif msg.topic == self.speed_topic:
                speed = int(msg.payload.decode())
                self.callback_registry['set_speed'](speed)
            elif msg.topic == f"{self.device_id}/command/stop":
                # Handle stop command
                callback = self.callback_registry['stop']
                if asyncio.iscoroutinefunction(callback):
                    asyncio.run_coroutine_threadsafe(callback(), self.main_loop)
                else:
                    callback()
                # Clear both pattern and playlist selections
                self._publish_pattern_state(None)
                self._publish_playlist_state(None)
            elif msg.topic == f"{self.device_id}/command/pause":
                # Handle pause command - only if in running state
                if bool(self.state.current_playing_file) and not self.state.pause_requested:
                    # Check if callback is async or sync
                    callback = self.callback_registry['pause']
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.run_coroutine_threadsafe(callback(), self.main_loop)
                    else:
                        callback()
            elif msg.topic == f"{self.device_id}/command/play":
                # Handle play command - only if in paused state
                if bool(self.state.current_playing_file) and self.state.pause_requested:
                    # Check if callback is async or sync
                    callback = self.callback_registry['resume']
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.run_coroutine_threadsafe(callback(), self.main_loop)
                    else:
                        callback()
            elif msg.topic == f"{self.device_id}/playlist/mode/set":
                mode = msg.payload.decode()
                if mode in ["single", "loop"]:
                    state.playlist_mode = mode
                    self.client.publish(f"{self.device_id}/playlist/mode/state", mode, retain=True)
            elif msg.topic == f"{self.device_id}/playlist/pause_time/set":
                pause_time = float(msg.payload.decode())
                if 0 <= pause_time <= 60:
                    state.pause_time = pause_time
                    self.client.publish(f"{self.device_id}/playlist/pause_time/state", pause_time, retain=True)
            elif msg.topic == f"{self.device_id}/playlist/clear_pattern/set":
                clear_pattern = msg.payload.decode()
                if clear_pattern in ["none", "random", "adaptive", "clear_from_in", "clear_from_out", "clear_sideway"]:
                    state.clear_pattern = clear_pattern
                    self.client.publish(f"{self.device_id}/playlist/clear_pattern/state", clear_pattern, retain=True)
            elif msg.topic == f"{self.device_id}/playlist/shuffle/set":
                payload = msg.payload.decode()
                shuffle_value = payload == "ON"
                state.shuffle = shuffle_value
                self.client.publish(f"{self.device_id}/playlist/shuffle/state", payload, retain=True)
            elif msg.topic == self.led_power_topic:
                # Handle LED power command (DW LEDs only)
                payload = msg.payload.decode()
                if state.led_controller and state.led_provider == "dw_leds":
                    power_state = 1 if payload == "ON" else 0
                    state.led_controller.set_power(power_state)
                    # Reset idle timeout when LEDs are manually powered on via MQTT (only if idle timeout is enabled)
                    if payload == "ON" and state.dw_led_idle_timeout_enabled:
                        state.dw_led_last_activity_time = time.time()
                        logger.debug("LED activity time reset due to MQTT power on")
                    self.client.publish(f"{self.device_id}/led/power/state", payload, retain=True)
            elif msg.topic == self.led_brightness_topic:
                # Handle LED brightness command (DW LEDs only)
                brightness = int(msg.payload.decode())
                if 0 <= brightness <= 100 and state.led_controller and state.led_provider == "dw_leds":
                    controller = state.led_controller.get_controller()
                    if controller and hasattr(controller, 'set_brightness'):
                        # DW LED controller expects 0-100, converts internally to 0.0-1.0
                        controller.set_brightness(brightness)
                        self.client.publish(f"{self.device_id}/led/brightness/state", brightness, retain=True)
            elif msg.topic == self.led_effect_topic:
                # Handle LED effect command (DW LEDs only)
                effect_name = msg.payload.decode()
                if state.led_controller and state.led_provider == "dw_leds":
                    # Map effect name to ID
                    effect_map = {
                        "Static": 0, "Blink": 1, "Breathe": 2, "Wipe": 3, "Fade": 4,
                        "Scan": 5, "Dual Scan": 6, "Rainbow Cycle": 7, "Rainbow": 8,
                        "Theater Chase": 9, "Running Lights": 10, "Random Color": 11,
                        "Dynamic": 12, "Twinkle": 13, "Sparkle": 14, "Strobe": 15,
                        "Fire": 16, "Comet": 17, "Chase": 18, "Police": 19, "Lightning": 20,
                        "Fireworks": 21, "Ripple": 22, "Flow": 23, "Colorloop": 24,
                        "Palette Flow": 25, "Gradient": 26, "Multi Strobe": 27, "Waves": 28,
                        "BPM": 29, "Juggle": 30, "Meteor": 31, "Pride": 32, "Pacifica": 33,
                        "Plasma": 34, "Dissolve": 35, "Glitter": 36, "Confetti": 37,
                        "Sinelon": 38, "Candle": 39, "Aurora": 40, "Rain": 41,
                        "Halloween": 42, "Noise": 43, "Funky Plank": 44
                    }
                    effect_id = effect_map.get(effect_name)
                    if effect_id is not None:
                        controller = state.led_controller.get_controller()
                        if controller and hasattr(controller, 'set_effect'):
                            controller.set_effect(effect_id)
                            self.client.publish(f"{self.device_id}/led/effect/state", effect_name, retain=True)
            elif msg.topic == self.led_speed_topic:
                # Handle LED speed command (DW LEDs only)
                speed = int(msg.payload.decode())
                if 0 <= speed <= 255 and state.led_controller and state.led_provider == "dw_leds":
                    controller = state.led_controller.get_controller()
                    if controller and hasattr(controller, 'set_speed'):
                        controller.set_speed(speed)
                        self.client.publish(f"{self.device_id}/led/speed/state", speed, retain=True)
            elif msg.topic == self.led_intensity_topic:
                # Handle LED intensity command (DW LEDs only)
                intensity = int(msg.payload.decode())
                if 0 <= intensity <= 255 and state.led_controller and state.led_provider == "dw_leds":
                    controller = state.led_controller.get_controller()
                    if controller and hasattr(controller, 'set_intensity'):
                        controller.set_intensity(intensity)
                        self.client.publish(f"{self.device_id}/led/intensity/state", intensity, retain=True)
            elif msg.topic == self.led_color_topic:
                # Handle LED color command (RGB) (DW LEDs only)
                try:
                    color_data = json.loads(msg.payload.decode())
                    if state.led_controller and state.led_provider == "dw_leds" and 'r' in color_data and 'g' in color_data and 'b' in color_data:
                        controller = state.led_controller.get_controller()
                        if controller and hasattr(controller, 'set_color'):
                            r, g, b = color_data['r'], color_data['g'], color_data['b']
                            controller.set_color(r, g, b)
                            self.client.publish(f"{self.device_id}/led/color/state",
                                              json.dumps({"r": r, "g": g, "b": b}), retain=True)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON for color command: {msg.payload}")
            else:
                # Handle other commands
                payload = json.loads(msg.payload.decode())
                command = payload.get('command')
                params = payload.get('params', {})

                if command in self.callback_registry:
                    self.callback_registry[command](**params)
                else:
                    logger.error(f"Unknown command received: {command}")

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON payload received: {msg.payload}")
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")

    def publish_status(self):
        """Publish status updates periodically."""
        while self.running:
            try:
                # Update all states
                self._publish_running_state()
                self._publish_pattern_state()
                self._publish_playlist_state()
                self._publish_serial_state()
                self._publish_progress_state()
                
                # Update speed state
                self.client.publish(f"{self.speed_topic}/state", self.state.speed, retain=True)

                # Update LED state
                self._publish_led_state()

                # Publish keepalive status
                status = {
                    "timestamp": time.time(),
                    "client_id": self.client_id
                }
                self.client.publish(self.status_topic, json.dumps(status))
                
                # Wait for next interval
                time.sleep(self.status_interval)
            except Exception as e:
                logger.error(f"Error publishing status: {e}")
                time.sleep(5)  # Wait before retry

    def start(self) -> None:
        """Start the MQTT handler."""
        if not self.is_enabled:
            return
        
        try:
            self.client.connect(self.broker, self.port)
            self.client.loop_start()
            
            # Start status publishing thread
            self.running = True
            self.status_thread = threading.Thread(target=self.publish_status, daemon=True)
            self.status_thread.start()
            
            # Get initial pattern and playlist lists
            self.patterns = list_theta_rho_files()
            self.playlists = list_all_playlists()

            # Wait a bit for MQTT connection to establish
            time.sleep(1)
            
            # Publish initial states
            self._publish_running_state()
            self._publish_pattern_state()
            self._publish_playlist_state()
            self._publish_serial_state()
            self._publish_progress_state()
            self._publish_playlist_settings_state()
            self._publish_led_state()

            # Setup Home Assistant discovery
            self.setup_ha_discovery()
            
            logger.info("MQTT Handler started successfully")
        except Exception as e:
            logger.error(f"Failed to start MQTT Handler: {e}")

    def stop(self) -> None:
        """Stop the MQTT handler."""
        if not self.is_enabled:
            return

        # First stop the running flag to prevent new iterations
        self.running = False
        
        # Clean up status thread
        local_status_thread = self.status_thread  # Keep a local reference
        if local_status_thread and local_status_thread.is_alive():
            try:
                local_status_thread.join(timeout=5)
                if local_status_thread.is_alive():
                    logger.warning("MQTT status thread did not terminate cleanly")
            except Exception as e:
                logger.error(f"Error joining status thread: {e}")
        self.status_thread = None
            
        # Clean up MQTT client
        try:
            if hasattr(self, 'client'):
                self.client.loop_stop()
                self.client.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting MQTT client: {e}")
        
        # Clean up main loop reference
        self.main_loop = None
        
        logger.info("MQTT handler stopped")

    @property
    def is_enabled(self) -> bool:
        """Return whether MQTT functionality is enabled.

        MQTT is enabled if:
        1. A broker address is configured (either via state or env var), AND
        2. Either state.mqtt_enabled is True, OR no UI config exists (env-only mode)
        """
        # If no broker configured, MQTT is disabled
        if not self.broker:
            return False

        # If state has mqtt_enabled explicitly set (UI was used), respect that setting
        # If mqtt_broker is set in state, user configured via UI - use mqtt_enabled
        if state.mqtt_broker:
            return state.mqtt_enabled

        # Otherwise, broker came from env vars - enable if broker exists
        return True

    @property
    def is_connected(self) -> bool:
        """Return whether MQTT client is currently connected to the broker."""
        return self._connected and self.is_enabled 