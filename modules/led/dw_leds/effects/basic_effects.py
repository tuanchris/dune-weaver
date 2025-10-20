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

def mode_fire(seg: Segment) -> int:
    """Fire/flame effect"""
    if seg.call == 0:
        seg.data = [0] * seg.length

    # Cooling parameter (higher = cooler flames)
    cooling = ((100 - (seg.intensity >> 1)) * 10) // seg.length + 2

    # Heat decay for all pixels
    for i in range(seg.length):
        cool_down = random.randint(0, cooling)
        seg.data[i] = max(0, seg.data[i] - cool_down)

    # Heat drift upward
    for i in range(seg.length - 1, 2, -1):
        seg.data[i] = (seg.data[i - 1] + seg.data[i - 2] + seg.data[i - 2]) // 3

    # Randomly ignite new sparks near bottom
    if random.randint(0, 255) < seg.intensity:
        spark_pos = random.randint(0, min(7, seg.length - 1))
        seg.data[spark_pos] = min(255, seg.data[spark_pos] + random.randint(160, 255))

    # Convert heat to colors
    for i in range(seg.length):
        heat = seg.data[i]

        # Black -> Red -> Yellow -> White
        if heat < 85:
            color = (heat * 3, 0, 0)
        elif heat < 170:
            h = heat - 85
            color = (255, h * 3, 0)
        else:
            h = heat - 170
            color = (255, 255, h * 3)

        r, g, b = color
        seg.set_pixel_color(i, (r << 16) | (g << 8) | b)

    return FRAMETIME

def mode_comet(seg: Segment) -> int:
    """Comet/shooting star effect"""
    if seg.call == 0:
        seg.aux0 = 0
        seg.aux1 = 0

    seg.fade_out(128)

    size = 1 + ((seg.intensity * seg.length) >> 9)
    cycle_time = 10 + (255 - seg.speed)
    iteration = seg.now() // cycle_time

    if iteration != seg.step:
        seg.aux0 = (seg.aux0 + 1) % seg.length
        seg.step = iteration

    # Draw comet
    for i in range(size):
        pos = (seg.aux0 - i) % seg.length
        brightness = 255 - (i * 255 // max(1, size))
        color = color_blend(0, seg.color_from_palette(pos), brightness)
        seg.set_pixel_color(pos, color)

    return FRAMETIME

def mode_chase(seg: Segment) -> int:
    """Chase effect with colored segments"""
    if seg.call == 0:
        seg.aux0 = 0

    size = max(1, seg.length // 4)
    cycle_time = 10 + (255 - seg.speed)
    iteration = seg.now() // cycle_time

    if iteration != seg.step:
        seg.aux0 = (seg.aux0 + 1) % seg.length
        seg.step = iteration

    seg.fill(seg.get_color(1))

    for i in range(size):
        pos = (seg.aux0 + i) % seg.length
        seg.set_pixel_color(pos, seg.color_from_palette(pos))

    return FRAMETIME

def mode_police(seg: Segment) -> int:
    """Police lights (red/blue alternating)"""
    cycle_time = 25 + (255 - seg.speed)
    on_time = cycle_time // 2

    now = seg.now()
    iteration = now // cycle_time
    rem = now % cycle_time
    on = rem < on_time

    half = seg.length // 2

    # Red on left, blue on right
    red = (255, 0, 0)
    blue = (0, 0, 255)
    off_color = (0, 0, 0)

    for i in range(half):
        if (iteration % 2 == 0 and on) or (iteration % 2 == 1 and not on):
            seg.set_pixel_color(i, (red[0] << 16) | (red[1] << 8) | red[2])
        else:
            seg.set_pixel_color(i, (off_color[0] << 16) | (off_color[1] << 8) | off_color[2])

    for i in range(half, seg.length):
        if (iteration % 2 == 1 and on) or (iteration % 2 == 0 and not on):
            seg.set_pixel_color(i, (blue[0] << 16) | (blue[1] << 8) | blue[2])
        else:
            seg.set_pixel_color(i, (off_color[0] << 16) | (off_color[1] << 8) | off_color[2])

    return FRAMETIME

def mode_lightning(seg: Segment) -> int:
    """Lightning flash effect"""
    if seg.call == 0:
        seg.aux0 = 0
        seg.aux1 = 0

    cycle_time = 50 + (255 - seg.speed) * 10
    iteration = seg.now() // cycle_time

    if iteration != seg.step:
        # Random chance of lightning
        if random.randint(0, 255) < seg.intensity:
            seg.aux0 = random.randint(3, 8)  # Number of flashes
            seg.aux1 = seg.now()
        seg.step = iteration

    # Flash sequence
    if seg.aux0 > 0:
        flash_duration = 50
        time_since = seg.now() - seg.aux1

        if time_since < flash_duration:
            # Flash on
            brightness = 255 - (time_since * 255 // flash_duration)
            for i in range(seg.length):
                color = color_blend(0, WHITE, brightness)
                seg.set_pixel_color(i, color)
        else:
            # Flash off, wait for next
            if time_since > flash_duration + random.randint(10, 100):
                seg.aux0 -= 1
                seg.aux1 = seg.now()
            else:
                seg.fill(seg.get_color(1))
    else:
        seg.fill(seg.get_color(1))

    return FRAMETIME

def mode_fireworks(seg: Segment) -> int:
    """Fireworks effect"""
    seg.fade_out(64)

    cycle_time = 20 + (255 - seg.speed)
    iteration = seg.now() // cycle_time

    if iteration != seg.step:
        # Launch new firework
        if random.randint(0, 255) < seg.intensity:
            pos = random.randint(0, seg.length - 1)
            color = color_wheel(random.randint(0, 255))

            # Bright center
            seg.set_pixel_color(pos, color)

            # Dimmer neighbors
            if pos > 0:
                seg.set_pixel_color(pos - 1, color_blend(0, color, 128))
            if pos < seg.length - 1:
                seg.set_pixel_color(pos + 1, color_blend(0, color, 128))

        seg.step = iteration

    return FRAMETIME

def mode_ripple(seg: Segment) -> int:
    """Ripple effect"""
    if seg.call == 0:
        seg.data = [0] * seg.length
        seg.aux0 = seg.length // 2

    seg.fade_out(250)

    cycle_time = 50 + (255 - seg.speed) * 2
    iteration = seg.now() // cycle_time

    if iteration != seg.step:
        # New ripple
        if random.randint(0, 255) < seg.intensity:
            seg.aux0 = random.randint(0, seg.length - 1)
            seg.data[seg.aux0] = 255

        # Propagate ripple
        new_data = seg.data.copy()
        for i in range(1, seg.length - 1):
            new_data[i] = (seg.data[i - 1] + seg.data[i + 1]) // 2
        seg.data = new_data

        seg.step = iteration

    for i in range(seg.length):
        if seg.data[i] > 0:
            color = color_blend(seg.get_color(1),
                              seg.color_from_palette(i),
                              seg.data[i])
            seg.set_pixel_color(i, color)

    return FRAMETIME

def mode_flow(seg: Segment) -> int:
    """Smooth flowing color movement"""
    counter = seg.now() * ((seg.speed >> 3) + 1)

    for i in range(seg.length):
        pos = ((i * 256 // seg.length) + counter) & 0xFFFF
        color = color_wheel((pos >> 8) & 0xFF)

        # Apply intensity as brightness modulation
        brightness = 128 + ((sin8((pos >> 7) & 0xFF) - 128) * seg.intensity // 255)
        color = color_blend(0, color, brightness)
        seg.set_pixel_color(i, color)

    return FRAMETIME

def mode_colorloop(seg: Segment) -> int:
    """Smooth color loop across entire strip"""
    counter = (seg.now() * ((seg.speed >> 3) + 1)) & 0xFFFF

    for i in range(seg.length):
        # Create gradient based on position and time
        hue = ((i * 256 // max(1, seg.length)) + (counter >> 7)) & 0xFF
        color = color_wheel(hue)

        # Intensity controls saturation
        if seg.intensity < 255:
            color = color_blend(color, WHITE, 255 - seg.intensity)

        seg.set_pixel_color(i, color)

    return FRAMETIME

def mode_palette_flow(seg: Segment) -> int:
    """Flowing palette colors"""
    counter = seg.now() * ((seg.speed >> 3) + 1)

    for i in range(seg.length):
        # Get color from palette based on position and time
        palette_pos = ((i * 255 // max(1, seg.length)) + (counter >> 7)) & 0xFF
        color = seg.color_from_palette(palette_pos)

        # Intensity controls brightness modulation
        if seg.intensity < 255:
            brightness = 128 + ((sin8(palette_pos) - 128) * seg.intensity // 255)
            color = color_blend(0, color, brightness)

        seg.set_pixel_color(i, color)

    return FRAMETIME

def mode_gradient(seg: Segment) -> int:
    """Smooth gradient between colors"""
    for i in range(seg.length):
        # Create gradient from color 0 to color 2
        blend_amount = (i * 255) // max(1, seg.length - 1)
        color = color_blend(seg.get_color(0), seg.get_color(2), blend_amount)

        # Intensity controls a pulsing brightness
        if seg.intensity > 0:
            counter = (seg.now() * ((seg.speed >> 3) + 1)) & 0xFFFF
            pulse = sin8((counter >> 8) & 0xFF)
            brightness = 128 + ((pulse - 128) * seg.intensity // 255)
            color = color_blend(0, color, brightness)

        seg.set_pixel_color(i, color)

    return FRAMETIME

def mode_multi_strobe(seg: Segment) -> int:
    """Multi-color strobe effect"""
    cycle_time = 50 + (255 - seg.speed)
    flash_duration = max(5, cycle_time // 4)

    now = seg.now()
    iteration = now // cycle_time
    rem = now % cycle_time

    if rem < flash_duration:
        # Strobe on with color from palette
        color_index = (iteration * 85) & 0xFF
        color = color_wheel(color_index)
        seg.fill(color)
    else:
        # Strobe off
        seg.fill(seg.get_color(1))

    return FRAMETIME

def mode_waves(seg: Segment) -> int:
    """Sine wave effect"""
    counter = seg.now() * ((seg.speed >> 3) + 1)

    for i in range(seg.length):
        # Create wave pattern
        wave_pos = (i * 255 // max(1, seg.length)) + (counter >> 7)
        brightness = sin8(wave_pos & 0xFF)

        # Intensity controls wave amplitude
        brightness = 128 + ((brightness - 128) * seg.intensity // 255)

        color = color_blend(seg.get_color(1),
                          seg.color_from_palette(i),
                          brightness)
        seg.set_pixel_color(i, color)

    return FRAMETIME

def mode_bpm(seg: Segment) -> int:
    """BPM (beats per minute) pulse effect"""
    # Calculate BPM based on speed (60-180 BPM)
    bpm = 60 + ((seg.speed * 120) >> 8)
    ms_per_beat = 60000 // bpm

    beat_phase = (seg.now() % ms_per_beat) * 255 // ms_per_beat
    brightness = sin8(beat_phase)

    for i in range(seg.length):
        # Create traveling beat
        offset = (i * 255 // max(1, seg.length))
        local_brightness = sin8((beat_phase + offset) & 0xFF)

        # Intensity controls brightness range
        local_brightness = 128 + ((local_brightness - 128) * seg.intensity // 255)

        color = color_blend(seg.get_color(1),
                          seg.color_from_palette(i),
                          local_brightness)
        seg.set_pixel_color(i, color)

    return FRAMETIME

def mode_juggle(seg: Segment) -> int:
    """Juggling colored dots"""
    if seg.call == 0:
        seg.data = [0] * 8  # Track 8 dot positions

    seg.fade_out(224)

    cycle_time = 10 + (255 - seg.speed) // 2
    iteration = seg.now() // cycle_time

    if iteration != seg.step:
        # Update dot positions using different sine waves
        for dot in range(min(8, 1 + seg.intensity // 32)):
            phase = (seg.now() * (dot + 1)) & 0xFFFF
            pos = (sin16(phase) + 32768) * seg.length // 65536
            pos = max(0, min(seg.length - 1, pos))

            hue = (dot * 32) & 0xFF
            color = color_wheel(hue)
            seg.set_pixel_color(pos, color)

        seg.step = iteration

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
    7: ("Rainbow Cycle", mode_rainbow),
    8: ("Rainbow", mode_rainbow_cycle),
    9: ("Theater Chase", mode_theater_chase),
    10: ("Running Lights", mode_running_lights),
    11: ("Random Color", mode_random_color),
    12: ("Dynamic", mode_dynamic),
    13: ("Twinkle", mode_twinkle),
    14: ("Sparkle", mode_sparkle),
    15: ("Strobe", mode_strobe),
    16: ("Fire", mode_fire),
    17: ("Comet", mode_comet),
    18: ("Chase", mode_chase),
    19: ("Police", mode_police),
    20: ("Lightning", mode_lightning),
    21: ("Fireworks", mode_fireworks),
    22: ("Ripple", mode_ripple),
    23: ("Flow", mode_flow),
    24: ("Colorloop", mode_colorloop),
    25: ("Palette Flow", mode_palette_flow),
    26: ("Gradient", mode_gradient),
    27: ("Multi Strobe", mode_multi_strobe),
    28: ("Waves", mode_waves),
    29: ("BPM", mode_bpm),
    30: ("Juggle", mode_juggle),
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
