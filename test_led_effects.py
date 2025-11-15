#!/usr/bin/env python3
"""Test script for per-pattern LED effect functionality."""
import os
import sys
import json

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.core.cache_manager import (
    get_pattern_led_effect,
    set_pattern_led_effect,
    clear_pattern_led_effect,
    load_metadata_cache,
    save_metadata_cache
)

def test_led_effect_storage():
    """Test storing and retrieving LED effects for patterns."""
    print("Testing LED effect storage...")

    # Test pattern
    test_pattern = "test_pattern.thr"

    # Test effect settings
    test_effect = {
        "effect_id": 8,
        "palette_id": 0,
        "speed": 150,
        "intensity": 200,
        "color1": "#ff0000",
        "color2": "#00ff00",
        "color3": "#0000ff"
    }

    # Test 1: Set playing effect
    print("\n1. Setting playing effect for pattern...")
    success = set_pattern_led_effect(test_pattern, "playing", test_effect)
    print(f"   Result: {'✓ Success' if success else '✗ Failed'}")

    # Test 2: Retrieve playing effect
    print("\n2. Retrieving playing effect for pattern...")
    retrieved_effect = get_pattern_led_effect(test_pattern, "playing")
    if retrieved_effect == test_effect:
        print(f"   Result: ✓ Success - Effect matches")
        print(f"   Retrieved: {json.dumps(retrieved_effect, indent=2)}")
    else:
        print(f"   Result: ✗ Failed - Effect doesn't match")
        print(f"   Expected: {json.dumps(test_effect, indent=2)}")
        print(f"   Retrieved: {json.dumps(retrieved_effect, indent=2)}")

    # Test 3: Set idle effect
    test_idle_effect = {
        "effect_id": 0,
        "palette_id": 0,
        "speed": 128,
        "intensity": 128,
        "color1": "#ffffff",
        "color2": "#000000",
        "color3": "#0000ff"
    }
    print("\n3. Setting idle effect for pattern...")
    success = set_pattern_led_effect(test_pattern, "idle", test_idle_effect)
    print(f"   Result: {'✓ Success' if success else '✗ Failed'}")

    # Test 4: Retrieve both effects
    print("\n4. Verifying both effects are stored...")
    playing = get_pattern_led_effect(test_pattern, "playing")
    idle = get_pattern_led_effect(test_pattern, "idle")
    if playing == test_effect and idle == test_idle_effect:
        print(f"   Result: ✓ Success - Both effects stored correctly")
    else:
        print(f"   Result: ✗ Failed - Effects don't match")

    # Test 5: Clear specific effect
    print("\n5. Clearing playing effect...")
    success = clear_pattern_led_effect(test_pattern, "playing")
    print(f"   Result: {'✓ Success' if success else '✗ Failed'}")

    playing = get_pattern_led_effect(test_pattern, "playing")
    idle = get_pattern_led_effect(test_pattern, "idle")
    if playing is None and idle == test_idle_effect:
        print(f"   Result: ✓ Success - Playing cleared, idle remains")
    else:
        print(f"   Result: ✗ Failed")
        print(f"   Playing (should be None): {playing}")
        print(f"   Idle (should exist): {idle}")

    # Test 6: Clear all effects
    print("\n6. Clearing all effects...")
    success = clear_pattern_led_effect(test_pattern)
    print(f"   Result: {'✓ Success' if success else '✗ Failed'}")

    playing = get_pattern_led_effect(test_pattern, "playing")
    idle = get_pattern_led_effect(test_pattern, "idle")
    if playing is None and idle is None:
        print(f"   Result: ✓ Success - All effects cleared")
    else:
        print(f"   Result: ✗ Failed - Effects still exist")
        print(f"   Playing: {playing}")
        print(f"   Idle: {idle}")

    print("\n✓ LED effect storage tests completed!")

if __name__ == "__main__":
    test_led_effect_storage()
