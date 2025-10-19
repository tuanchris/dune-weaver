#!/usr/bin/env python3
"""
WLED Segment class for Raspberry Pi
Manages LED strip segments and their effects
"""
import time
from typing import List, Callable, Optional
from .utils.colors import *
from .utils.palettes import color_from_palette, get_palette

class Segment:
    """LED segment with effect support"""

    def __init__(self, pixels, start: int, stop: int):
        """
        Initialize a segment
        pixels: neopixel.NeoPixel object
        start: starting LED index
        stop: ending LED index (exclusive)
        """
        self.pixels = pixels
        self.start = start
        self.stop = stop
        self.length = stop - start

        # Colors (up to 3 colors like WLED)
        self.colors = [0x00FF0000, 0x000000FF, 0x0000FF00]  # Red, Blue, Green defaults

        # Effect parameters
        self.speed = 128        # 0-255
        self.intensity = 128    # 0-255
        self.palette_id = 0     # Palette ID
        self.custom1 = 0        # Custom parameter 1
        self.custom2 = 0        # Custom parameter 2
        self.custom3 = 0        # Custom parameter 3

        # Runtime state (like SEGENV in WLED)
        self.call = 0           # Number of times effect has been called
        self.step = 0           # Effect step counter
        self.aux0 = 0           # Auxiliary variable 0
        self.aux1 = 0           # Auxiliary variable 1
        self.next_time = 0      # Next time to run effect (ms)
        self.data = []          # Effect data storage

        # Timing
        self._start_time = time.time() * 1000  # Convert to milliseconds

    def get_pixel_color(self, i: int) -> int:
        """Get color of pixel at index i (segment-relative)"""
        if i < 0 or i >= self.length:
            return 0
        actual_idx = self.start + i
        color = self.pixels[actual_idx]
        # Convert from neopixel (R,G,B) or (G,R,B) to 32-bit
        if isinstance(color, tuple):
            if len(color) == 3:
                return (color[0] << 16) | (color[1] << 8) | color[2]
            elif len(color) == 4:
                return (color[3] << 24) | (color[0] << 16) | (color[1] << 8) | color[2]
        return 0

    def set_pixel_color(self, i: int, color: int):
        """Set color of pixel at index i (segment-relative)"""
        if i < 0 or i >= self.length:
            return
        actual_idx = self.start + i
        r = get_r(color)
        g = get_g(color)
        b = get_b(color)
        self.pixels[actual_idx] = (r, g, b)

    def fill(self, color: int):
        """Fill entire segment with color"""
        for i in range(self.length):
            self.set_pixel_color(i, color)

    def fade_out(self, amount: int):
        """Fade all pixels in segment toward black"""
        for i in range(self.length):
            current = self.get_pixel_color(i)
            faded = color_fade(current, amount)
            self.set_pixel_color(i, faded)

    def blur(self, amount: int):
        """Blur/blend pixels with neighbors"""
        if amount == 0 or self.length < 3:
            return

        # Simple blur: blend each pixel with neighbors
        temp = [self.get_pixel_color(i) for i in range(self.length)]

        for i in range(self.length):
            if i == 0:
                # First pixel: blend with next
                blended = color_blend(temp[i], temp[i + 1], amount)
            elif i == self.length - 1:
                # Last pixel: blend with previous
                blended = color_blend(temp[i], temp[i - 1], amount)
            else:
                # Middle pixels: blend with both neighbors
                left = color_blend(temp[i], temp[i - 1], amount // 2)
                blended = color_blend(left, temp[i + 1], amount // 2)

            self.set_pixel_color(i, blended)

    def now(self) -> int:
        """Get current time in milliseconds since segment start"""
        return int((time.time() * 1000) - self._start_time)

    def color_from_palette(self, index: int, use_index: bool = True,
                          brightness: int = 255) -> int:
        """
        Get color from current palette
        index: LED index or palette position
        use_index: if True, scale index across palette
        brightness: 0-255
        """
        palette = get_palette(self.palette_id)

        if use_index and self.length > 1:
            # Map LED position to palette position
            palette_pos = (index * 255) // (self.length - 1)
        else:
            palette_pos = index & 0xFF

        return color_from_palette(palette, palette_pos, brightness)

    def get_color(self, index: int) -> int:
        """Get segment color by index (0-2)"""
        if 0 <= index < len(self.colors):
            return self.colors[index]
        return 0

    def reset(self):
        """Reset segment state"""
        self.call = 0
        self.step = 0
        self.aux0 = 0
        self.aux1 = 0
        self.next_time = 0
        self.data = []
