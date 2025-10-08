#!/usr/bin/env python3
"""
Test script for Hyperion loading and connected effects
This simulates the startup sequence when LEDs are off
"""

import time
import sys
from modules.led.led_interface import LEDInterface

# Configuration
HYPERION_IP = "192.168.2.183"
HYPERION_PORT = 8090

def test_effects():
    """Test Hyperion effects with LEDs off"""
    print(f"Testing Hyperion effects at {HYPERION_IP}:{HYPERION_PORT}")
    print("=" * 60)

    # Create LED interface
    led = LEDInterface(
        provider="hyperion",
        ip_address=HYPERION_IP,
        port=HYPERION_PORT
    )

    # Test 1: Loading effect
    print("\n1. Testing LOADING effect (orange color)...")
    print("   - This should turn on the LEDs")
    print("   - Clear any previous effects")
    print("   - Show orange color")
    result = led.effect_loading()
    print(f"   Result: {'SUCCESS' if result else 'FAILED'}")

    # Wait 5 seconds so you can see the loading effect
    print("\n   Waiting 5 seconds...")
    time.sleep(5)

    # Test 2: Connected effect
    print("\n2. Testing CONNECTED effect (green flash)...")
    print("   - This should flash green twice")
    print("   - Then return to idle state (cleared)")
    result = led.effect_connected()
    print(f"   Result: {'SUCCESS' if result else 'FAILED'}")

    print("\n" + "=" * 60)
    print("Test complete!")
    print("\nDid you see:")
    print("  1. Orange color for ~5 seconds?")
    print("  2. Two green flashes?")
    print("  3. LEDs return to default state after?")

if __name__ == "__main__":
    try:
        test_effects()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
