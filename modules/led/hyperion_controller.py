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

            # Reduced timeout from 2s to 1s - Hyperion should respond quickly
            # This prevents hanging when Hyperion is under load
            response = requests.post(url, json=payload, timeout=1)
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
        """Check Hyperion connection status, component state, and active priorities"""
        result = self._send_command("serverinfo")

        if result.get("connected"):
            response = result.get("response", {})
            info = response.get("info", {})
            components = {c["name"]: c["enabled"] for c in info.get("components", [])}

            # Get active priorities information
            priorities = info.get("priorities", [])
            active_priority = None
            active_effect = None
            active_color = None

            # Find the highest priority (lowest number) active source
            if priorities:
                # Filter for visible priorities only
                visible = [p for p in priorities if p.get("visible", True)]
                if visible:
                    # Sort by priority (lowest first)
                    visible.sort(key=lambda x: x.get("priority", 999))
                    active_priority = visible[0].get("priority")

                    # Check if it's our priority
                    if active_priority == self.priority:
                        component_id = visible[0].get("componentId", "")
                        if component_id == "EFFECT":
                            active_effect = visible[0].get("owner", "")
                        elif component_id == "COLOR":
                            active_color = visible[0].get("value", {}).get("RGB")

            return {
                "connected": True,
                "is_on": components.get("ALL", False),
                "ledstream_on": components.get("LEDDEVICE", False),
                "hostname": info.get("hostname", "unknown"),
                "version": info.get("version", "unknown"),
                "message": "Hyperion is ON" if components.get("ALL", False) else "Hyperion is OFF",
                "active_priority": active_priority,
                "active_effect": active_effect,
                "active_color": active_color,
                "our_priority_active": active_priority == self.priority if active_priority else False
            }

        return result

    def set_power(self, state: int, check_current: bool = True) -> Dict:
        """
        Set Hyperion power state (component control)
        Args:
            state: 0=Off, 1=On, 2=Toggle
            check_current: If True, check current state and skip if already in desired state
        """
        if state not in [0, 1, 2]:
            return {"connected": False, "message": "Power state must be 0 (Off), 1 (On), or 2 (Toggle)"}

        # Always check current state for toggle or when check_current is enabled
        if state == 2 or check_current:
            status = self.check_hyperion_status()
            if not status.get("connected"):
                return status

            current_state = status.get("is_on", False)

            if state == 2:
                # Toggle: flip the current state
                state = 0 if current_state else 1
            elif check_current:
                # Check if already in desired state
                desired_state = bool(state)
                if current_state == desired_state:
                    logger.debug(f"Hyperion already {'ON' if desired_state else 'OFF'}, skipping power command")
                    return {
                        "connected": True,
                        "message": f"Already in desired state ({'ON' if desired_state else 'OFF'})",
                        "skipped": True
                    }

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

    def set_effect(self, effect_name: str, args: Optional[Dict] = None, duration: int = 86400000, check_current: bool = True) -> Dict:
        """
        Set Hyperion effect
        Args:
            effect_name: Name of the effect (e.g., 'Rainbow swirl', 'Warm mood blobs')
            args: Optional effect arguments
            duration: Duration in milliseconds (default = 86400000ms = 24 hours)
            check_current: If True, check if effect is already active and skip if so
        """
        # Check current state if requested
        if check_current:
            status = self.check_hyperion_status()
            if not status.get("connected"):
                return status

            # Check if the same effect is already active at our priority
            if status.get("our_priority_active") and status.get("active_effect") == effect_name:
                logger.debug(f"Effect '{effect_name}' already active at our priority, skipping")
                return {
                    "connected": True,
                    "message": f"Effect '{effect_name}' already active",
                    "skipped": True
                }

            # Ensure Hyperion is on (with state check)
            self.set_power(1, check_current=True)
        else:
            # Turn on without checking
            self.set_power(1, check_current=False)

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

    def clear_priority(self, priority: Optional[int] = None, check_current: bool = True) -> Dict:
        """
        Clear a specific priority or Dune Weaver's priority
        Args:
            priority: Priority to clear (defaults to self.priority)
            check_current: If True, check if priority is active before clearing
        """
        if priority is None:
            priority = self.priority

        # Check if the priority is actually active
        if check_current:
            status = self.check_hyperion_status()
            if not status.get("connected"):
                return status

            # If our priority isn't active, no need to clear
            if priority == self.priority and not status.get("our_priority_active"):
                logger.debug(f"Priority {priority} not active, skipping clear")
                return {
                    "connected": True,
                    "message": f"Priority {priority} not active",
                    "skipped": True
                }

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
    try:
        # Set effect with smart checking (will check power state and current effect)
        res = hyperion_controller.set_effect("Atomic swirl", check_current=True)
        return res.get('connected', False)
    except Exception as e:
        logger.error(f"Error in effect_loading: {e}")
        return False


def effect_idle(hyperion_controller: HyperionController, effect_name: str = "off") -> bool:
    """Show idle effect - use configured effect or clear priority to return to default

    Args:
        effect_name: Effect name to show, "off" to clear priority (default), or None for off
    """
    try:
        if effect_name and effect_name != "off":
            # Set effect with smart checking (will check power state and current effect)
            res = hyperion_controller.set_effect(effect_name, check_current=True)
        else:
            # Clear priority with smart checking (only if our priority is active)
            res = hyperion_controller.clear_priority(check_current=True)

        return res.get('connected', False)
    except Exception as e:
        logger.error(f"Error in effect_idle: {e}")
        return False


def effect_connected(hyperion_controller: HyperionController) -> bool:
    """Show connected effect - green flash

    Note: This function only shows the connection flash. The calling code
    should explicitly set the idle effect afterwards to ensure the user's
    configured idle effect is used.
    """
    try:
        # Turn on Hyperion and clear in one go
        hyperion_controller.set_power(1)
        time.sleep(0.1)  # Reduced blocking time
        hyperion_controller.clear_priority()

        # Single green flash instead of double - reduces load
        res = hyperion_controller.set_color(r=8, g=255, b=0, duration=1000)
        time.sleep(1.0)  # Wait for flash to complete
        # Don't call effect_idle here - let the caller set the configured idle effect
        return res.get('connected', False)
    except Exception as e:
        logger.error(f"Error in effect_connected: {e}")
        return False


def effect_playing(hyperion_controller: HyperionController, effect_name: str = "off") -> bool:
    """Show playing effect - use configured effect or clear to show default

    Args:
        effect_name: Effect name to show, "off" to clear priority (default), or None for off
    """
    try:
        if effect_name and effect_name != "off":
            # Set effect with smart checking (will check power state and current effect)
            res = hyperion_controller.set_effect(effect_name, check_current=True)
        else:
            # Clear priority with smart checking (only if our priority is active)
            res = hyperion_controller.clear_priority(check_current=True)

        return res.get('connected', False)
    except Exception as e:
        logger.error(f"Error in effect_playing: {e}")
        return False
