"""
Reed switch monitoring module for Raspberry Pi GPIO.
Used for angular homing to detect home position.
"""
import logging
import platform

logger = logging.getLogger(__name__)

class ReedSwitchMonitor:
    """Monitor a reed switch connected to a Raspberry Pi GPIO pin."""

    def __init__(self, gpio_pin=18):
        """
        Initialize the reed switch monitor.

        Args:
            gpio_pin: GPIO pin number (BCM numbering) for the reed switch
        """
        self.gpio_pin = gpio_pin
        self.gpio = None
        self.is_raspberry_pi = self._check_raspberry_pi()

        if self.is_raspberry_pi:
            try:
                import RPi.GPIO as GPIO
                self.gpio = GPIO

                # Set up GPIO mode (BCM numbering)
                self.gpio.setmode(GPIO.BCM)

                # Set up the pin as input with pull-up resistor
                # Reed switch should connect pin to ground when triggered
                self.gpio.setup(self.gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

                logger.info(f"Reed switch initialized on GPIO pin {self.gpio_pin}")
            except ImportError:
                logger.warning("RPi.GPIO not available. Reed switch monitoring disabled.")
                self.is_raspberry_pi = False
            except Exception as e:
                logger.error(f"Error initializing reed switch: {e}")
                self.is_raspberry_pi = False
        else:
            logger.info("Not running on Raspberry Pi. Reed switch monitoring disabled.")

    def _check_raspberry_pi(self):
        """Check if we're running on a Raspberry Pi."""
        try:
            # Check if we're on Linux first
            if platform.system() != 'Linux':
                return False

            # Check for Raspberry Pi specific identifiers
            with open('/proc/cpuinfo', 'r') as f:
                cpuinfo = f.read()
                if 'Raspberry Pi' in cpuinfo or 'BCM' in cpuinfo:
                    return True

            # Alternative check using device tree
            try:
                with open('/proc/device-tree/model', 'r') as f:
                    model = f.read()
                    if 'Raspberry Pi' in model:
                        return True
            except FileNotFoundError:
                pass

            return False
        except Exception as e:
            logger.debug(f"Error checking for Raspberry Pi: {e}")
            return False

    def is_triggered(self):
        """
        Check if the reed switch is currently triggered.

        Returns:
            bool: True if reed switch is triggered (pin is LOW), False otherwise
        """
        if not self.is_raspberry_pi or not self.gpio:
            return False

        try:
            # Pin is LOW (0) when reed switch is closed (triggered)
            return self.gpio.input(self.gpio_pin) == 0
        except Exception as e:
            logger.error(f"Error reading reed switch: {e}")
            return False

    def wait_for_trigger(self, timeout=None):
        """
        Wait for the reed switch to be triggered.

        Args:
            timeout: Maximum time to wait in seconds (None = wait indefinitely)

        Returns:
            bool: True if triggered, False if timeout occurred
        """
        if not self.is_raspberry_pi or not self.gpio:
            logger.warning("Reed switch not available, cannot wait for trigger")
            return False

        try:
            # Wait for falling edge (pin goes from HIGH to LOW)
            channel = self.gpio.wait_for_edge(
                self.gpio_pin,
                self.gpio.FALLING,
                timeout=int(timeout * 1000) if timeout else None
            )
            return channel is not None
        except Exception as e:
            logger.error(f"Error waiting for reed switch trigger: {e}")
            return False

    def cleanup(self):
        """Clean up GPIO resources."""
        if self.is_raspberry_pi and self.gpio:
            try:
                self.gpio.cleanup(self.gpio_pin)
                logger.info(f"Reed switch GPIO pin {self.gpio_pin} cleaned up")
            except Exception as e:
                logger.error(f"Error cleaning up reed switch GPIO: {e}")

    def __del__(self):
        """Destructor to ensure GPIO cleanup."""
        self.cleanup()
