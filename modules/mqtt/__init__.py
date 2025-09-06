"""MQTT module for Dune Weaver application."""
from .factory import create_mqtt_handler
import logging

logger = logging.getLogger(__name__)
# Global MQTT handler instance
mqtt_handler = None

def init_mqtt():
    """Initialize the MQTT handler."""
    global mqtt_handler
    logger.info("initializing mqtt module")
    if mqtt_handler is None:
        mqtt_handler = create_mqtt_handler()
        mqtt_handler.start()
    return mqtt_handler

def get_mqtt_handler():
    """Get the MQTT handler instance."""
    global mqtt_handler
    if mqtt_handler is None:
        mqtt_handler = init_mqtt()
    return mqtt_handler

def cleanup_mqtt():
    """Clean up MQTT handler resources."""
    global mqtt_handler
    if mqtt_handler is not None:
        mqtt_handler.stop()
        mqtt_handler = None 