"""Factory for creating MQTT handlers."""
import os
from typing import Dict, Callable
from .base import BaseMQTTHandler
from .handler import MQTTHandler
from .mock import MockMQTTHandler
from .utils import create_mqtt_callbacks

import logging

logger = logging.getLogger(__name__)

def create_mqtt_handler() -> BaseMQTTHandler:
    """Create and return an appropriate MQTT handler based on configuration.
    
    Returns:
        BaseMQTTHandler: Either a real MQTTHandler if MQTT_BROKER is configured,
                        or a MockMQTTHandler if not.
    """
    if os.getenv('MQTT_BROKER'):
        logger.info("Got MQTT configuration, instantiating MQTTHandler")
        return MQTTHandler(create_mqtt_callbacks())
    
    logger.info("MQTT Not going to be used, instantiating MockMQTTHandler")
    return MockMQTTHandler() 