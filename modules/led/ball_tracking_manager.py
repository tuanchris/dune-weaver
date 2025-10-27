"""
Ball Tracking LED Manager
Tracks the ball bearing's position and updates LEDs in real-time to follow its movement.
"""
import asyncio
import time
import logging
import threading
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

        # Position storage (buffer only if lookback > 0)
        lookback = config.get("lookback", 0)
        if lookback > 0:
            # Use buffer for lookback delay
            self.position_buffer = deque(maxlen=min(15, lookback + 5))
            self._use_buffer = True
            logger.info(f"Using position buffer (size={lookback + 5}) for lookback={lookback}")
        else:
            # No lookback, just store current position
            self.position_buffer = None
            self._current_position = None  # (theta, rho, timestamp)
            self._use_buffer = False
            logger.info("Direct tracking (no lookback buffer)")

        # Tracking state
        self._active = False
        self._update_task = None
        self._last_led_index = None
        self._lock = threading.Lock()  # Thread safety for LED index updates
        self._update_count = 0  # Counter for debug logging
        self._skipped_updates = 0  # Track how many updates were skipped

        # Polling timer for position updates
        self._poll_timer = None
        self._poll_interval = 0.5  # Check position every 0.5 seconds
        self._is_pattern_running = False  # Flag to track if pattern is executing

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
        self._stop_polling()

        if self._use_buffer and self.position_buffer:
            self.position_buffer.clear()
        else:
            self._current_position = None
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

        # Store position
        timestamp = time.time()
        if self._use_buffer:
            self.position_buffer.append((theta, rho, timestamp))
        else:
            self._current_position = (theta, rho, timestamp)

        self._update_count += 1

        # Debug logging (every 100th update)
        if self._update_count % 100 == 0:
            buffer_info = f"buffer_size={len(self.position_buffer)}" if self._use_buffer else "direct"
            logger.info(f"Position update #{self._update_count}: theta={theta:.1f}°, rho={rho:.2f}, {buffer_info}, skipped={self._skipped_updates}")

        # Trigger LED update (with optimization)
        self._update_leds_optimized(theta, rho)

    def set_pattern_running(self, is_running: bool):
        """
        Notify manager that pattern execution started/stopped

        Args:
            is_running: True if pattern is executing, False otherwise
        """
        logger.info(f"set_pattern_running called: is_running={is_running}, active={self._active}")
        self._is_pattern_running = is_running

        if is_running and self._active:
            # Pattern started, begin polling
            self._start_polling()
            logger.info(f"Pattern started - beginning position polling (interval={self._poll_interval}s)")
        else:
            # Pattern stopped, stop polling
            self._stop_polling()
            logger.info("Pattern stopped - stopping position polling")

    def _start_polling(self):
        """Start the position polling timer"""
        if self._poll_timer is not None:
            return  # Already polling

        self._poll_position()  # Do first poll immediately

    def _stop_polling(self):
        """Stop the position polling timer"""
        if self._poll_timer is not None:
            self._poll_timer.cancel()
            self._poll_timer = None

    def _poll_position(self):
        """Poll current position from state and update LEDs if needed"""
        if not self._active or not self._is_pattern_running:
            logger.debug(f"Polling stopped: active={self._active}, pattern_running={self._is_pattern_running}")
            self._poll_timer = None
            return

        try:
            # Import here to avoid circular dependency
            from modules.core.state import state

            # Get current position from global state
            theta = state.current_theta
            rho = state.current_rho

            logger.debug(f"Polling position: theta={theta:.1f}°, rho={rho:.2f}, last_led={self._last_led_index}")

            # Update position (this will skip if LED zone hasn't changed)
            self._update_leds_optimized(theta, rho)

        except Exception as e:
            logger.error(f"Error polling position: {e}", exc_info=True)

        # Schedule next poll
        if self._active and self._is_pattern_running:
            self._poll_timer = threading.Timer(self._poll_interval, self._poll_position)
            self._poll_timer.daemon = True
            self._poll_timer.start()
        else:
            self._poll_timer = None

    def _update_leds_optimized(self, current_theta: float, current_rho: float):
        """
        Optimized LED update - only recalculates if LED zone changed

        Args:
            current_theta: Most recent theta value
            current_rho: Most recent rho value
        """
        if not self._active:
            logger.debug("Update skipped: not active")
            return

        # If using lookback buffer, get the delayed position
        if self._use_buffer:
            position = self._get_tracked_position()
            if position is None:
                logger.debug("Update skipped: no position in buffer")
                return
            theta, rho, _ = position
        else:
            # Direct tracking - use current position
            theta = current_theta
            rho = current_rho

        # Calculate new LED index
        new_led_index = self._theta_to_led(theta)

        # OPTIMIZATION: Only update if LED index actually changed
        with self._lock:
            if new_led_index == self._last_led_index:
                # LED zone hasn't changed, skip update
                self._skipped_updates += 1
                logger.debug(f"LED zone unchanged: {new_led_index}")
                return

            # LED zone changed, update it
            logger.info(f"LED zone changed: {self._last_led_index} → {new_led_index} (theta={theta:.1f}°)")
            self._last_led_index = new_led_index

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

        # Debug logging (every 50th update)
        if self._update_count % 50 == 0:
            lookback = self.config.get("lookback", 0)
            logger.info(f"LED update #{self._update_count}: lookback={lookback}, tracked_theta={theta:.1f}°, led_index={led_index}")

        # Store the LED index (effect will read this) - thread-safe update
        with self._lock:
            self._last_led_index = led_index

    def _get_tracked_position(self) -> Optional[Tuple[float, float, float]]:
        """Get position to track (accounting for lookback delay)"""
        if not self._use_buffer:
            # Direct mode - return current position
            return self._current_position

        # Buffer mode - apply lookback
        if not self.position_buffer or len(self.position_buffer) == 0:
            return None

        lookback = self.config.get("lookback", 0)

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
        # Thread-safe read of LED index
        with self._lock:
            led_index = self._last_led_index

        if led_index is None:
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
            'led_index': led_index,
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
