"""
Board LED controller — drives the table's own LED ring through the FluidNC
firmware instead of host GPIO.

The firmware owns the strip ($LED/* NVS settings, live control via /sand_led)
and natively handles run/idle transitions ($LED/RunEffect / $LED/IdleEffect),
so the host neither renders effects nor switches them around pattern playback.

This class intentionally mirrors the DWLEDController surface the /api/dw_leds/*
endpoints are duck-typed against (check_status, set_power, set_brightness,
set_color(s), get_effects/get_palettes, set_effect/set_palette, set_speed,
set_intensity), so the existing LED page works unchanged against the board.
"""
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Firmware effects in the firmware's order (ids are list indices).
# Keep in sync with the firmware's Leds.cpp / the mobile app's LED_EFFECTS.
BOARD_EFFECTS: List[Tuple[str, str]] = [
    ("off", "Off"), ("static", "Static"), ("rainbow", "Rainbow"),
    ("breathe", "Breathe"), ("colorloop", "Color loop"), ("theater", "Theater"),
    ("scan", "Scan"), ("running", "Running"), ("sine", "Sine"),
    ("gradient", "Gradient"), ("sinelon", "Sinelon"), ("twinkle", "Twinkle"),
    ("sparkle", "Sparkle"), ("fire", "Fire"), ("candle", "Candle"),
    ("meteor", "Meteor"), ("bouncing", "Bouncing"), ("wipe", "Wipe"),
    ("dualscan", "Dual scan"), ("juggle", "Juggle"), ("multicomet", "Multi-comet"),
    ("glitter", "Glitter"), ("dissolve", "Dissolve"), ("ripple", "Ripple"),
    ("drip", "Drip"), ("lightning", "Lightning"), ("fireworks", "Fireworks"),
    ("plasma", "Plasma"), ("heartbeat", "Heartbeat"), ("strobe", "Strobe"),
    ("police", "Police"), ("chase", "Chase"), ("railway", "Railway"),
    ("pacifica", "Pacifica"), ("aurora", "Aurora"), ("pride", "Pride"),
    ("colorwaves", "Color waves"), ("bpm", "BPM"), ("ball", "Ball"),
]
BOARD_PALETTES = ["rainbow", "ocean", "lava", "forest", "party", "cloud", "heat", "sunset"]

_EFFECT_ID_BY_NAME = {name: i for i, (name, _label) in enumerate(BOARD_EFFECTS)}


def effect_name_for_id(effect_id: int) -> Optional[str]:
    if 0 <= effect_id < len(BOARD_EFFECTS):
        return BOARD_EFFECTS[effect_id][0]
    return None


def effect_id_for_name(name: str) -> int:
    return _EFFECT_ID_BY_NAME.get((name or "").lower(), 0)


class BoardLEDController:
    """DWLEDController-compatible facade over the firmware's LED API."""

    def __init__(self):
        # Restore target for set_power(1) when the strip was turned off.
        self._last_effect = "static"

    # -- helpers ---------------------------------------------------------

    def _conn(self):
        from modules.core.state import state
        if not state.conn or not state.conn.is_connected():
            return None
        return state.conn

    def _led(self, **keys) -> Dict:
        """Send live LED control (/sand_led); works mid-pattern, NVS-persisted at idle."""
        conn = self._conn()
        if not conn:
            return {"connected": False, "error": "Table not connected"}
        try:
            conn.set_led(**keys)
            return {"connected": True, "power_on": keys.get("effect") != "off"}
        except Exception as e:
            logger.warning(f"Board LED control failed ({keys}): {e}")
            return {"connected": False, "error": str(e)}

    def _read(self) -> Optional[Dict]:
        """Read the board's $LED/* settings map (None when unreachable)."""
        conn = self._conn()
        if not conn:
            return None
        try:
            settings = conn.get_settings()
            return {k[4:]: v for k, v in settings.items() if k.startswith("LED/")}
        except Exception as e:
            logger.warning(f"Could not read board LED settings: {e}")
            return None

    # -- DWLEDController-compatible surface -------------------------------

    def check_status(self) -> Dict:
        led = self._read()
        if led is None:
            return {"connected": False, "error": "Table not connected"}
        effect = (led.get("Effect") or "off").lower()
        if effect != "off":
            self._last_effect = effect
        brightness_255 = int(led.get("Brightness", 128) or 0)
        palette = (led.get("Palette") or "rainbow").lower()
        return {
            "connected": True,
            "power_on": effect != "off",
            "brightness": round(brightness_255 * 100 / 255),
            "speed": int(led.get("Speed", 128) or 0),
            "intensity": 0,  # no firmware equivalent
            "current_effect": effect_id_for_name(effect),
            "current_palette": BOARD_PALETTES.index(palette) if palette in BOARD_PALETTES else 0,
            "num_leds": 0,  # owned by the board's config.yaml
            "gpio_pin": None,
            "colors": [
                f"#{led.get('Color', 'FF0000')}",
                f"#{led.get('Color2', '000000')}",
                "#000000",
            ],
            "run_effect": (led.get("RunEffect") or "none").lower(),
            "idle_effect": (led.get("IdleEffect") or "none").lower(),
            # 'ball' effect params (firmware-native; the blob that follows the ball).
            "ball": {
                "fgbright": int(led.get("BallBright", 255) or 0),
                "bgbright": int(led.get("BallBgBright", 255) or 0),
                "size": int(led.get("BallSize", 3) or 0),
                "bg": (led.get("BallBg") or "static").lower(),
                "direction": (led.get("Direction") or "cw").lower(),
                "align": int(led.get("Align", 0) or 0),
            },
        }

    def set_power(self, power_state: int) -> Dict:
        status = self.check_status()
        if not status.get("connected"):
            return status
        currently_on = status.get("power_on", False)
        turn_on = not currently_on if power_state == 2 else bool(power_state)
        if turn_on == currently_on:
            return status
        result = self._led(effect=self._last_effect if turn_on else "off")
        result["power_on"] = turn_on
        return result

    def set_brightness(self, value: int) -> Dict:
        # dw API is 0-100; the firmware wants 0-255.
        return self._led(brightness=max(0, min(255, round(value * 255 / 100))))

    def set_color(self, r: int, g: int, b: int) -> Dict:
        return self._led(color=f"{r:02X}{g:02X}{b:02X}")

    def set_colors(self, color1=None, color2=None, color3=None) -> Dict:
        keys = {}
        if color1:
            keys["color"] = "{:02X}{:02X}{:02X}".format(*color1)
        if color2:
            keys["color2"] = "{:02X}{:02X}{:02X}".format(*color2)
        # color3 has no firmware equivalent
        if not keys:
            return {"connected": True}
        return self._led(**keys)

    def get_effects(self) -> List[Tuple[int, str]]:
        return [(i, label) for i, (_name, label) in enumerate(BOARD_EFFECTS)]

    def get_palettes(self) -> List[Tuple[int, str]]:
        return [(i, name.capitalize()) for i, name in enumerate(BOARD_PALETTES)]

    def set_effect(self, effect_id: int, speed: Optional[int] = None,
                   intensity: Optional[int] = None) -> Dict:
        name = effect_name_for_id(int(effect_id))
        if name is None:
            return {"connected": False, "error": f"Unknown effect id {effect_id}"}
        if name != "off":
            self._last_effect = name
        keys = {"effect": name}
        if speed is not None:
            keys["speed"] = max(1, min(255, int(speed)))
        return self._led(**keys)

    def set_palette(self, palette_id: int) -> Dict:
        if not 0 <= int(palette_id) < len(BOARD_PALETTES):
            return {"connected": False, "error": f"Unknown palette id {palette_id}"}
        return self._led(palette=BOARD_PALETTES[int(palette_id)])

    def set_speed(self, value: int) -> Dict:
        return self._led(speed=max(1, min(255, int(value))))

    def set_intensity(self, value: int) -> Dict:
        # The firmware has no intensity control; accept and ignore.
        return {"connected": True}

    # -- 'ball' tracker (firmware-native blob that follows the sand ball) -----

    # Live /sand_led keys, with their clamp ranges (persisted to NVS at idle).
    _BALL_KEYS = {
        "fgbright": (0, 255),   # blob brightness
        "bgbright": (0, 255),   # background brightness
        "size": (1, 200),       # glow size in LEDs
        "align": (0, 359),      # rotate the blob onto the ball (degrees)
    }

    def set_ball(self, **params) -> Dict:
        """Tune the 'ball' effect live via /sand_led (only meaningful while the
        'ball' effect is active). Accepted keys: fgbright, bgbright, size, align
        (ints), direction ('cw'|'ccw'), bg (sub-effect name / 'static' / 'off'),
        color, color2 (RRGGBB hex)."""
        keys: dict = {}
        for key, (lo, hi) in self._BALL_KEYS.items():
            if params.get(key) is not None:
                keys[key] = max(lo, min(hi, int(params[key])))
        if params.get("direction") in ("cw", "ccw"):
            keys["direction"] = params["direction"]
        if params.get("bg"):
            keys["bg"] = str(params["bg"])
        for c in ("color", "color2"):
            if params.get(c):
                keys[c] = str(params[c]).lstrip("#").upper()
        if not keys:
            return {"connected": True}
        return self._led(**keys)

    # -- firmware-native run/idle automation -------------------------------

    def set_run_effect(self, effect_name: str) -> bool:
        """$LED/RunEffect — the board switches to it while moving ('none' disables)."""
        return self._set_auto_effect("LED/RunEffect", effect_name)

    def set_idle_effect(self, effect_name: str) -> bool:
        """$LED/IdleEffect — the board switches to it at idle ('none' disables)."""
        return self._set_auto_effect("LED/IdleEffect", effect_name)

    def _set_auto_effect(self, key: str, effect_name: str) -> bool:
        conn = self._conn()
        if not conn:
            return False
        try:
            conn.set_setting(key, effect_name or "none")
            return True
        except Exception as e:
            logger.warning(f"Could not set {key}={effect_name}: {e}")
            return False

    def stop(self):
        """Provider-switch hook; nothing to tear down (the board keeps running)."""
