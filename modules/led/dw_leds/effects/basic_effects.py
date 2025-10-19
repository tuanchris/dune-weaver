#!/usr/bin/env python3
"""
WLED Basic Effects for Raspberry Pi
Effects 0-30: Static, Blink, Rainbow, Scan, etc.
Ported from WLED FX.cpp
"""
import random
import math
from ..segment import Segment
from ..utils.colors import *

# Effect return value is delay in milliseconds
FRAMETIME = 24  # ~42 FPS

def mode_static(seg: Segment) -> int:
    """Solid color"""
    seg.fill(seg.get_color(0))
    return 350 if seg.call == 0 else FRAMETIME

def mode_blink(seg: Segment) -> int:
    """Blink between two colors"""
    cycle_time = (255 - seg.speed) * 20
    on_time = FRAMETIME + ((cycle_time * seg.intensity) >> 8)
    cycle_time += FRAMETIME * 2

    now = seg.now()
    iteration = now // cycle_time
    rem = now % cycle_time

    on = (iteration != seg.step) or (rem <= on_time)
    seg.step = iteration

    seg.fill(seg.get_color(0) if on else seg.get_color(1))
    return FRAMETIME

def mode_strobe(seg: Segment) -> int:
    """Strobe effect"""
    cycle_time = (255 - seg.speed) * 20 + FRAMETIME * 2
    now = seg.now()
    iteration = now // cycle_time
    on = (iteration != seg.step)
    seg.step = iteration

    seg.fill(seg.get_color(0) if on else seg.get_color(1))
    return FRAMETIME

def mode_breath(seg: Segment) -> int:
    """Breathing effect"""
    counter = (seg.now() * ((seg.speed >> 3) + 10)) & 0xFFFF
    counter = (counter >> 2) + (counter >> 4)

    var = 0
    if counter < 16384:
        if counter > 8192:
            counter = 8192 - (counter - 8192)
        var = sin16(counter) // 103

    lum = 30 + var
    for i in range(seg.length):
        seg.set_pixel_color(i, color_blend(seg.get_color(1),
                                          seg.color_from_palette(i),
                                          lum & 0xFF))
    return FRAMETIME

def mode_fade(seg: Segment) -> int:
    """Fade between two colors"""
    counter = seg.now() * ((seg.speed >> 3) + 10)
    lum = triwave16(counter & 0xFFFF) >> 8

    for i in range(seg.length):
        seg.set_pixel_color(i, color_blend(seg.get_color(1),
                                          seg.color_from_palette(i),
                                          lum))
    return FRAMETIME

def mode_scan(seg: Segment) -> int:
    """Scanning pixel"""
    if seg.length <= 1:
        return mode_static(seg)

    cycle_time = 750 + (255 - seg.speed) * 150
    perc = seg.now() % cycle_time
    prog = (perc * 65535) // cycle_time
    size = 1 + ((seg.intensity * seg.length) >> 9)
    led_index = (prog * ((seg.length * 2) - size * 2)) >> 16

    seg.fill(seg.get_color(1))

    led_offset = led_index - (seg.length - size)
    led_offset = abs(led_offset)

    for j in range(led_offset, min(led_offset + size, seg.length)):
        seg.set_pixel_color(j, seg.color_from_palette(j))

    return FRAMETIME

def mode_dual_scan(seg: Segment) -> int:
    """Dual scanning pixels"""
    if seg.length <= 1:
        return mode_static(seg)

    cycle_time = 750 + (255 - seg.speed) * 150
    perc = seg.now() % cycle_time
    prog = (perc * 65535) // cycle_time
    size = 1 + ((seg.intensity * seg.length) >> 9)
    led_index = (prog * ((seg.length * 2) - size * 2)) >> 16

    seg.fill(seg.get_color(1))

    led_offset = led_index - (seg.length - size)
    led_offset = abs(led_offset)

    # First scanner
    for j in range(led_offset, min(led_offset + size, seg.length)):
        seg.set_pixel_color(j, seg.color_from_palette(j))

    # Second scanner (opposite direction)
    for j in range(led_offset, min(led_offset + size, seg.length)):
        i2 = seg.length - 1 - j
        seg.set_pixel_color(i2, seg.color_from_palette(i2))

    return FRAMETIME

def mode_rainbow(seg: Segment) -> int:
    """Solid rainbow (cycles through hues)"""
    counter = (seg.now() * ((seg.speed >> 2) + 2)) & 0xFFFF
    counter = counter >> 8

    if seg.intensity < 128:
        color = color_blend(color_wheel(counter), WHITE,
                           128 - seg.intensity)
    else:
        color = color_wheel(counter)

    seg.fill(color)
    return FRAMETIME

def mode_rainbow_cycle(seg: Segment) -> int:
    """Rainbow distributed across strip"""
    counter = (seg.now() * ((seg.speed >> 2) + 2)) & 0xFFFF
    counter = counter >> 8

    for i in range(seg.length):
        # intensity controls density
        index = (i * (16 << (seg.intensity // 29)) // seg.length) + counter
        seg.set_pixel_color(i, color_wheel(index & 0xFF))

    return FRAMETIME

def mode_theater_chase(seg: Segment) -> int:
    """Theater chase effect"""
    width = 3 + (seg.intensity >> 4)
    cycle_time = 50 + (255 - seg.speed)
    iteration = seg.now() // cycle_time

    for i in range(seg.length):
        if (i % width) == seg.aux0:
            seg.set_pixel_color(i, seg.color_from_palette(i))
        else:
            seg.set_pixel_color(i, seg.get_color(1))

    if iteration != seg.step:
        seg.aux0 = (seg.aux0 + 1) % width
        seg.step = iteration

    return FRAMETIME

def mode_running_lights(seg: Segment) -> int:
    """Running lights with sine wave"""
    x_scale = seg.intensity >> 2
    counter = (seg.now() * seg.speed) >> 9

    for i in range(seg.length):
        a = i * x_scale - counter
        s = sin8(a & 0xFF)
        color = color_blend(seg.get_color(1),
                           seg.color_from_palette(i), s)
        seg.set_pixel_color(i, color)

    return FRAMETIME

def mode_color_wipe(seg: Segment) -> int:
    """Color wipe effect"""
    if seg.length <= 1:
        return mode_static(seg)

    cycle_time = 750 + (255 - seg.speed) * 150
    perc = seg.now() % cycle_time
    prog = (perc * 65535) // cycle_time
    back = prog > 32767

    if back:
        prog -= 32767
        if seg.step == 0:
            seg.step = 1
    else:
        if seg.step == 2:
            seg.step = 3

    led_index = (prog * seg.length) >> 15
    rem = (prog * seg.length) * 2
    rem //= (seg.intensity + 1)
    rem = min(255, rem)

    col0 = seg.get_color(0)
    col1 = seg.get_color(1)

    for i in range(seg.length):
        if i < led_index:
            seg.set_pixel_color(i, col1 if back else col0)
        else:
            seg.set_pixel_color(i, col0 if back else col1)
            if i == led_index:
                blended = color_blend(col1 if back else col0,
                                     col0 if back else col1,
                                     rem)
                seg.set_pixel_color(i, blended)

    return FRAMETIME

def mode_random_color(seg: Segment) -> int:
    """Random solid colors with fade"""
    cycle_time = 200 + (255 - seg.speed) * 50
    iteration = seg.now() // cycle_time
    rem = seg.now() % cycle_time
    fade_dur = (cycle_time * seg.intensity) >> 8

    fade = 255
    if fade_dur:
        fade = (rem * 255) // fade_dur
        fade = min(255, fade)

    if seg.call == 0:
        seg.aux0 = random.randint(0, 255)
        seg.step = 2

    if iteration != seg.step:
        seg.aux1 = seg.aux0
        seg.aux0 = random.randint(0, 255)
        seg.step = iteration

    color = color_blend(color_wheel(seg.aux1),
                       color_wheel(seg.aux0), fade)
    seg.fill(color)
    return FRAMETIME

def mode_dynamic(seg: Segment) -> int:
    """Dynamic random colors per pixel"""
    if seg.call == 0:
        seg.data = [random.randint(0, 255) for _ in range(seg.length)]

    cycle_time = 50 + (255 - seg.speed) * 15
    iteration = seg.now() // cycle_time

    if iteration != seg.step and seg.speed != 0:
        for i in range(seg.length):
            if random.randint(0, 255) <= seg.intensity:
                seg.data[i] = random.randint(0, 255)
        seg.step = iteration

    for i in range(seg.length):
        seg.set_pixel_color(i, color_wheel(seg.data[i]))

    return FRAMETIME

def mode_twinkle(seg: Segment) -> int:
    """Twinkle effect"""
    seg.fade_out(224)

    cycle_time = 20 + (255 - seg.speed) * 5
    iteration = seg.now() // cycle_time

    if iteration != seg.step:
        max_on = max(1, (seg.intensity * seg.length) // 255)
        if seg.aux0 >= max_on:
            seg.aux0 = 0
            seg.aux1 = random.randint(0, 0xFFFF)
        seg.aux0 += 1
        seg.step = iteration

    prng = seg.aux1
    for _ in range(seg.aux0):
        prng = (prng * 2053 + 13849) & 0xFFFF
        j = (prng * seg.length) >> 16
        if j < seg.length:
            seg.set_pixel_color(j, seg.color_from_palette(j))

    return FRAMETIME

def mode_sparkle(seg: Segment) -> int:
    """Single sparkle effect"""
    for i in range(seg.length):
        seg.set_pixel_color(i, seg.color_from_palette(i))

    cycle_time = 10 + (255 - seg.speed) * 2
    iteration = seg.now() // cycle_time

    if iteration != seg.step:
        seg.aux0 = random.randint(0, seg.length - 1)
        seg.step = iteration

    seg.set_pixel_color(seg.aux0, seg.get_color(0))
    return FRAMETIME

# Effect registry
EFFECTS = {
    0: ("Static", mode_static),
    1: ("Blink", mode_blink),
    2: ("Breathe", mode_breath),
    3: ("Wipe", mode_color_wipe),
    4: ("Fade", mode_fade),
    5: ("Scan", mode_scan),
    6: ("Dual Scan", mode_dual_scan),
    7: ("Rainbow", mode_rainbow),
    8: ("Rainbow Cycle", mode_rainbow_cycle),
    9: ("Theater Chase", mode_theater_chase),
    10: ("Running Lights", mode_running_lights),
    11: ("Random Color", mode_random_color),
    12: ("Dynamic", mode_dynamic),
    13: ("Twinkle", mode_twinkle),
    14: ("Sparkle", mode_sparkle),
    15: ("Strobe", mode_strobe),
}

def get_effect(effect_id: int):
    """Get effect function by ID"""
    if effect_id in EFFECTS:
        return EFFECTS[effect_id][1]
    return mode_static

def get_effect_name(effect_id: int) -> str:
    """Get effect name by ID"""
    if effect_id in EFFECTS:
        return EFFECTS[effect_id][0]
    return "Unknown"

def get_all_effects():
    """Get list of all effects"""
    return [(k, v[0]) for k, v in sorted(EFFECTS.items())]
