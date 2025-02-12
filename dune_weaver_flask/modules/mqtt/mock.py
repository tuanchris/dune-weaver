"""Mock MQTT handler implementation."""
from typing import Dict, Callable
from .base import BaseMQTTHandler
from dune_weaver_flask.modules.core.state import state



class MockMQTTHandler(BaseMQTTHandler):
    """Mock implementation of MQTT handler that does nothing."""
    
    def start(self) -> None:
        """No-op start."""
        pass
    
    def stop(self) -> None:
        """No-op stop."""
        pass
    
    def update_state(self, **kwargs) -> None:
        """No-op state update."""
        pass
    
    @property
    def is_enabled(self) -> bool:
        """Always returns False since this is a mock."""
        return False
        
    def publish_status(self) -> None:
        """Mock status publisher."""
        pass
        
    def setup_ha_discovery(self) -> None:
        """Mock discovery setup."""
        pass 