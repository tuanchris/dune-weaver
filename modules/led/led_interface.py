"""
Unified LED interface for different LED control systems
Provides a common abstraction layer for pattern manager integration.
"""
from typing import Optional, Literal
from modules.led.led_controller import LEDController, effect_loading as wled_loading, effect_idle as wled_idle, effect_connected as wled_connected, effect_playing as wled_playing
from modules.led.dw_led_controller import DWLEDController, effect_loading as dw_led_loading, effect_idle as dw_led_idle, effect_connected as dw_led_connected, effect_playing as dw_led_playing


LEDProviderType = Literal["wled", "dw_leds", "none"]


class LEDInterface:
    """
    Unified interface for LED control that works with multiple backends.
    Automatically delegates to the appropriate controller based on configuration.
    """

    def __init__(self, provider: LEDProviderType = "none", ip_address: Optional[str] = None,
                 num_leds: Optional[int] = None, gpio_pin: Optional[int] = None, brightness: Optional[float] = None,
                 speed: Optional[int] = None, intensity: Optional[int] = None):
        self.provider = provider
        self._controller = None

        if provider == "wled" and ip_address:
            self._controller = LEDController(ip_address)
        elif provider == "dw_leds":
            # DW LEDs uses local GPIO, no IP needed
            num_leds = num_leds or 60
            gpio_pin = gpio_pin or 12
            brightness = brightness if brightness is not None else 0.35
            speed = speed if speed is not None else 128
            intensity = intensity if intensity is not None else 128
            self._controller = DWLEDController(num_leds, gpio_pin, brightness, speed=speed, intensity=intensity)

    @property
    def is_configured(self) -> bool:
        """Check if LED controller is configured"""
        return self._controller is not None

    def update_config(self, provider: LEDProviderType, ip_address: Optional[str] = None,
                     num_leds: Optional[int] = None, gpio_pin: Optional[int] = None, brightness: Optional[float] = None,
                     speed: Optional[int] = None, intensity: Optional[int] = None):
        """Update LED provider configuration"""
        self.provider = provider

        # Stop existing controller if switching providers
        if self._controller and hasattr(self._controller, 'stop'):
            try:
                self._controller.stop()
            except:
                pass

        if provider == "wled" and ip_address:
            self._controller = LEDController(ip_address)
        elif provider == "dw_leds":
            num_leds = num_leds or 60
            gpio_pin = gpio_pin or 12
            brightness = brightness if brightness is not None else 0.35
            speed = speed if speed is not None else 128
            intensity = intensity if intensity is not None else 128
            self._controller = DWLEDController(num_leds, gpio_pin, brightness, speed=speed, intensity=intensity)
        else:
            self._controller = None

    def effect_loading(self) -> bool:
        """Show loading effect"""
        if not self.is_configured:
            return False

        if self.provider == "wled":
            return wled_loading(self._controller)
        elif self.provider == "dw_leds":
            return dw_led_loading(self._controller)
        return False

    def effect_idle(self, effect_name: Optional[str] = None) -> bool:
        """Show idle effect"""
        if not self.is_configured:
            return False

        if self.provider == "wled":
            return wled_idle(self._controller)
        elif self.provider == "dw_leds":
            return dw_led_idle(self._controller, effect_name)
        return False

    def effect_connected(self) -> bool:
        """Show connected effect"""
        if not self.is_configured:
            return False

        if self.provider == "wled":
            return wled_connected(self._controller)
        elif self.provider == "dw_leds":
            return dw_led_connected(self._controller)
        return False

    def effect_playing(self, effect_name: Optional[str] = None) -> bool:
        """Show playing effect"""
        if not self.is_configured:
            return False

        if self.provider == "wled":
            return wled_playing(self._controller)
        elif self.provider == "dw_leds":
            return dw_led_playing(self._controller, effect_name)
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
        elif self.provider == "dw_leds":
            return self._controller.check_status()

        return {"connected": False, "message": "Unknown provider"}

    def get_controller(self):
        """Get the underlying controller instance (for advanced usage)"""
        return self._controller
