#!/bin/bash

# Setup Dune Weaver Touch to start automatically on boot

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTUAL_USER="${SUDO_USER:-$USER}"
USER_HOME=$(eval echo ~$ACTUAL_USER)

echo "=== Dune Weaver Touch Auto-Start Setup ==="
echo "App directory: $SCRIPT_DIR"
echo "User: $ACTUAL_USER"
echo ""

# Function to install system scripts
install_scripts() {
    echo "Installing system scripts..."
    
    if [ "$EUID" -ne 0 ]; then
        echo "❌ Script installation requires root privileges. Run with sudo."
        return 1
    fi
    
    "$SCRIPT_DIR/scripts/install-scripts.sh"
    echo "✅ System scripts installed"
}

# Function to setup systemd service
setup_systemd() {
    echo "Setting up systemd service..."
    
    # Check if running as root
    if [ "$EUID" -ne 0 ]; then
        echo "❌ Systemd setup requires root privileges. Run with sudo."
        return 1
    fi
    
    # Install scripts first
    install_scripts
    
    # Update paths in the service file
    sed "s|/home/pi/dune-weaver-touch|$SCRIPT_DIR|g" "$SCRIPT_DIR/dune-weaver-touch.service" > /tmp/dune-weaver-touch.service
    sed -i "s|User=pi|User=$ACTUAL_USER|g" /tmp/dune-weaver-touch.service
    sed -i "s|Group=pi|Group=$ACTUAL_USER|g" /tmp/dune-weaver-touch.service
    
    # Copy service file
    cp /tmp/dune-weaver-touch.service /etc/systemd/system/
    
    # Enable service
    systemctl daemon-reload
    systemctl enable dune-weaver-touch.service
    
    echo "✅ Systemd service installed and enabled"
    echo "   The app will start automatically on boot"
    echo ""
    echo "Service commands:"
    echo "   sudo systemctl start dune-weaver-touch"
    echo "   sudo systemctl stop dune-weaver-touch" 
    echo "   sudo systemctl status dune-weaver-touch"
    echo "   sudo journalctl -u dune-weaver-touch -f"
}

# Function to setup desktop autostart
setup_desktop() {
    echo "Setting up desktop autostart..."
    
    # Create autostart directory if it doesn't exist
    mkdir -p "$USER_HOME/.config/autostart"
    
    # Update paths in desktop file
    sed "s|/home/pi/dune-weaver-touch|$SCRIPT_DIR|g" "$SCRIPT_DIR/dune-weaver-touch.desktop" > "$USER_HOME/.config/autostart/dune-weaver-touch.desktop"
    
    # Make sure the user owns the file
    chown $ACTUAL_USER:$ACTUAL_USER "$USER_HOME/.config/autostart/dune-weaver-touch.desktop"
    
    echo "✅ Desktop autostart configured"
    echo "   The app will start when the user logs in"
}

# Function to setup boot splash (optional)
setup_boot_splash() {
    echo "Setting up boot splash screen..."
    
    if [ "$EUID" -ne 0 ]; then
        echo "❌ Boot splash setup requires root privileges. Run with sudo."
        return 1
    fi
    
    # Disable boot messages for cleaner boot
    if ! grep -q "quiet splash" /boot/cmdline.txt; then
        sed -i 's/$/ quiet splash/' /boot/cmdline.txt
        echo "✅ Boot splash enabled"
    else
        echo "ℹ️  Boot splash already enabled"
    fi
    
    # Disable rainbow splash
    if ! grep -q "disable_splash=1" /boot/config.txt; then
        echo "disable_splash=1" >> /boot/config.txt
        echo "✅ Rainbow splash disabled"
    else
        echo "ℹ️  Rainbow splash already disabled"
    fi
}

# Main menu
echo "Choose setup method:"
echo "1) Systemd service (recommended for headless/kiosk mode)"
echo "2) Desktop autostart (for desktop environments)" 
echo "3) Both systemd + desktop autostart"
echo "4) Install system scripts only"
echo "5) Add boot splash optimizations"
echo "6) Complete kiosk setup (scripts + systemd + boot splash)"
echo ""
read -p "Enter your choice (1-6): " choice

case $choice in
    1)
        setup_systemd
        ;;
    2)
        setup_desktop
        ;;
    3)
        setup_systemd
        setup_desktop
        ;;
    4)
        install_scripts
        ;;
    5)
        setup_boot_splash
        ;;
    6)
        install_scripts
        setup_systemd
        setup_boot_splash
        echo ""
        echo "🎯 Complete kiosk setup done!"
        echo "   Reboot to see the full kiosk experience"
        ;;
    *)
        echo "❌ Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "✅ Setup complete!"