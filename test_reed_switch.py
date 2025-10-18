#!/usr/bin/env python3
"""
Simple test script to verify reed switch functionality on GPIO 18.
Run this script on your Raspberry Pi to test the reed switch.

Usage:
    python test_reed_switch.py
"""

import time
import sys

try:
    from modules.connection.reed_switch import ReedSwitchMonitor
except ImportError:
    print("Error: Could not import ReedSwitchMonitor")
    print("Make sure you're running this from the dune-weaver directory")
    sys.exit(1)

def main():
    print("=" * 60)
    print("Reed Switch Test - GPIO 18")
    print("=" * 60)
    print()

    # Initialize the reed switch monitor
    print("Initializing reed switch monitor on GPIO 18...")
    reed_switch = ReedSwitchMonitor(gpio_pin=18)

    # Check if we're on a Raspberry Pi
    if not reed_switch.is_raspberry_pi:
        print("❌ ERROR: Not running on a Raspberry Pi!")
        print("This test must be run on a Raspberry Pi with GPIO support.")
        return

    print("✓ Running on Raspberry Pi")
    print("✓ GPIO initialized successfully")
    print()
    print("=" * 60)
    print("MONITORING REED SWITCH")
    print("=" * 60)
    print()
    print("Instructions:")
    print("  • The reed switch should be connected:")
    print("    - One terminal → GPIO 18")
    print("    - Other terminal → Ground (any GND pin)")
    print()
    print("  • Bring a magnet close to the reed switch to trigger it")
    print("  • You should see 'TRIGGERED!' when the switch closes")
    print("  • Press Ctrl+C to exit")
    print()
    print("-" * 60)

    try:
        last_state = None
        trigger_count = 0

        while True:
            # Check if reed switch is triggered
            is_triggered = reed_switch.is_triggered()

            # Only print when state changes (to avoid spam)
            if is_triggered != last_state:
                if is_triggered:
                    trigger_count += 1
                    print(f"🔴 TRIGGERED! (count: {trigger_count})")
                else:
                    print("⚪ Not triggered")

                last_state = is_triggered

            # Small delay to avoid overwhelming the GPIO
            time.sleep(0.05)

    except KeyboardInterrupt:
        print()
        print("-" * 60)
        print(f"✓ Test completed. Reed switch was triggered {trigger_count} times.")
        print()

    finally:
        # Clean up GPIO
        reed_switch.cleanup()
        print("✓ GPIO cleaned up")
        print()

if __name__ == "__main__":
    main()
