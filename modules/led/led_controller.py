import requests
import json
from typing import Dict, Optional
import time
import logging
logger = logging.getLogger(__name__)


class LEDController:
    def __init__(self, ip_address: Optional[str] = None):
        self.ip_address = ip_address

    def _get_base_url(self) -> str:
        """Get base URL for WLED JSON API"""
        if not self.ip_address:
            raise ValueError("No WLED IP configured")
        return f"http://{self.ip_address}/json"

    def set_ip(self, ip_address: str) -> None:
        """Update the WLED IP address"""
        self.ip_address = ip_address

    def _send_command(self, state_params: Dict = None) -> Dict:
        """Send command to WLED and return status"""
        logger.info("Sending command to WLED...")
        logger.info(state_params)
        try:
            url = self._get_base_url()
            
            # First check current state
            response = requests.get(f"{url}/state", timeout=2)
            response.raise_for_status()
            current_state = response.json()
            
            # If WLED is off and we're trying to set something, turn it on first
            if not current_state.get('on', False) and state_params and 'on' not in state_params:
                # Turn on power first
                requests.post(f"{url}/state", json={"on": True}, timeout=2)
            
            # Now send the actual command if there are parameters
            if state_params:
                response = requests.post(f"{url}/state", json=state_params, timeout=2)
                response.raise_for_status()
                response = requests.get(f"{url}/state", timeout=2)
                response.raise_for_status()
                current_state = response.json()
                
            preset_id = current_state.get('ps', -1)
            playlist_id = current_state.get('pl', -1)

            # Use True as default since WLED is typically on when responding
            is_on = current_state.get('on', True)
            
            return {
                "connected": True,
                "is_on": is_on,
                "preset_id": preset_id,
                "playlist_id": playlist_id,
                "brightness": current_state.get('bri', 0),
                "message": "WLED is ON" if is_on else "WLED is OFF"
            }

        except ValueError as e:
            return {"connected": False, "message": str(e)}
        except requests.RequestException as e:
            return {"connected": False, "message": f"Cannot connect to WLED: {str(e)}"}
        except json.JSONDecodeError as e:
            return {"connected": False, "message": f"Error parsing WLED response: {str(e)}"}

    def check_wled_status(self) -> Dict:
        """Check WLED connection status and brightness"""
        return self._send_command()

    def set_brightness(self, value: int) -> Dict:
        """Set WLED brightness (0-255)"""
        if not 0 <= value <= 255:
            return {"connected": False, "message": "Brightness must be between 0 and 255"}
        return self._send_command({"bri": value})

    def set_power(self, state: int) -> Dict:
        """Set WLED power state (0=Off, 1=On, 2=Toggle)"""
        if state not in [0, 1, 2]:
            return {"connected": False, "message": "Power state must be 0 (Off), 1 (On), or 2 (Toggle)"}
        if state == 2:
            return self._send_command({"on": "t"})  # Toggle
        return self._send_command({"on": bool(state)})

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        """Convert hex color string to RGB tuple"""
        hex_color = hex_color.lstrip('#')
        if len(hex_color) != 6:
            raise ValueError("Hex color must be 6 characters long (without #)")
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def set_color(self, r: int = None, g: int = None, b: int = None, w: int = None, hex: str = None) -> Dict:
        """Set WLED color using RGB(W) values or hex color code"""
        if hex is not None:
            try:
                r, g, b = self._hex_to_rgb(hex)
            except ValueError as e:
                return {"connected": False, "message": str(e)}

        # Prepare segment with color
        seg = {"col": [[r or 0, g or 0, b or 0]]}
        if w is not None:
            if not 0 <= w <= 255:
                return {"connected": False, "message": "White value must be between 0 and 255"}
            seg["col"][0].append(w)

        return self._send_command({"seg": [seg]})

    def set_effect(self, effect_index: int, speed: int = None, intensity: int = None, 
                   brightness: int = None, palette: int = None,
                   # Primary color
                   r: int = None, g: int = None, b: int = None, w: int = None, hex: str = None,
                   # Secondary color
                   r2: int = None, g2: int = None, b2: int = None, w2: int = None, hex2: str = None,
                   # Transition
                   transition: int = 0) -> Dict:
        """
        Set WLED effect with optional parameters
        Args:
            effect_index: Effect index (0-101)
            speed: Effect speed (0-255)
            intensity: Effect intensity (0-255)
            brightness: LED brightness (0-255)
            palette: FastLED palette index (0-46)
            r, g, b: Primary RGB color values (0-255)
            w: Primary White value for RGBW (0-255)
            hex: Primary hex color code (e.g., '#ff0000' or 'ff0000')
            r2, g2, b2: Secondary RGB color values (0-255)
            w2: Secondary White value for RGBW (0-255)
            hex2: Secondary hex color code
            transition: Duration of crossfade in 100ms units (e.g. 7 = 700ms). Default 0 for instant change.
        """
        try:
            effect_index = int(effect_index)
        except (ValueError, TypeError):
            return {"connected": False, "message": "Effect index must be a valid integer between 0 and 101"}

        if not 0 <= effect_index <= 101:
            return {"connected": False, "message": "Effect index must be between 0 and 101"}

        # Convert primary hex to RGB if provided
        if hex is not None:
            try:
                r, g, b = self._hex_to_rgb(hex)
            except ValueError as e:
                return {"connected": False, "message": f"Primary color: {str(e)}"}

        # Convert secondary hex to RGB if provided
        if hex2 is not None:
            try:
                r2, g2, b2 = self._hex_to_rgb(hex2)
            except ValueError as e:
                return {"connected": False, "message": f"Secondary color: {str(e)}"}

        # Build segment parameters
        seg = {"fx": effect_index}
        
        if speed is not None:
            if not 0 <= speed <= 255:
                return {"connected": False, "message": "Speed must be between 0 and 255"}
            seg["sx"] = speed
        
        if intensity is not None:
            if not 0 <= intensity <= 255:
                return {"connected": False, "message": "Intensity must be between 0 and 255"}
            seg["ix"] = intensity

        # Prepare colors array
        colors = []
        
        # Add primary color
        primary = [r or 0, g or 0, b or 0]
        if w is not None:
            if not 0 <= w <= 255:
                return {"connected": False, "message": "Primary white value must be between 0 and 255"}
            primary.append(w)
        colors.append(primary)
        
        # Add secondary color if any secondary color parameter is provided
        if any(x is not None for x in [r2, g2, b2, w2, hex2]):
            secondary = [r2 or 0, g2 or 0, b2 or 0]
            if w2 is not None:
                if not 0 <= w2 <= 255:
                    return {"connected": False, "message": "Secondary white value must be between 0 and 255"}
                secondary.append(w2)
            colors.append(secondary)

        if colors:
            seg["col"] = colors

        if palette is not None:
            if not 0 <= palette <= 46:
                return {"connected": False, "message": "Palette index must be between 0 and 46"}
            seg["pal"] = palette

        # Combine with global parameters
        state = {"seg": [seg], "transition": transition}
        if brightness is not None:
            if not 0 <= brightness <= 255:
                return {"connected": False, "message": "Brightness must be between 0 and 255"}
            state["bri"] = brightness

        return self._send_command(state)

    def set_preset(self, preset_id: int) -> bool:
        preset_id = int(preset_id)
        # Send the command and get response
        response = self._send_command({"ps": preset_id})
        logger.debug(response)
        return response

def effect_loading(led_controller: LEDController):
    res = led_controller.set_effect(47, hex='#ffa000', hex2='#000000', palette=0, speed=150, intensity=150)
    if res.get('is_on', False):
        return True
    else:
        return False

def set_off(led_controller: LEDController):
    led_controller.set_power(0)  # Turn off WLED


def effect_idle(led_controller: LEDController):
    led_controller.set_preset(1)


def effect_connected(led_controller: LEDController):
    res = led_controller.set_effect(0, hex='#08ff00', brightness=100)
    time.sleep(1)
    led_controller.set_effect(0, brightness=0)  # Turn off
    time.sleep(0.5)
    res = led_controller.set_effect(0, hex='#08ff00', brightness=100)
    time.sleep(1)
    effect_idle(led_controller)
    if res.get('is_on', False):
        return True
    else:
        return False

def effect_pattern_done(led_controller: LEDController):
    for i in range(5):
        led_controller.set_effect(0, hex="#00ff37", brightness=100)
        time.sleep(0.2)
        led_controller.set_effect(0, brightness=0)
        time.sleep(0.2)

def effect_playing(led_controller: LEDController):
    led_controller.set_preset(2)
