"""
Unified LED interface for different LED control systems (WLED, Hyperion, etc.)
Provides a common abstraction layer for pattern manager integration.
"""
from typing import Optional, Literal
from modules.led.led_controller import LEDController, effect_loading as wled_loading, effect_idle as wled_idle, effect_connected as wled_connected, effect_playing as wled_playing
from modules.led.hyperion_controller import HyperionController, effect_loading as hyperion_loading, effect_idle as hyperion_idle, effect_connected as hyperion_connected, effect_playing as hyperion_playing


LEDProviderType = Literal["wled", "hyperion", "none"]


class LEDInterface:
    """
    Unified interface for LED control that works with multiple backends.
    Automatically delegates to the appropriate controller based on configuration.
    """

    def __init__(self, provider: LEDProviderType = "none", ip_address: Optional[str] = None, port: Optional[int] = None):
        self.provider = provider
        self._controller = None

        if provider == "wled" and ip_address:
            self._controller = LEDController(ip_address)
        elif provider == "hyperion" and ip_address:
            port = port or 8090  # Default Hyperion port
            self._controller = HyperionController(ip_address, port)

    @property
    def is_configured(self) -> bool:
        """Check if LED controller is configured"""
        return self._controller is not None

    def update_config(self, provider: LEDProviderType, ip_address: Optional[str] = None, port: Optional[int] = None):
        """Update LED provider configuration"""
        self.provider = provider

        if provider == "wled" and ip_address:
            self._controller = LEDController(ip_address)
        elif provider == "hyperion" and ip_address:
            port = port or 8090
            self._controller = HyperionController(ip_address, port)
        else:
            self._controller = None

    def effect_loading(self) -> bool:
        """Show loading effect"""
        if not self.is_configured:
            return False

        if self.provider == "wled":
            return wled_loading(self._controller)
        elif self.provider == "hyperion":
            return hyperion_loading(self._controller)
        return False

    def effect_idle(self, effect_name: Optional[str] = None) -> bool:
        """Show idle effect"""
        if not self.is_configured:
            return False

        if self.provider == "wled":
            return wled_idle(self._controller)
        elif self.provider == "hyperion":
            return hyperion_idle(self._controller, effect_name)
        return False

    def effect_connected(self) -> bool:
        """Show connected effect"""
        if not self.is_configured:
            return False

        if self.provider == "wled":
            return wled_connected(self._controller)
        elif self.provider == "hyperion":
            return hyperion_connected(self._controller)
        return False

    def effect_playing(self, effect_name: Optional[str] = None) -> bool:
        """Show playing effect"""
        if not self.is_configured:
            return False

        if self.provider == "wled":
            return wled_playing(self._controller)
        elif self.provider == "hyperion":
            return hyperion_playing(self._controller, effect_name)
        return False

    def set_power(self, state: int) -> dict:
        """Set power state (0=Off, 1=On, 2=Toggle)"""
        if not self.is_configured:
            return {"connected": False, "message": "No LED controller configured"}

        return self._controller.set_power(state)

    def check_status(self) -> dict:
        """Check controller status"""
        if not self.is_configured:
            return {"connected": False, "message": "No LED controller configured"}

        if self.provider == "wled":
            return self._controller.check_wled_status()
        elif self.provider == "hyperion":
            return self._controller.check_hyperion_status()

        return {"connected": False, "message": "Unknown provider"}

    def get_controller(self):
        """Get the underlying controller instance (for advanced usage)"""
        return self._controller
