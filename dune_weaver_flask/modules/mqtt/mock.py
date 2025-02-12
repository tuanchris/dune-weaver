"""Mock MQTT handler implementation."""
from .base import BaseMQTTHandler



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