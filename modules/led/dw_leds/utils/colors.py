#!/usr/bin/env python3
"""
WLED Color Utilities for Raspberry Pi
Ported from WLED colors.cpp
"""
import math
from typing import Tuple

# Color manipulation functions

def color_blend(color1: int, color2: int, blend: int) -> int:
    """
    Blend two colors together (32-bit WRGB format)
    blend: 0-255 (0 = full color1, 255 = full color2)
    """
    if blend == 0:
        return color1
    if blend == 255:
        return color2

    w1 = (color1 >> 24) & 0xFF
    r1 = (color1 >> 16) & 0xFF
    g1 = (color1 >> 8) & 0xFF
    b1 = color1 & 0xFF

    w2 = (color2 >> 24) & 0xFF
    r2 = (color2 >> 16) & 0xFF
    g2 = (color2 >> 8) & 0xFF
    b2 = color2 & 0xFF

    w3 = ((w1 * (255 - blend)) + (w2 * blend)) // 255
    r3 = ((r1 * (255 - blend)) + (r2 * blend)) // 255
    g3 = ((g1 * (255 - blend)) + (g2 * blend)) // 255
    b3 = ((b1 * (255 - blend)) + (b2 * blend)) // 255

    return (w3 << 24) | (r3 << 16) | (g3 << 8) | b3

def color_add(c1: int, c2: int, preserve_ratio: bool = False) -> int:
    """Add two colors together with optional ratio preservation"""
    if c1 == 0:
        return c2
    if c2 == 0:
        return c1

    w1 = (c1 >> 24) & 0xFF
    r1 = (c1 >> 16) & 0xFF
    g1 = (c1 >> 8) & 0xFF
    b1 = c1 & 0xFF

    w2 = (c2 >> 24) & 0xFF
    r2 = (c2 >> 16) & 0xFF
    g2 = (c2 >> 8) & 0xFF
    b2 = c2 & 0xFF

    r = min(255, r1 + r2)
    g = min(255, g1 + g2)
    b = min(255, b1 + b2)
    w = min(255, w1 + w2)

    if preserve_ratio:
        max_val = max(r, g, b, w)
        if max_val > 255:
            scale = 255.0 / max_val
            r = int(r * scale)
            g = int(g * scale)
            b = int(b * scale)
            w = int(w * scale)

    return (w << 24) | (r << 16) | (g << 8) | b

def color_fade(color: int, amount: int, video: bool = False) -> int:
    """
    Fade color toward black
    amount: 0 (black) to 255 (no fade)
    video: if True, uses "video" scaling (never goes to pure black)
    """
    if color == 0 or amount == 0:
        return 0
    if amount == 255:
        return color

    w = (color >> 24) & 0xFF
    r = (color >> 16) & 0xFF
    g = (color >> 8) & 0xFF
    b = color & 0xFF

    if not video:
        amount += 1
        w = (w * amount) >> 8
        r = (r * amount) >> 8
        g = (g * amount) >> 8
        b = (b * amount) >> 8
    else:
        # Video scaling - ensure colors don't go to zero if they started non-zero
        w = max(1 if w else 0, (w * amount) >> 8)
        r = max(1 if r else 0, (r * amount) >> 8)
        g = max(1 if g else 0, (g * amount) >> 8)
        b = max(1 if b else 0, (b * amount) >> 8)

    return (w << 24) | (r << 16) | (g << 8) | b

def wheel(pos: int) -> Tuple[int, int, int]:
    """
    Color wheel function (0-255) -> RGB
    Used for rainbow effects
    """
    pos &= 0xFF
    if pos < 85:
        return (pos * 3, 255 - pos * 3, 0)
    elif pos < 170:
        pos -= 85
        return (255 - pos * 3, 0, pos * 3)
    else:
        pos -= 170
        return (0, pos * 3, 255 - pos * 3)

def color_wheel(pos: int) -> int:
    """Color wheel returning 32-bit color (WLED format)"""
    r, g, b = wheel(pos)
    return (r << 16) | (g << 8) | b

def hsv_to_rgb(h: int, s: int, v: int) -> Tuple[int, int, int]:
    """
    Convert HSV to RGB
    h: 0-65535 (16-bit hue)
    s: 0-255 (saturation)
    v: 0-255 (value/brightness)
    Returns: (r, g, b) tuple, each 0-255
    """
    if s == 0:
        return (v, v, v)

    region = h // 10923  # 65536 / 6
    remainder = (h - (region * 10923)) * 6

    p = (v * (255 - s)) >> 8
    q = (v * (255 - ((s * remainder) >> 16))) >> 8
    t = (v * (255 - ((s * (65535 - remainder)) >> 16))) >> 8

    if region == 0:
        return (v, t, p)
    elif region == 1:
        return (q, v, p)
    elif region == 2:
        return (p, v, t)
    elif region == 3:
        return (p, q, v)
    elif region == 4:
        return (t, p, v)
    else:
        return (v, p, q)

def rgb_to_hsv(r: int, g: int, b: int) -> Tuple[int, int, int]:
    """
    Convert RGB to HSV
    Returns: (h, s, v) where h is 0-65535, s and v are 0-255
    """
    min_val = min(r, g, b)
    max_val = max(r, g, b)

    if max_val == 0:
        return (0, 0, 0)

    v = max_val
    delta = max_val - min_val
    s = (255 * delta) // max_val

    if s == 0:
        return (0, 0, v)

    if max_val == r:
        h = (10923 * (g - b)) // delta
    elif max_val == g:
        h = 21845 + (10923 * (b - r)) // delta
    else:
        h = 43690 + (10923 * (r - g)) // delta

    h &= 0xFFFF  # Ensure 16-bit
    return (h, s, v)

def sin8(x: int) -> int:
    """Fast 8-bit sine approximation (0-255 input, 0-255 output)"""
    # Simple sine approximation
    x &= 0xFF
    if x < 128:
        # Rising half
        return int(128 + 127 * math.sin(x * math.pi / 128))
    else:
        # Falling half
        return int(128 + 127 * math.sin((x - 128) * math.pi / 128))

def sin16(x: int) -> int:
    """16-bit sine (-32768 to 32767 output)"""
    angle = (x & 0xFFFF) / 65536.0 * 2 * math.pi
    return int(32767 * math.sin(angle))

def triwave16(x: int) -> int:
    """Triangle wave 0-65535"""
    x &= 0xFFFF
    if x < 0x8000:
        return x * 2
    return 0xFFFF - (x - 0x8000) * 2

# Helper functions to extract color components
def get_r(color: int) -> int:
    """Extract red component from 32-bit color"""
    return (color >> 16) & 0xFF

def get_g(color: int) -> int:
    """Extract green component from 32-bit color"""
    return (color >> 8) & 0xFF

def get_b(color: int) -> int:
    """Extract blue component from 32-bit color"""
    return color & 0xFF

def get_w(color: int) -> int:
    """Extract white component from 32-bit color"""
    return (color >> 24) & 0xFF

def rgb_to_color(r: int, g: int, b: int, w: int = 0) -> int:
    """Create 32-bit color from RGBW components"""
    return (w << 24) | (r << 16) | (g << 8) | b

def color_from_tuple(rgb: Tuple[int, int, int]) -> int:
    """Convert RGB tuple to 32-bit color"""
    return (rgb[0] << 16) | (rgb[1] << 8) | rgb[2]

# Constants
BLACK = 0x00000000
WHITE = 0x00FFFFFF
RED = 0x00FF0000
GREEN = 0x0000FF00
BLUE = 0x000000FF
