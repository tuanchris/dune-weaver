"""Screen (LCD backlight) controller via Linux sysfs.

Mirrors the sysfs approach used in dune-weaver-touch/backend.py so the main
FastAPI backend can control the attached touchscreen independently. On dev
machines without /sys/class/backlight the controller reports available=False
and all commands no-op gracefully.
"""
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

SUDO = shutil.which("sudo") or "/usr/bin/sudo"
SH = shutil.which("sh") or "/bin/sh"


class ScreenController:
    def __init__(self):
        self.brightness_path: str = ""
        self.max_brightness: int = 255
        self._current_brightness: int = 0
        self._power_on: bool = True
        self.available: bool = False

        self._detect_backlight()

    # ── Detection ──────────────────────────────────────────────

    def _detect_backlight(self):
        """Auto-detect the sysfs backlight device, path, and max brightness."""
        backlight_base = Path("/sys/class/backlight")
        if not backlight_base.exists():
            logger.info("No /sys/class/backlight found — screen control unavailable")
            return

        try:
            devices = [d.name for d in backlight_base.iterdir() if d.is_dir()]
        except Exception as e:
            logger.warning(f"Failed to list backlight devices: {e}")
            return

        if not devices:
            logger.info("No backlight devices found")
            return

        device = devices[0]
        self.brightness_path = f"/sys/class/backlight/{device}/brightness"
        logger.info(f"Auto-detected backlight device: {device}")

        # Read max_brightness
        max_path = f"/sys/class/backlight/{device}/max_brightness"
        try:
            self.max_brightness = int(Path(max_path).read_text().strip())
            logger.info(f"Max brightness: {self.max_brightness}")
        except Exception as e:
            self.max_brightness = 255
            logger.warning(f"Failed to read max_brightness, defaulting to 255: {e}")

        # Read current brightness
        try:
            self._current_brightness = int(Path(self.brightness_path).read_text().strip())
            self._power_on = self._current_brightness > 0
            logger.info(f"Current brightness: {self._current_brightness}/{self.max_brightness}")
        except Exception as e:
            logger.warning(f"Failed to read current brightness: {e}")

        self.available = True

    # ── Public API ─────────────────────────────────────────────

    def set_brightness(self, value: int) -> dict:
        """Set backlight brightness (0 to max_brightness)."""
        if not self.available:
            return {"success": False, "message": "Screen control not available"}

        value = max(0, min(value, self.max_brightness))
        try:
            subprocess.run(
                [SUDO, SH, "-c", f"echo {value} > {self.brightness_path}"],
                check=True, timeout=5
            )
            self._current_brightness = value
            if value > 0:
                self._power_on = True
            return {"success": True, "brightness": value}
        except Exception as e:
            logger.error(f"Failed to set brightness: {e}")
            return {"success": False, "message": str(e)}

    def set_power(self, on: bool) -> dict:
        """Turn screen on or off via framebuffer blank + backlight."""
        if not self.available:
            return {"success": False, "message": "Screen control not available"}

        try:
            if on:
                # Restore brightness + unblank framebuffer
                restore = self._current_brightness if self._current_brightness > 0 else self.max_brightness
                subprocess.run(
                    [SUDO, SH, "-c",
                     f"echo 0 > /sys/class/graphics/fb0/blank && echo {restore} > {self.brightness_path}"],
                    check=True, timeout=5
                )
                self._current_brightness = restore
                self._power_on = True
            else:
                # Zero brightness + blank framebuffer
                subprocess.run(
                    [SUDO, SH, "-c",
                     f"echo 0 > {self.brightness_path} && echo 1 > /sys/class/graphics/fb0/blank"],
                    check=True, timeout=5
                )
                self._power_on = False

            return {"success": True, "power_on": self._power_on}
        except Exception as e:
            logger.error(f"Failed to set screen power: {e}")
            return {"success": False, "message": str(e)}

    def get_status(self) -> dict:
        """Return current screen state."""
        return {
            "available": self.available,
            "power_on": self._power_on,
            "brightness": self._current_brightness,
            "max_brightness": self.max_brightness,
        }
