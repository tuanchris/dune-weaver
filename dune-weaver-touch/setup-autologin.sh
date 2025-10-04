#!/bin/bash
# Quick auto-login setup for Dune Weaver Touch

set -e

if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run as root (use sudo)"
    exit 1
fi

ACTUAL_USER="${SUDO_USER:-$USER}"

echo "🔑 Dune Weaver Touch - Auto-Login Setup"
echo "======================================="
echo "User: $ACTUAL_USER"
echo ""

# Check if raspi-config is available
if command -v raspi-config >/dev/null 2>&1; then
    echo "🔧 Setting up auto-login using raspi-config..."
    
    # Use raspi-config to enable auto-login to desktop
    raspi-config nonint do_boot_behaviour B4
    
    if [ $? -eq 0 ]; then
        echo "✅ Auto-login configured successfully!"
        echo ""
        echo "📝 What was configured:"
        echo "   - Boot to desktop with auto-login enabled"
        echo "   - User: $ACTUAL_USER"
        echo "   - The Dune Weaver service will start automatically"
        echo ""
        echo "🚀 Reboot to see the changes:"
        echo "   sudo reboot"
    else
        echo "❌ raspi-config failed. Try manual configuration:"
        echo "   sudo raspi-config"
        echo "   → System Options → Boot/Auto Login → Desktop Autologin"
    fi
else
    echo "⚠️  raspi-config not found."
    echo ""
    echo "Manual alternatives:"
    echo "1. If you have a desktop environment with lightdm:"
    echo "   sudo nano /etc/lightdm/lightdm.conf"
    echo "   Uncomment and set: autologin-user=$ACTUAL_USER"
    echo ""
    echo "2. For console auto-login (minimal systems):"
    echo "   sudo systemctl edit getty@tty1"
    echo "   Add: [Service]"
    echo "        ExecStart="
    echo "        ExecStart=-/sbin/agetty --autologin $ACTUAL_USER --noclear %I \\$TERM"
    echo ""
fi

echo ""
echo "ℹ️  The Dune Weaver Touch service is already configured to start automatically."
echo "   After enabling auto-login and rebooting, you'll have a complete kiosk setup!"