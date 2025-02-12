"""Real MQTT handler implementation."""
import os
import threading
import time
import json
from typing import Dict, Callable, List, Optional, Any
import paho.mqtt.client as mqtt
import logging

from .base import BaseMQTTHandler
from dune_weaver_flask.modules.core.state import state
from dune_weaver_flask.modules.core.pattern_manager import list_theta_rho_files
from dune_weaver_flask.modules.core.playlist_manager import list_all_playlists
from dune_weaver_flask.modules.serial.serial_manager import is_connected, get_port

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
        self.current_file_topic = f"{self.device_id}/state/current_file"
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
        self._publish_discovery("binary_sensor", "running_state", running_config)

        # Speed Control
        speed_config = {
            "name": f"{self.device_name} Speed",
            "unique_id": f"{self.device_id}_speed",
            "command_topic": self.speed_topic,
            "state_topic": f"{self.speed_topic}/state",
            "device": base_device,
            "icon": "mdi:speedometer",
            "min": 50,
            "max": 1000,
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

        # Playlist Active Sensor
        playlist_active_config = {
            "name": f"{self.device_name} Playlist Active",
            "unique_id": f"{self.device_id}_playlist_active",
            "state_topic": f"{self.device_id}/state/playlist",
            "value_template": "{{ value_json.active }}",
            "device": base_device,
            "icon": "mdi:playlist-play",
            "entity_category": "diagnostic"
        }
        self._publish_discovery("binary_sensor", "playlist_active", playlist_active_config)

    def _publish_discovery(self, component: str, config_type: str, config: dict):
        """Helper method to publish HA discovery configs."""
        if not self.is_enabled:
            return
            
        discovery_topic = f"{self.discovery_prefix}/{component}/{self.device_id}/{config_type}/config"
        self.client.publish(discovery_topic, json.dumps(config), retain=True)

    def update_state(self, is_running: Optional[bool] = None, 
                    current_file: Optional[str] = None,
                    patterns: Optional[List[str]] = None, 
                    serial: Optional[str] = None,
                    playlist: Optional[Dict[str, Any]] = None) -> None:
        """Update the state of the sand table and publish to MQTT."""
        if not self.is_enabled:
            return

        if is_running is not None:
            self.is_running_state = is_running
            self.client.publish(self.running_state_topic, "ON" if is_running else "OFF", retain=True)
        
        if current_file is not None:
            if current_file:  # Only publish if there's actually a file
                # Extract just the filename without path and normalize it 
                if current_file.startswith('./patterns/'):
                    file_name = current_file[len('./patterns/'):]
                else:
                    file_name = current_file.split("/")[-1].split("\\")[-1]
                
                self.current_file = file_name
                # Update both the current file topic and the pattern select state
                self.client.publish(self.current_file_topic, file_name, retain=True)
                self.client.publish(f"{self.pattern_select_topic}/state", file_name, retain=True)
            else:
                # Clear both states when no file is playing
                self.client.publish(self.current_file_topic, "", retain=True)
                self.client.publish(f"{self.pattern_select_topic}/state", "", retain=True)

        if patterns is not None:
            # Only proceed if patterns have actually changed
            if set(patterns) != set(self.patterns):
                self.patterns = patterns
                # Republish discovery config with updated pattern options
                self.setup_ha_discovery()
        
        if serial is not None:
            # Format serial state as "connected to <port>" or "disconnected"
            if "connected" in serial.lower():
                port = serial.split(" ")[-1]  # Extract port from status message
                formatted_state = f"connected to {port}"
            else:
                formatted_state = "disconnected"
            
            self.serial_state = formatted_state
            self.client.publish(self.serial_state_topic, formatted_state, retain=True)
        
        if playlist is not None:
            # Update playlist list if needed
            if playlist.get('all_playlists'):
                self.playlists = playlist['all_playlists']
                self.setup_ha_discovery()  # Republish discovery to update playlist options
            
            # Publish playlist active state
            self.client.publish(f"{self.device_id}/state/playlist", json.dumps({
                "active": bool(playlist.get('current_playlist')),
            }), retain=True)
            
            # Update playlist select state if a playlist is active
            if playlist.get('current_playlist'):
                current_playlist_name = playlist['current_playlist'][0]  # Use first file as playlist name
                self.client.publish(f"{self.playlist_select_topic}/state", current_playlist_name, retain=True)
            else:
                self.client.publish(f"{self.playlist_select_topic}/state", "", retain=True)

    def on_connect(self, client, userdata, flags, rc):
        """Callback when connected to MQTT broker."""
        logger.info(f"Connected to MQTT broker with result code {rc}")
        # Subscribe to command topics
        client.subscribe([
            (self.command_topic, 0),
            (self.pattern_select_topic, 0),
            (self.playlist_select_topic, 0),
            (self.speed_topic, 0)
        ])
        # Publish discovery configurations
        self.setup_ha_discovery()

    def on_message(self, client, userdata, msg):
        """Callback when message is received."""
        try:
            if msg.topic == self.pattern_select_topic:
                # Handle pattern selection
                pattern_name = msg.payload.decode()
                if pattern_name in self.patterns:
                    self.callback_registry['run_pattern'](file_path=f"{pattern_name}")
                    self.client.publish(f"{self.pattern_select_topic}/state", pattern_name, retain=True)
            elif msg.topic == self.playlist_select_topic:
                # Handle playlist selection
                playlist_name = msg.payload.decode()
                if playlist_name in self.playlists:
                    self.callback_registry['run_playlist'](playlist_name=playlist_name)
                    self.client.publish(f"{self.playlist_select_topic}/state", playlist_name, retain=True)
            elif msg.topic == self.speed_topic:
                speed = int(msg.payload.decode())
                self.callback_registry['set_speed'](speed)
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
                # Create status message
                is_running = bool(state.current_playing_file) and not state.stop_requested
                status = {
                    "status": "running" if is_running else "idle",
                    "timestamp": time.time(),
                    "client_id": self.client_id,
                    "current_file": state.current_playing_file or '',
                    "speed": state.speed,
                    "position": {
                        "theta": state.current_theta,
                        "rho": state.current_rho,
                        "x": state.machine_x,
                        "y": state.machine_y
                    }
                }
                logger.info(f"publishing status: {status}" )
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
            
            # Get initial states from modules
            is_running = bool(state.current_playing_file) and not state.stop_requested
            serial_connected = is_connected()
            serial_port = get_port() if serial_connected else None
            patterns = list_theta_rho_files()
            playlists = list_all_playlists()

            # Wait a bit for MQTT connection to establish
            time.sleep(1)

            # Publish initial state
            status = {
                "status": "running" if is_running else "idle",
                "timestamp": time.time(),
                "client_id": self.client_id,
                "current_file": state.current_playing_file or ''
            }
            self.client.publish(self.status_topic, json.dumps(status), retain=True)
            self.client.publish(self.running_state_topic, 
                              "ON" if is_running else "OFF", 
                              retain=True)
            
            # Format and publish serial state
            serial_status = f"connected to {serial_port}" if serial_connected else "disconnected"
            self.client.publish(self.serial_state_topic, serial_status, retain=True)
            
            # Update and publish pattern list
            self.patterns = patterns
            
            # Update and publish playlist list
            self.playlists = playlists
            
            # Get and publish playlist state
            playlist_info = None
            if state.current_playlist:
                playlist_info = {
                    'current_playlist': state.current_playlist
                }
            
            self.client.publish(f"{self.device_id}/state/playlist", json.dumps({
                "active": bool(playlist_info)
            }), retain=True)

            # Update playlist select state if a playlist is active
            if playlist_info and playlist_info['current_playlist']:
                current_playlist_name = playlist_info['current_playlist'][0]
                self.client.publish(f"{self.playlist_select_topic}/state", current_playlist_name, retain=True)
            else:
                self.client.publish(f"{self.playlist_select_topic}/state", "", retain=True)

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