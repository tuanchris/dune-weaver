"""
Unified LED interface for different LED control systems
Provides a common abstraction layer for pattern manager integration.
"""
import asyncio
from typing import Optional, Literal
from modules.led.led_controller import LEDController, effect_loading as wled_loading, effect_idle as wled_idle, effect_connected as wled_connected, effect_playing as wled_playing
from modules.led.board_led_controller import BoardLEDController

LEDProviderType = Literal["wled", "board", "none"]


class LEDInterface:
    """
    Unified interface for LED control that works with multiple backends.
    Automatically delegates to the appropriate controller based on configuration.
    """

    def __init__(self, provider: LEDProviderType = "none", ip_address: Optional[str] = None,
                 num_leds: Optional[int] = None, gpio_pin: Optional[int] = None, pixel_order: Optional[str] = None,
                 brightness: Optional[float] = None, speed: Optional[int] = None, intensity: Optional[int] = None):
        self.provider = provider
        self._controller = None

        if provider == "wled" and ip_address:
            self._controller = LEDController(ip_address)
        elif provider == "board":
            # The table's own LED ring, driven by the FluidNC firmware.
            self._controller = BoardLEDController()

    @property
    def is_configured(self) -> bool:
        """Check if LED controller is configured"""
        return self._controller is not None

    def update_config(self, provider: LEDProviderType, ip_address: Optional[str] = None,
                     num_leds: Optional[int] = None, gpio_pin: Optional[int] = None, pixel_order: Optional[str] = None,
                     brightness: Optional[float] = None, speed: Optional[int] = None, intensity: Optional[int] = None):
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
        elif provider == "board":
            self._controller = BoardLEDController()
        else:
            self._controller = None

    # NOTE: for the "board" provider the effect_* transition hooks below fall
    # through to False on purpose — the firmware switches run/idle effects
    # itself ($LED/RunEffect / $LED/IdleEffect); the host must not fight it.

    def effect_loading(self) -> bool:
        """Show loading effect"""
        if not self.is_configured:
            return False

        if self.provider == "wled":
            return wled_loading(self._controller)
        return False

    def effect_idle(self, effect_name: Optional[str] = None) -> bool:
        """Show idle effect"""
        if not self.is_configured:
            return False

        if self.provider == "wled":
            return wled_idle(self._controller)
        return False

    def effect_connected(self) -> bool:
        """Show connected effect"""
        if not self.is_configured:
            return False

        if self.provider == "wled":
            return wled_connected(self._controller)
        return False

    def effect_playing(self, effect_name: Optional[str] = None) -> bool:
        """Show playing effect"""
        if not self.is_configured:
            return False

        if self.provider == "wled":
            return wled_playing(self._controller)
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
        elif self.provider == "board":
            return self._controller.check_status()

        return {"connected": False, "message": "Unknown provider"}

    def get_controller(self):
        """Get the underlying controller instance (for advanced usage)"""
        return self._controller

    # Async versions of methods for non-blocking calls from async context
    # These use asyncio.to_thread() to avoid blocking the event loop

    async def effect_loading_async(self) -> bool:
        """Show loading effect (non-blocking)"""
        return await asyncio.to_thread(self.effect_loading)

    async def effect_idle_async(self, effect_name: Optional[str] = None) -> bool:
        """Show idle effect (non-blocking)"""
        return await asyncio.to_thread(self.effect_idle, effect_name)

    async def effect_connected_async(self) -> bool:
        """Show connected effect (non-blocking)"""
        return await asyncio.to_thread(self.effect_connected)

    async def effect_playing_async(self, effect_name: Optional[str] = None) -> bool:
        """Show playing effect (non-blocking)"""
        return await asyncio.to_thread(self.effect_playing, effect_name)

    async def set_power_async(self, state: int) -> dict:
        """Set power state (non-blocking)"""
        return await asyncio.to_thread(self.set_power, state)

    async def check_status_async(self) -> dict:
        """Check controller status (non-blocking)"""
        return await asyncio.to_thread(self.check_status)
