"""Real MQTT handler implementation."""
import os
import threading
import time
import json
from typing import Dict, Callable, List, Optional, Any
import paho.mqtt.client as mqtt
import logging
import asyncio
from functools import partial

from .base import BaseMQTTHandler
from modules.core.state import state
from modules.core.pattern_manager import list_theta_rho_files
from modules.core.playlist_manager import list_all_playlists

logger = logging.getLogger(__name__)

class MQTTHandler(BaseMQTTHandler):
    """Real implementation of MQTT handler."""
    
    def __init__(self, callback_registry: Dict[str, Callable]):
        # MQTT Configuration from environment variables
        self.broker = os.getenv('MQTT_BROKER')
        self.port = int(os.getenv('MQTT_PORT', '1883'))
        self.username = os.getenv('MQTT_USERNAME')
        self.password = os.getenv('MQTT_PASSWORD')
        self.client_id = os.getenv('MQTT_CLIENT_ID', 'dune_weaver')
        self.status_topic = os.getenv('MQTT_STATUS_TOPIC', 'dune_weaver/status')
        self.command_topic = os.getenv('MQTT_COMMAND_TOPIC', 'dune_weaver/command')
        self.status_interval = int(os.getenv('MQTT_STATUS_INTERVAL', '30'))

        # Store callback registry
        self.callback_registry = callback_registry

        # Threading control
        self.running = False
        self.status_thread = None

        # Home Assistant MQTT Discovery settings
        self.discovery_prefix = os.getenv('MQTT_DISCOVERY_PREFIX', 'homeassistant')
        self.device_name = os.getenv('HA_DEVICE_NAME', 'Dune Weaver')
        self.device_id = os.getenv('HA_DEVICE_ID', 'dune_weaver')
        
        # Additional topics for state
        self.running_state_topic = f"{self.device_id}/state/running"
        self.serial_state_topic = f"{self.device_id}/state/serial"
        self.pattern_select_topic = f"{self.device_id}/pattern/set"
        self.playlist_select_topic = f"{self.device_id}/playlist/set"
        self.speed_topic = f"{self.device_id}/speed/set"

        # Store current state
        self.current_file = ""
        self.is_running_state = False
        self.serial_state = ""
        self.patterns = []
        self.playlists = []

        # Initialize MQTT client if broker is configured
        if self.broker:
            self.client = mqtt.Client(client_id=self.client_id)
            self.client.on_connect = self.on_connect
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
            "name": f"Stop pattern execution",
            "unique_id": f"{self.device_id}_stop",
            "command_topic": f"{self.device_id}/command/stop",
            "device": base_device,
            "icon": "mdi:stop",
            "entity_category": "config"
        }
        self._publish_discovery("button", "stop", stop_config)

        # Pause Button
        pause_config = {
            "name": f"Pause pattern execution",
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
            "name": f"Resume pattern execution",
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
            ])
            # Publish discovery configurations
            self.setup_ha_discovery()
        elif rc == 1:
            logger.error("MQTT Connection Refused. Protocol level not supported.")
        elif rc == 2:
            logger.error("MQTT Connection Refused. The client-identifier is not allowed by the server.")
        elif rc == 3:
            logger.error("MQTT Connection Refused. The MQTT service is not available.")
        elif rc == 4:
            logger.error("MQTT Connection Refused. The data in the username or password is malformed.")
        elif rc == 5:
            logger.error("MQTT Connection Refused. The client is not authorized to connect.")
        else:
            logger.error(f"MQTT Connection Refused. Unknown error code: {rc}")

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
                            clear_pattern=self.state.clear_pattern
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
                self.callback_registry['stop']()
                # Clear both pattern and playlist selections
                self._publish_pattern_state(None)
                self._publish_playlist_state(None)
            elif msg.topic == f"{self.device_id}/command/pause":
                # Handle pause command - only if in running state
                if bool(self.state.current_playing_file) and not self.state.pause_requested:
                    self.callback_registry['pause']()
            elif msg.topic == f"{self.device_id}/command/play":
                # Handle play command - only if in paused state
                if bool(self.state.current_playing_file) and self.state.pause_requested:
                    self.callback_registry['resume']()
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
                
                # Update speed state
                self.client.publish(f"{self.speed_topic}/state", self.state.speed, retain=True)
                
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
            
            # Setup Home Assistant discovery
            self.setup_ha_discovery()
            
            logger.info("MQTT Handler started successfully")
        except Exception as e:
            logger.error(f"Failed to start MQTT Handler: {e}")

    def stop(self) -> None:
        """Stop the MQTT handler."""
        if not self.is_enabled:
            return

        self.running = False
        if self.status_thread:
            self.status_thread.join(timeout=1)
        self.client.loop_stop()
        self.client.disconnect()

    @property
    def is_enabled(self) -> bool:
        """Return whether MQTT functionality is enabled."""
        return bool(self.broker) 