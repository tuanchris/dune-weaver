"""Base MQTT handler interface."""
from abc import ABC, abstractmethod
from typing import Dict, Callable, List, Optional, Any

class BaseMQTTHandler(ABC):
    """Abstract base class for MQTT handlers."""
    
    @abstractmethod
    def start(self) -> None:
        """Start the MQTT handler."""
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """Stop the MQTT handler."""
        pass
    
    @abstractmethod
    def update_state(self, is_running: Optional[bool] = None, 
                    current_file: Optional[str] = None,
                    patterns: Optional[List[str]] = None, 
                    serial: Optional[str] = None,
                    playlist: Optional[Dict[str, Any]] = None) -> None:
        """Update the state of the sand table and publish to MQTT.
        
        Args:
            is_running: Whether the table is currently running a pattern
            current_file: The currently playing file
            patterns: List of available pattern files
            serial: Serial connection status
            playlist: Current playlist information if in playlist mode
        """
        pass
    
    @property
    @abstractmethod
    def is_enabled(self) -> bool:
        """Return whether MQTT functionality is enabled."""
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Return whether MQTT client is connected to the broker."""
        pass