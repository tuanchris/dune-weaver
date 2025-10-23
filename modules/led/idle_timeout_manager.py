"""
Idle LED Timeout Manager
Handles automatic LED turn-off after a period of inactivity.
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class IdleTimeoutManager:
    """
    Manages idle timeout for LED effects.
    When idle effect is played, starts a timer. When timer expires,
    checks if table is still idle and turns off LEDs if so.
    """

    def __init__(self):
        self._timeout_task: Optional[asyncio.Task] = None
        self._last_idle_time: Optional[datetime] = None

    def start_idle_timeout(self, timeout_minutes: float, state, check_idle_callback):
        """
        Start or restart the idle timeout timer.

        Args:
            timeout_minutes: Minutes to wait before turning off LEDs
            state: Application state object
            check_idle_callback: Async callback to check if table is still idle
        """
        # Cancel any existing timeout
        self.cancel_timeout()

        if timeout_minutes <= 0:
            logger.debug("Idle timeout disabled (timeout <= 0)")
            return

        # Record when idle effect was started
        self._last_idle_time = datetime.now()
        logger.info(f"Starting idle LED timeout: {timeout_minutes} minutes")

        # Create background task to handle timeout
        self._timeout_task = asyncio.create_task(
            self._timeout_handler(timeout_minutes, state, check_idle_callback)
        )

    async def _timeout_handler(self, timeout_minutes: float, state, check_idle_callback):
        """
        Background task that waits for timeout and turns off LEDs if still idle.
        """
        try:
            # Wait for the specified timeout
            timeout_seconds = timeout_minutes * 60
            await asyncio.sleep(timeout_seconds)

            # Check if we should turn off the LEDs
            logger.debug("Idle timeout expired, checking table state...")

            # Check if table is still idle (not playing anything)
            is_idle = await check_idle_callback()

            if is_idle:
                logger.info("Table is still idle after timeout - turning off LEDs")
                if state.led_controller:
                    try:
                        state.led_controller.set_power(0)  # Turn off LEDs
                        logger.info("LEDs turned off successfully")
                    except Exception as e:
                        logger.error(f"Failed to turn off LEDs: {e}")
                else:
                    logger.warning("LED controller not configured")
            else:
                logger.debug("Table is not idle - skipping LED turn-off")

        except asyncio.CancelledError:
            logger.debug("Idle timeout cancelled")
        except Exception as e:
            logger.error(f"Error in idle timeout handler: {e}")

    def cancel_timeout(self):
        """Cancel any running timeout task."""
        if self._timeout_task and not self._timeout_task.done():
            logger.debug("Cancelling existing idle timeout")
            self._timeout_task.cancel()
            self._timeout_task = None

    def is_timeout_active(self) -> bool:
        """Check if a timeout is currently active."""
        return self._timeout_task is not None and not self._timeout_task.done()


# Singleton instance
idle_timeout_manager = IdleTimeoutManager()
