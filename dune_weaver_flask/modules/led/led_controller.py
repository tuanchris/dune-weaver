import platform
import time
import logging
import threading
import colorsys
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class BaseLEDController(ABC):
    """Base class for LED strip controller"""
    
    @abstractmethod
    def set_color(self, color):
        """Set color for all LEDs"""
        pass
    
    @abstractmethod
    def set_brightness(self, brightness):
        """Set brightness (0-255)"""
        pass
    
    @abstractmethod
    def start_animation(self, animation_type):
        """Start animation"""
        pass
    
    @abstractmethod
    def stop_current_animation(self):
        """Stop current animation"""
        pass
    
    @abstractmethod
    def set_animation_speed(self, speed):
        """Set animation speed (1-100)"""
        pass
    
    @abstractmethod
    def get_status(self):
        """Get current status"""
        pass

    @abstractmethod
    def turn_on(self):
        """Turn on the LED strip"""
        pass

    @abstractmethod
    def turn_off(self):
        """Turn off the LED strip"""
        pass

    @abstractmethod
    def startup_indication(self):
        """System startup indication"""
        pass


class MockLEDController(BaseLEDController):
    """Mock version of controller for development on non-Raspberry Pi systems"""
    
    def __init__(self, led_count=47):
        self.led_count = led_count
        self.current_color = (0, 0, 0)
        self.brightness = 255
        self.animation_speed = 50
        self.current_animation = None
        self.animation_thread = None
        self.stop_animation = False
        self.is_on = False
        logger.info(f"[MOCK] Initialized LED controller with {led_count} LEDs")
    
    def set_color(self, color):
        self.current_color = color
        logger.info(f"[MOCK] Color set to: RGB{color}")
        return True
    
    def set_brightness(self, brightness):
        self.brightness = max(0, min(255, brightness))
        logger.info(f"[MOCK] Brightness set to: {self.brightness}")
        return True
    
    def start_animation(self, animation_type):
        animations = ['rainbow', 'wave', 'fade']
        if animation_type not in animations:
            logger.info(f"[MOCK] Error: unknown animation type {animation_type}")
            return False
        
        self.stop_current_animation()
        self.current_animation = animation_type
        logger.info(f"[MOCK] Animation started: {animation_type}")
        
        def mock_animation():
            logger.info(f"[MOCK] Animation {animation_type} is running...")
            while not self.stop_animation:
                time.sleep(self.animation_speed / 100.0)
        
        self.stop_animation = False
        self.animation_thread = threading.Thread(target=mock_animation)
        self.animation_thread.start()
        return True
    
    def stop_current_animation(self):
        if self.animation_thread and self.animation_thread.is_alive():
            self.stop_animation = True
            self.animation_thread.join()
            logger.info("[MOCK] Animation stopped")
        self.current_animation = None
        return True
    
    def set_animation_speed(self, speed):
        self.animation_speed = max(1, min(100, speed))
        logger.info(f"[MOCK] Animation speed set to: {self.animation_speed}")
        return True
    
    def turn_on(self):
        self.is_on = True
        logger.info("[MOCK] LED strip turned on")
        return True

    def turn_off(self):
        self.is_on = False
        self.stop_current_animation()
        logger.info("[MOCK] LED strip turned off")
        return True

    def get_status(self):
        return {
            'current_animation': self.current_animation,
            'brightness': self.brightness,
            'animation_speed': self.animation_speed,
            'current_color': self.current_color,
            'mode': 'mock',
            'is_on': self.is_on
        }

    def startup_indication(self):
        """Mock version of startup indication"""
        logger.info("[MOCK] Performing startup indication: green -> blue -> red")
        return True


class RaspberryLEDController(BaseLEDController):
    """Real controller version for Raspberry Pi"""
    
    def __init__(self, led_count=47, led_pin=18, led_freq_hz=800000, led_dma=10, led_brightness=255, led_channel=0):
        try:
            from rpi_ws281x import PixelStrip, Color
            self.Color = Color
            self.strip = PixelStrip(led_count, led_pin, led_freq_hz, led_dma, False, led_brightness, led_channel)
            self.strip.begin()
            self.animation_thread = None
            self.stop_animation = False
            self.current_animation = None
            self.animation_speed = 50
            self.brightness = led_brightness
            self.is_on = False
            self.last_color = (0, 0, 0)
            logger.info(f"Initialized LED controller with {led_count} LEDs")
        except ImportError:
            raise ImportError("rpi_ws281x library is not installed. Install it using pip install rpi-ws281x")
        except Exception as e:
            raise Exception(f"LED controller initialization error: {str(e)}")

    def set_color(self, color):
        self.last_color = color
        if not self.is_on:
            return True
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, self.Color(*color))
        self.strip.show()
        return True

    def set_brightness(self, brightness):
        self.brightness = brightness
        self.strip.setBrightness(brightness)
        self.strip.show()
        return True

    def _rainbow_cycle(self):
        while not self.stop_animation:
            for j in range(256):
                if self.stop_animation:
                    break
                for i in range(self.strip.numPixels()):
                    pos = (i * 256 // self.strip.numPixels() + j) & 255
                    r, g, b = [int(x * 255) for x in colorsys.hsv_to_rgb(pos/256.0, 1.0, 1.0)]
                    self.strip.setPixelColor(i, self.Color(r, g, b))
                self.strip.show()
                time.sleep(self.animation_speed / 1000.0)

    def _wave(self):
        while not self.stop_animation:
            for i in range(self.strip.numPixels() * 2):
                if self.stop_animation:
                    break
                for j in range(self.strip.numPixels()):
                    pos = (i + j) % self.strip.numPixels()
                    r, g, b = [int(x * 255) for x in colorsys.hsv_to_rgb(pos/float(self.strip.numPixels()), 1.0, 1.0)]
                    self.strip.setPixelColor(j, self.Color(r, g, b))
                self.strip.show()
                time.sleep(self.animation_speed / 1000.0)

    def _fade(self):
        while not self.stop_animation:
            for i in range(256):
                if self.stop_animation:
                    break
                self.strip.setBrightness(i)
                self.strip.show()
                time.sleep(self.animation_speed / 1000.0)
            
            for i in range(255, -1, -1):
                if self.stop_animation:
                    break
                self.strip.setBrightness(i)
                self.strip.show()
                time.sleep(self.animation_speed / 1000.0)

    def start_animation(self, animation_type):
        self.stop_animation = True
        if self.animation_thread:
            self.animation_thread.join()
        
        self.stop_animation = False
        animation_map = {
            'rainbow': self._rainbow_cycle,
            'wave': self._wave,
            'fade': self._fade
        }
        
        if animation_type in animation_map:
            self.current_animation = animation_type
            self.animation_thread = threading.Thread(target=animation_map[animation_type])
            self.animation_thread.start()
            return True
        return False

    def stop_current_animation(self):
        self.stop_animation = True
        if self.animation_thread:
            self.animation_thread.join()
        self.current_animation = None
        return True

    def set_animation_speed(self, speed):
        self.animation_speed = max(1, min(100, speed))
        return True

    def turn_on(self):
        self.is_on = True
        # Restore last color
        self.set_color(self.last_color)
        return True

    def turn_off(self):
        self.is_on = False
        self.stop_current_animation()
        # Save current color before turning off
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i, self.Color(0, 0, 0))
        self.strip.show()
        return True

    def get_status(self):
        return {
            'current_animation': self.current_animation,
            'brightness': self.brightness,
            'animation_speed': self.animation_speed,
            'mode': 'raspberry',
            'is_on': self.is_on
        }

    def startup_indication(self):
        """System startup indication: smooth blinking in green, blue, and red"""
        logger.info("Starting LED startup indication...")
        colors = [(0, 255, 0), (0, 0, 255), (255, 0, 0)]  # Green, blue, red
        steps = 50  # Number of steps for smooth transition
        delay = 0.02  # Delay between steps (in seconds)

        # Turn on the strip if it's off
        self.is_on = True
        logger.info("LED strip turned on")

        for i, color in enumerate(colors):
            logger.info(f"Showing color {i+1}/3: RGB{color}")
            # Smooth fade in
            for i in range(steps):
                brightness = int((i / steps) * 255)
                r = int((color[0] / 255) * brightness)
                g = int((color[1] / 255) * brightness)
                b = int((color[2] / 255) * brightness)
                self.set_color((r, g, b))
                time.sleep(delay)
            
            # Smooth fade out
            for i in range(steps, -1, -1):
                brightness = int((i / steps) * 255)
                r = int((color[0] / 255) * brightness)
                g = int((color[1] / 255) * brightness)
                b = int((color[2] / 255) * brightness)
                self.set_color((r, g, b))
                time.sleep(delay)

        # Turn off the strip after indication
        self.set_color((0, 0, 0))
        logger.info("LED startup indication completed")
        return True


def create_led_controller(led_count=47, **kwargs):
    """Factory method to create appropriate controller"""
    if platform.system() == 'Linux' and (platform.machine().startswith('arm') or platform.machine().startswith('aarch64')):
        try:
            return RaspberryLEDController(led_count=led_count, **kwargs)
        except Exception as e:
            logger.error(f"Error creating Raspberry Pi controller: {e}")
            logger.error("Switching to mock version...")
            return MockLEDController(led_count=led_count)
    else:
        return MockLEDController(led_count=led_count)
    
