"""
Ball Tracking LED Manager
Tracks the ball bearing's position and updates LEDs in real-time to follow its movement.
"""
import asyncio
import time
import logging
from collections import deque
from typing import Optional, Tuple, Dict
from .dw_led_controller import DWLEDController

logger = logging.getLogger(__name__)


class BallTrackingManager:
    """Manages real-time LED tracking of ball bearing position"""

    def __init__(self, led_controller: DWLEDController, num_leds: int, config: Dict):
        """
        Initialize ball tracking manager

        Args:
            led_controller: DWLEDController instance (kept for compatibility, not used for rendering)
            num_leds: Number of LEDs in the strip
            config: Configuration dict with keys:
                - led_offset: LED index offset (0 to num_leds-1)
                - reversed: Reverse LED direction (bool)
                - spread: Number of adjacent LEDs to light (1-10)
                - lookback: Number of coordinates to look back (0-15)
                - brightness: LED brightness 0-100
                - color: Hex color string (e.g., "#ffffff")
                - trail_enabled: Enable fade trail (bool)
                - trail_length: Trail length in LEDs (1-20)
        """
        self.led_controller = led_controller  # Kept for backward compatibility
        self.num_leds = num_leds
        self.config = config

        # Coordinate history buffer (max 15 coordinates)
        self.position_buffer = deque(maxlen=15)

        # Tracking state
        self._active = False
        self._update_task = None
        self._last_led_index = None

        logger.info(f"BallTrackingManager initialized with {num_leds} LEDs")

    def start(self):
        """Start ball tracking"""
        if self._active:
            logger.warning("Ball tracking already active")
            return

        self._active = True
        logger.info("Ball tracking started")

    def stop(self):
        """Stop ball tracking"""
        if not self._active:
            return

        self._active = False
        self.position_buffer.clear()
        self._last_led_index = None

        logger.info("Ball tracking stopped")

    def update_position(self, theta: float, rho: float):
        """
        Update ball position (called from pattern execution)

        Args:
            theta: Angular position in degrees (0-360)
            rho: Radial distance (0.0-1.0)
        """
        if not self._active:
            return

        # Add to buffer
        self.position_buffer.append((theta, rho, time.time()))

        # Trigger LED update
        self._update_leds()

    def _update_leds(self):
        """Update LED tracking state (rendering is done by effect loop)"""
        if not self._active:
            return

        # Get position to track (with lookback)
        position = self._get_tracked_position()
        if position is None:
            return

        theta, rho, _ = position

        # Calculate LED index
        led_index = self._theta_to_led(theta)

        # Store the LED index (effect will read this)
        self._last_led_index = led_index

    def _get_tracked_position(self) -> Optional[Tuple[float, float, float]]:
        """Get position to track (accounting for lookback delay)"""
        lookback = self.config.get("lookback", 0)

        if len(self.position_buffer) == 0:
            return None

        # Clamp lookback to buffer size
        lookback = min(lookback, len(self.position_buffer) - 1)
        lookback = max(0, lookback)

        # Get position from buffer
        # Index -1 = most recent, -2 = one back, etc.
        index = -(lookback + 1)
        return self.position_buffer[index]

    def _theta_to_led(self, theta: float) -> int:
        """
        Convert theta angle to LED index

        Args:
            theta: Angle in degrees (0-360)

        Returns:
            LED index (0 to num_leds-1)
        """
        # Normalize theta to 0-360
        theta = theta % 360
        if theta < 0:
            theta += 360

        # Calculate LED index (0° = LED 0 before offset)
        led_index = int((theta / 360.0) * self.num_leds)
        original_index = led_index

        # Apply user-defined offset
        offset = self.config.get("led_offset", 0)
        led_index = (led_index + offset) % self.num_leds

        # Reverse direction if needed
        is_reversed = self.config.get("reversed", False)
        if is_reversed:
            led_index_before_reverse = led_index
            led_index = (self.num_leds - led_index) % self.num_leds
            logger.debug(f"Theta={theta:.1f}° -> LED {original_index} + offset {offset} = {led_index_before_reverse} -> REVERSED to {led_index}")
        else:
            logger.debug(f"Theta={theta:.1f}° -> LED {original_index} + offset {offset} = {led_index}")

        return led_index

    def get_tracking_data(self) -> Optional[Dict]:
        """
        Get current tracking data for effect rendering

        Returns:
            Dictionary with led_index, spread, brightness, color
            or None if no tracking data available
        """
        if self._last_led_index is None:
            return None

        # Get configuration
        spread = self.config.get("spread", 3)
        brightness = self.config.get("brightness", 50) / 100.0
        color_hex = self.config.get("color", "#ffffff")

        # Convert hex color to RGB tuple
        color_hex = color_hex.lstrip('#')
        r = int(color_hex[0:2], 16)
        g = int(color_hex[2:4], 16)
        b = int(color_hex[4:6], 16)

        return {
            'led_index': self._last_led_index,
            'spread': spread,
            'brightness': brightness,
            'color': (r, g, b)
        }

    def update_config(self, config: Dict):
        """Update configuration at runtime"""
        self.config.update(config)
        logger.info(f"Ball tracking config updated: {config}")
        logger.info(f"Current reversed setting: {self.config.get('reversed', False)}")

    def get_status(self) -> Dict:
        """Get current tracking status"""
        return {
            "active": self._active,
            "buffer_size": len(self.position_buffer),
            "last_led_index": self._last_led_index,
            "config": self.config
        }
