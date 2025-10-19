"""
Dune Weaver LED Controller - Embedded NeoPixel LED controller for Raspberry Pi
Provides direct GPIO control of WS2812B LED strips with beautiful effects
"""
import threading
import time
import logging
from typing import Optional, Dict, List, Tuple
from .dw_leds.segment import Segment
from .dw_leds.effects.basic_effects import get_effect, get_all_effects, FRAMETIME
from .dw_leds.utils.palettes import get_palette_name, PALETTE_NAMES
from .dw_leds.utils.colors import rgb_to_color

logger = logging.getLogger(__name__)


class DWLEDController:
    """Dune Weaver LED Controller for NeoPixel LED strips"""

    def __init__(self, num_leds: int = 60, gpio_pin: int = 12, brightness: float = 0.35,
                 pixel_order: str = "GRB"):
        """
        Initialize Dune Weaver LED controller

        Args:
            num_leds: Number of LEDs in the strip
            gpio_pin: GPIO pin number (BCM numbering: 12, 13, 18, or 19)
            brightness: Global brightness (0.0 - 1.0)
            pixel_order: Pixel color order (GRB, RGB, RGBW, GRBW)
        """
        self.num_leds = num_leds
        self.gpio_pin = gpio_pin
        self.brightness = brightness
        self.pixel_order = pixel_order

        # State
        self._powered_on = False
        self._current_effect_id = 0
        self._current_palette_id = 0
        self._speed = 128
        self._intensity = 128
        self._color1 = (255, 0, 0)  # Red
        self._color2 = (0, 0, 255)  # Blue
        self._color3 = (0, 255, 0)  # Green

        # Threading
        self._pixels = None
        self._segment = None
        self._effect_thread = None
        self._stop_thread = threading.Event()
        self._lock = threading.Lock()
        self._initialized = False
        self._init_error = None  # Store initialization error message

    def _initialize_hardware(self):
        """Lazy initialization of NeoPixel hardware"""
        if self._initialized:
            return True

        try:
            import board
            import neopixel

            # Map GPIO pin numbers to board pins
            pin_map = {
                12: board.D12,
                13: board.D13,
                18: board.D18,
                19: board.D19
            }

            if self.gpio_pin not in pin_map:
                error_msg = f"Invalid GPIO pin {self.gpio_pin}. Must be 12, 13, 18, or 19 (PWM-capable pins)"
                self._init_error = error_msg
                logger.error(error_msg)
                return False

            board_pin = pin_map[self.gpio_pin]

            # Initialize NeoPixel strip
            self._pixels = neopixel.NeoPixel(
                board_pin,
                self.num_leds,
                brightness=self.brightness,
                auto_write=False,
                pixel_order=self.pixel_order
            )

            # Create segment for the entire strip
            self._segment = Segment(self._pixels, 0, self.num_leds)
            self._segment.speed = self._speed
            self._segment.intensity = self._intensity
            self._segment.palette_id = self._current_palette_id

            # Set colors
            self._segment.colors[0] = rgb_to_color(*self._color1)
            self._segment.colors[1] = rgb_to_color(*self._color2)
            self._segment.colors[2] = rgb_to_color(*self._color3)

            self._initialized = True
            logger.info(f"DW LEDs initialized: {self.num_leds} LEDs on GPIO {self.gpio_pin}")
            return True

        except ImportError as e:
            error_msg = f"Failed to import NeoPixel libraries: {e}. Make sure adafruit-circuitpython-neopixel and Adafruit-Blinka are installed."
            self._init_error = error_msg
            logger.error(error_msg)
            return False
        except Exception as e:
            error_msg = f"Failed to initialize NeoPixel hardware: {e}"
            self._init_error = error_msg
            logger.error(error_msg)
            return False

    def _effect_loop(self):
        """Background thread that runs the current effect"""
        effect_func = get_effect(self._current_effect_id)

        while not self._stop_thread.is_set():
            try:
                with self._lock:
                    if self._pixels and self._segment and self._powered_on:
                        # Run effect and get delay
                        delay_ms = effect_func(self._segment)

                        # Update pixels
                        self._pixels.show()

                        # Increment call counter
                        self._segment.call += 1
                    else:
                        delay_ms = 100  # Idle delay when off

                # Sleep for the effect's requested delay
                time.sleep(delay_ms / 1000.0)

            except Exception as e:
                logger.error(f"Error in effect loop: {e}")
                time.sleep(0.1)

    def set_power(self, state: int) -> Dict:
        """
        Set power state

        Args:
            state: 0=Off, 1=On, 2=Toggle

        Returns:
            Dict with status
        """
        if not self._initialize_hardware():
            return {
                "connected": False,
                "error": self._init_error or "Failed to initialize LED hardware"
            }

        with self._lock:
            if state == 2:  # Toggle
                self._powered_on = not self._powered_on
            else:
                self._powered_on = bool(state)

            # Turn off all pixels immediately when powering off
            if not self._powered_on and self._pixels:
                self._pixels.fill((0, 0, 0))
                self._pixels.show()

            # Start effect thread if not running
            if self._powered_on and (self._effect_thread is None or not self._effect_thread.is_alive()):
                self._stop_thread.clear()
                self._effect_thread = threading.Thread(target=self._effect_loop, daemon=True)
                self._effect_thread.start()

        return {
            "connected": True,
            "power_on": self._powered_on,
            "message": f"Power {'on' if self._powered_on else 'off'}"
        }

    def set_brightness(self, value: int) -> Dict:
        """
        Set global brightness

        Args:
            value: Brightness 0-100

        Returns:
            Dict with status
        """
        if not self._initialized:
            if not self._initialize_hardware():
                return {"connected": False, "error": self._init_error or "Hardware not initialized"}

        brightness = max(0.0, min(1.0, value / 100.0))

        with self._lock:
            self.brightness = brightness
            if self._pixels:
                self._pixels.brightness = brightness

        return {
            "connected": True,
            "brightness": int(brightness * 100),
            "message": "Brightness updated"
        }

    def set_color(self, r: int, g: int, b: int) -> Dict:
        """
        Set solid color (sets effect to Static and color1)

        Args:
            r, g, b: RGB values 0-255

        Returns:
            Dict with status
        """
        if not self._initialized:
            if not self._initialize_hardware():
                return {"connected": False, "error": self._init_error or "Hardware not initialized"}

        with self._lock:
            self._color1 = (r, g, b)
            if self._segment:
                self._segment.colors[0] = rgb_to_color(r, g, b)
                # Switch to static effect
                self._current_effect_id = 0
                self._segment.reset()

        return {
            "connected": True,
            "color": [r, g, b],
            "message": "Color set"
        }

    def set_effect(self, effect_id: int, speed: Optional[int] = None,
                   intensity: Optional[int] = None) -> Dict:
        """
        Set active effect

        Args:
            effect_id: Effect ID (0-15)
            speed: Optional speed override (0-255)
            intensity: Optional intensity override (0-255)

        Returns:
            Dict with status
        """
        if not self._initialized:
            if not self._initialize_hardware():
                return {"connected": False, "error": self._init_error or "Hardware not initialized"}

        # Validate effect ID
        effects = get_all_effects()
        if not any(eid == effect_id for eid, _ in effects):
            return {
                "connected": False,
                "message": f"Invalid effect ID: {effect_id}"
            }

        with self._lock:
            self._current_effect_id = effect_id

            if speed is not None:
                self._speed = max(0, min(255, speed))
                if self._segment:
                    self._segment.speed = self._speed

            if intensity is not None:
                self._intensity = max(0, min(255, intensity))
                if self._segment:
                    self._segment.intensity = self._intensity

            # Reset effect state
            if self._segment:
                self._segment.reset()

        effect_name = next(name for eid, name in effects if eid == effect_id)
        return {
            "connected": True,
            "effect_id": effect_id,
            "effect_name": effect_name,
            "message": f"Effect set to {effect_name}"
        }

    def set_palette(self, palette_id: int) -> Dict:
        """
        Set color palette

        Args:
            palette_id: Palette ID (0-58)

        Returns:
            Dict with status
        """
        if not self._initialized:
            if not self._initialize_hardware():
                return {"connected": False, "error": self._init_error or "Hardware not initialized"}

        if palette_id < 0 or palette_id >= len(PALETTE_NAMES):
            return {
                "connected": False,
                "message": f"Invalid palette ID: {palette_id}"
            }

        with self._lock:
            self._current_palette_id = palette_id
            if self._segment:
                self._segment.palette_id = palette_id

        palette_name = get_palette_name(palette_id)
        return {
            "connected": True,
            "palette_id": palette_id,
            "palette_name": palette_name,
            "message": f"Palette set to {palette_name}"
        }

    def set_speed(self, speed: int) -> Dict:
        """Set effect speed (0-255)"""
        if not self._initialized:
            if not self._initialize_hardware():
                return {"connected": False, "error": self._init_error or "Hardware not initialized"}

        speed = max(0, min(255, speed))

        with self._lock:
            self._speed = speed
            if self._segment:
                self._segment.speed = speed

        return {
            "connected": True,
            "speed": speed,
            "message": "Speed updated"
        }

    def set_intensity(self, intensity: int) -> Dict:
        """Set effect intensity (0-255)"""
        if not self._initialized:
            if not self._initialize_hardware():
                return {"connected": False, "error": self._init_error or "Hardware not initialized"}

        intensity = max(0, min(255, intensity))

        with self._lock:
            self._intensity = intensity
            if self._segment:
                self._segment.intensity = intensity

        return {
            "connected": True,
            "intensity": intensity,
            "message": "Intensity updated"
        }

    def get_effects(self) -> List[Tuple[int, str]]:
        """Get list of all available effects"""
        return get_all_effects()

    def get_palettes(self) -> List[Tuple[int, str]]:
        """Get list of all available palettes"""
        return [(i, name) for i, name in enumerate(PALETTE_NAMES)]

    def check_status(self) -> Dict:
        """Get current controller status"""
        status = {
            "connected": self._initialized,
            "power_on": self._powered_on,
            "num_leds": self.num_leds,
            "gpio_pin": self.gpio_pin,
            "brightness": int(self.brightness * 100),
            "current_effect": self._current_effect_id,
            "current_palette": self._current_palette_id,
            "speed": self._speed,
            "intensity": self._intensity,
            "effect_running": self._effect_thread is not None and self._effect_thread.is_alive()
        }

        # Include error message if not initialized
        if not self._initialized and self._init_error:
            status["error"] = self._init_error

        return status

    def stop(self):
        """Stop the effect loop and cleanup"""
        self._stop_thread.set()
        if self._effect_thread and self._effect_thread.is_alive():
            self._effect_thread.join(timeout=1.0)

        with self._lock:
            if self._pixels:
                self._pixels.fill((0, 0, 0))
                self._pixels.show()
                self._pixels.deinit()
            self._pixels = None
            self._segment = None
            self._initialized = False


# Helper functions for pattern manager integration
def effect_loading(controller: DWLEDController) -> bool:
    """Show loading effect (Rainbow Cycle)"""
    try:
        controller.set_power(1)
        controller.set_effect(8, speed=100)  # Rainbow Cycle
        return True
    except Exception as e:
        logger.error(f"Error setting loading effect: {e}")
        return False


def effect_idle(controller: DWLEDController, effect_name: Optional[str] = None) -> bool:
    """Show idle effect"""
    try:
        if effect_name and effect_name.lower() != "off":
            # Try to find effect by name
            effects = controller.get_effects()
            for eid, name in effects:
                if name.lower() == effect_name.lower():
                    controller.set_power(1)
                    controller.set_effect(eid)
                    return True

        # Default: turn off
        controller.set_power(0)
        return True
    except Exception as e:
        logger.error(f"Error setting idle effect: {e}")
        return False


def effect_connected(controller: DWLEDController) -> bool:
    """Show connected effect (green flash)"""
    try:
        controller.set_power(1)
        controller.set_color(0, 255, 0)  # Green
        controller.set_effect(1, speed=200, intensity=128)  # Blink effect
        time.sleep(1.0)
        return True
    except Exception as e:
        logger.error(f"Error setting connected effect: {e}")
        return False


def effect_playing(controller: DWLEDController, effect_name: Optional[str] = None) -> bool:
    """Show playing effect"""
    try:
        if effect_name and effect_name.lower() != "off":
            # Try to find effect by name
            effects = controller.get_effects()
            for eid, name in effects:
                if name.lower() == effect_name.lower():
                    controller.set_power(1)
                    controller.set_effect(eid)
                    return True
        else:
            # Default: turn off
            controller.set_power(0)
        return True
    except Exception as e:
        logger.error(f"Error setting playing effect: {e}")
        return False
