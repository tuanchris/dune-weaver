import requests
import json
from typing import Dict, Optional
import time
import logging

logger = logging.getLogger(__name__)


class HyperionController:
    """Controller for Hyperion LED system using JSON-RPC API"""

    def __init__(self, ip_address: Optional[str] = None, port: int = 8090):
        self.ip_address = ip_address
        self.port = port
        # Priority for Dune Weaver effects (lower = higher priority)
        # Using 100 to allow user to override with lower priorities if needed
        self.priority = 100

    def _get_base_url(self) -> str:
        """Get base URL for Hyperion JSON-RPC API"""
        if not self.ip_address:
            raise ValueError("No Hyperion IP configured")
        return f"http://{self.ip_address}:{self.port}/json-rpc"

    def set_ip(self, ip_address: str, port: int = 8090) -> None:
        """Update the Hyperion IP address and port"""
        self.ip_address = ip_address
        self.port = port

    def _send_command(self, command: str, **params) -> Dict:
        """Send JSON-RPC command to Hyperion and return response"""
        try:
            url = self._get_base_url()

            payload = {
                "command": command,
                **params
            }

            response = requests.post(url, json=payload, timeout=2)
            response.raise_for_status()
            result = response.json()

            if not result.get("success", False):
                error_msg = result.get("error", "Unknown error")
                return {
                    "connected": False,
                    "message": f"Hyperion command failed: {error_msg}"
                }

            return {
                "connected": True,
                "message": "Command successful",
                "response": result
            }

        except ValueError as e:
            return {"connected": False, "message": str(e)}
        except requests.RequestException as e:
            return {"connected": False, "message": f"Cannot connect to Hyperion: {str(e)}"}
        except json.JSONDecodeError as e:
            return {"connected": False, "message": f"Error parsing Hyperion response: {str(e)}"}

    def check_hyperion_status(self) -> Dict:
        """Check Hyperion connection status and component state"""
        result = self._send_command("serverinfo")

        if result.get("connected"):
            response = result.get("response", {})
            info = response.get("info", {})
            components = {c["name"]: c["enabled"] for c in info.get("components", [])}

            return {
                "connected": True,
                "is_on": components.get("ALL", False),
                "ledstream_on": components.get("LEDDEVICE", False),
                "hostname": info.get("hostname", "unknown"),
                "version": info.get("version", "unknown"),
                "message": "Hyperion is ON" if components.get("ALL", False) else "Hyperion is OFF"
            }

        return result

    def set_power(self, state: int) -> Dict:
        """
        Set Hyperion power state (component control)
        Args:
            state: 0=Off, 1=On, 2=Toggle
        """
        if state not in [0, 1, 2]:
            return {"connected": False, "message": "Power state must be 0 (Off), 1 (On), or 2 (Toggle)"}

        if state == 2:
            # Get current state and toggle
            status = self.check_hyperion_status()
            if not status.get("connected"):
                return status
            state = 0 if status.get("is_on", False) else 1

        result = self._send_command(
            "componentstate",
            componentstate={
                "component": "ALL",
                "state": bool(state)
            }
        )

        return result

    def set_color(self, r: int = 0, g: int = 0, b: int = 0, duration: int = 86400000) -> Dict:
        """
        Set solid color on Hyperion
        Args:
            r, g, b: RGB values (0-255)
            duration: Duration in milliseconds (default = 86400000ms = 24 hours)
                     Note: Some Hyperion instances don't support duration=0 for infinite
        """
        if not all(0 <= val <= 255 for val in [r, g, b]):
            return {"connected": False, "message": "RGB values must be between 0 and 255"}

        # Turn on Hyperion first
        self.set_power(1)
        # Clear priority before setting new color
        self.clear_priority()

        result = self._send_command(
            "color",
            priority=self.priority,
            color=[r, g, b],
            duration=duration
        )

        return result

    def set_effect(self, effect_name: str, args: Optional[Dict] = None, duration: int = 86400000) -> Dict:
        """
        Set Hyperion effect
        Args:
            effect_name: Name of the effect (e.g., 'Rainbow swirl', 'Warm mood blobs')
            args: Optional effect arguments
            duration: Duration in milliseconds (default = 86400000ms = 24 hours)
        """
        # Turn on Hyperion first
        self.set_power(1)
        # Clear priority before setting new effect
        self.clear_priority()

        params = {
            "priority": self.priority,
            "effect": {"name": effect_name},
            "duration": duration
        }

        if args:
            params["effect"]["args"] = args

        result = self._send_command("effect", **params)
        return result

    def clear_priority(self, priority: Optional[int] = None) -> Dict:
        """
        Clear a specific priority or Dune Weaver's priority
        Args:
            priority: Priority to clear (defaults to self.priority)
        """
        if priority is None:
            priority = self.priority

        result = self._send_command("clear", priority=priority)
        return result

    def clear_all(self) -> Dict:
        """Clear all priorities (return to default state)"""
        result = self._send_command("clear", priority=-1)
        return result

    def set_brightness(self, value: int) -> Dict:
        """
        Set Hyperion brightness
        Args:
            value: Brightness (0-100)
        """
        if not 0 <= value <= 100:
            return {"connected": False, "message": "Brightness must be between 0 and 100"}

        result = self._send_command(
            "adjustment",
            adjustment={
                "brightness": value
            }
        )

        return result


def effect_loading(hyperion_controller: HyperionController) -> bool:
    """Show loading effect - Atomic swirl effect"""
    # Turn on Hyperion first
    hyperion_controller.set_power(1)
    time.sleep(0.2)  # Give Hyperion time to power on
    # Clear priority before setting new effect
    hyperion_controller.clear_priority()
    time.sleep(0.1)  # Give Hyperion time to clear
    res = hyperion_controller.set_effect("Atomic swirl")
    return res.get('connected', False)


def effect_idle(hyperion_controller: HyperionController, effect_name: str = "off") -> bool:
    """Show idle effect - use configured effect or clear priority to return to default

    Args:
        effect_name: Effect name to show, "off" to clear priority (default), or None for off
    """
    # Turn on Hyperion first
    hyperion_controller.set_power(1)
    time.sleep(0.2)  # Give Hyperion time to power on
    # Clear priority before setting new effect
    hyperion_controller.clear_priority()
    if effect_name and effect_name != "off":
        time.sleep(0.1)  # Give Hyperion time to clear
        res = hyperion_controller.set_effect(effect_name)
    else:
        # "off" or None - already cleared above, return to default state
        res = {"connected": True}
    return res.get('connected', False)


def effect_connected(hyperion_controller: HyperionController) -> bool:
    """Show connected effect - green flash"""
    # Turn on Hyperion first
    hyperion_controller.set_power(1)
    time.sleep(0.2)  # Give Hyperion time to power on
    # Clear priority before setting new effect
    hyperion_controller.clear_priority()
    time.sleep(0.1)  # Give Hyperion time to clear
    # Flash green twice with explicit 1 second durations
    res = hyperion_controller.set_color(r=8, g=255, b=0, duration=1000)
    time.sleep(1.2)  # Wait for flash to complete
    res = hyperion_controller.set_color(r=8, g=255, b=0, duration=1000)
    time.sleep(1.2)  # Wait for flash to complete
    effect_idle(hyperion_controller)
    return res.get('connected', False)


def effect_playing(hyperion_controller: HyperionController, effect_name: str = "off") -> bool:
    """Show playing effect - use configured effect or clear to show default

    Args:
        effect_name: Effect name to show, "off" to clear priority (default), or None for off
    """
    # Turn on Hyperion first
    hyperion_controller.set_power(1)
    time.sleep(0.2)  # Give Hyperion time to power on
    # Clear priority before setting new effect
    hyperion_controller.clear_priority()
    if effect_name and effect_name != "off":
        time.sleep(0.1)  # Give Hyperion time to clear
        res = hyperion_controller.set_effect(effect_name)
    else:
        # "off" or None - already cleared above, show user's configured effect/color
        res = {"connected": True}
    return res.get('connected', False)
