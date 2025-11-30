"""Factory for creating MQTT handlers."""
import os
from typing import Dict, Callable
from dotenv import load_dotenv
from pathlib import Path
from .base import BaseMQTTHandler
from .handler import MQTTHandler
from .mock import MockMQTTHandler
from .utils import create_mqtt_callbacks
from modules.core.state import state

import logging

logger = logging.getLogger(__name__)

# Load environment variables (fallback for legacy .env configuration)
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # Go up to project root
env_path = os.path.join(BASE_DIR, '.env')
load_dotenv(env_path)

def create_mqtt_handler() -> BaseMQTTHandler:
    """Create and return an appropriate MQTT handler based on configuration.

    Configuration is read from state (UI settings) first, with fallback to
    environment variables for legacy .env file support.

    Returns:
        BaseMQTTHandler: Either a real MQTTHandler if MQTT is enabled and configured,
                        or a MockMQTTHandler if not.
    """
    # Check state-based configuration first (from UI settings)
    if state.mqtt_enabled and state.mqtt_broker:
        logger.info(f"Got MQTT configuration from state for broker: {state.mqtt_broker}, instantiating MQTTHandler")
        return MQTTHandler(create_mqtt_callbacks())

    # Fallback to environment variable for legacy support
    mqtt_broker = os.getenv('MQTT_BROKER')
    if mqtt_broker:
        logger.info(f"Got MQTT configuration from env for broker: {mqtt_broker}, instantiating MQTTHandler")
        return MQTTHandler(create_mqtt_callbacks())

    logger.info("MQTT not enabled or not configured, instantiating MockMQTTHandler")
    return MockMQTTHandler() 