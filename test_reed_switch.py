#!/usr/bin/env python3
"""
Simple test script to verify reed switch functionality.
Run this script on your Raspberry Pi to test the reed switch.

Usage:
    python test_reed_switch.py [--gpio PIN] [--invert]

Arguments:
    --gpio PIN    GPIO pin number (BCM numbering) to test (default: 18)
    --invert      Invert the switch logic (triggered = LOW instead of HIGH)

Examples:
    python test_reed_switch.py                    # Test GPIO 18 (default, normal logic)
    python test_reed_switch.py --gpio 17          # Test GPIO 17 (normal logic)
    python test_reed_switch.py --gpio 22 --invert # Test GPIO 22 (inverted logic)
"""

import time
import sys
import argparse

try:
    from modules.connection.reed_switch import ReedSwitchMonitor
except ImportError:
    print("Error: Could not import ReedSwitchMonitor")
    print("Make sure you're running this from the dune-weaver directory")
    sys.exit(1)

def main(gpio_pin=18, invert_state=False):
    """
    Test the reed switch on the specified GPIO pin.

    Args:
        gpio_pin: GPIO pin number (BCM numbering) to test
        invert_state: If True, invert the switch logic (triggered = LOW)
    """
    print("=" * 60)
    print(f"Reed Switch Test - GPIO {gpio_pin}")
    if invert_state:
        print("(Inverted Logic: Triggered = LOW)")
    else:
        print("(Normal Logic: Triggered = HIGH)")
    print("=" * 60)
    print()

    # Initialize the reed switch monitor
    print(f"Initializing reed switch monitor on GPIO {gpio_pin}...")
    if invert_state:
        print("Using inverted logic (triggered when pin is LOW)")
    else:
        print("Using normal logic (triggered when pin is HIGH)")
    reed_switch = ReedSwitchMonitor(gpio_pin=gpio_pin, invert_state=invert_state)

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
    print(f"    - One terminal → GPIO {gpio_pin}")
    if invert_state:
        print("    - Other terminal → Ground (for inverted logic)")
        print("    - Pull-up resistor enabled internally")
    else:
        print("    - Other terminal → 3.3V (for normal logic)")
        print("    - Or use internal pull-up and connect to ground")
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
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Test reed switch functionality on Raspberry Pi GPIO pins",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_reed_switch.py                    # Test GPIO 18 (normal logic)
  python test_reed_switch.py --gpio 17          # Test GPIO 17 (normal logic)
  python test_reed_switch.py --gpio 22 --invert # Test GPIO 22 (inverted logic)

Note: Uses BCM GPIO numbering (not physical pin numbers)
      Normal logic: Triggered when HIGH (connected to 3.3V)
      Inverted logic: Triggered when LOW (connected to ground)
        """
    )
    parser.add_argument(
        '--gpio',
        type=int,
        default=18,
        metavar='PIN',
        help='GPIO pin number to test (BCM numbering, default: 18)'
    )
    parser.add_argument(
        '--invert',
        action='store_true',
        help='Invert the switch logic (triggered = LOW instead of HIGH)'
    )

    args = parser.parse_args()

    # Validate GPIO pin range
    if args.gpio < 2 or args.gpio > 27:
        print(f"❌ ERROR: GPIO pin must be between 2 and 27 (got {args.gpio})")
        print("Valid GPIO pins: 2-27 (BCM numbering)")
        sys.exit(1)

    # Run the test
    main(gpio_pin=args.gpio, invert_state=args.invert)
