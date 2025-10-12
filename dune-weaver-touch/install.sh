#!/bin/bash
# Dune Weaver Touch - One-Command Installer
# This script sets up everything needed to run Dune Weaver Touch on boot
#
# Uses linuxfb backend for Qt rendering (software-rendered via Linux framebuffer)
# This provides better compatibility with Raspberry Pi without complex GPU/KMS setup

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTUAL_USER="${SUDO_USER:-$USER}"
USER_HOME=$(eval echo ~$ACTUAL_USER)

echo "🎯 Dune Weaver Touch - Complete Installation"
echo "============================================="
echo "App directory: $SCRIPT_DIR"
echo "User: $ACTUAL_USER"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ This installer must be run with sudo privileges"
    echo ""
    echo "Usage: sudo ./install.sh"
    echo ""
    exit 1
fi

echo "🔧 Installing system components..."
echo ""

# Function to install system scripts
install_scripts() {
    echo "📄 Installing system scripts..."
    
    local scripts=("screen-on" "screen-off" "touch-monitor")
    
    for script in "${scripts[@]}"; do
        local source_path="$SCRIPT_DIR/scripts/$script"
        local target_path="/usr/local/bin/$script"
        
        if [ -f "$source_path" ]; then
            cp "$source_path" "$target_path"
            chmod 755 "$target_path"
            chown root:root "$target_path"
            echo "   ✅ $script → $target_path"
        else
            echo "   ⚠️  $script not found at $source_path"
        fi
    done
    
    echo "   📄 System scripts installed"
}

# Function to setup systemd service
setup_systemd() {
    echo "🚀 Setting up systemd service..."

    # Make startup wrapper executable
    chmod +x "$SCRIPT_DIR/start-with-fb-check.sh"

    # Update paths in the service file
    sed "s|/home/pi/dune-weaver-touch|$SCRIPT_DIR|g" "$SCRIPT_DIR/dune-weaver-touch.service" > /tmp/dune-weaver-touch.service
    sed -i "s|User=pi|User=$ACTUAL_USER|g" /tmp/dune-weaver-touch.service
    sed -i "s|Group=pi|Group=$ACTUAL_USER|g" /tmp/dune-weaver-touch.service

    # Copy service file
    cp /tmp/dune-weaver-touch.service /etc/systemd/system/

    # Enable service
    systemctl daemon-reload
    systemctl enable dune-weaver-touch.service

    echo "   🚀 Systemd service installed and enabled"
}

# Function to setup screen rotation
setup_screen_rotation() {
    echo "🔄 Setting up 180° screen rotation..."

    # Add display rotation to boot config if not already present
    if ! grep -q "display_lcd_rotate=2" /boot/config.txt 2>/dev/null; then
        if [ -f /boot/config.txt ]; then
            echo "display_lcd_rotate=2" >> /boot/config.txt
            echo "   ✅ Display rotation (180°) added to /boot/config.txt"
        else
            echo "   ⚠️  /boot/config.txt not found - rotation not configured"
        fi
    else
        echo "   ℹ️  Display rotation already configured"
    fi

    echo "   🔄 Screen rotation configured"
}

# Function to setup kiosk optimizations
setup_kiosk_optimizations() {
    echo "🖥️  Setting up kiosk optimizations..."

    # Disable boot messages for cleaner boot
    if ! grep -q "quiet splash" /boot/cmdline.txt 2>/dev/null; then
        if [ -f /boot/cmdline.txt ]; then
            cp /boot/cmdline.txt /boot/cmdline.txt.backup
            sed -i 's/$/ quiet splash/' /boot/cmdline.txt
            echo "   ✅ Boot splash enabled"
        fi
    else
        echo "   ℹ️  Boot splash already enabled"
    fi

    # Disable rainbow splash
    if ! grep -q "disable_splash=1" /boot/config.txt 2>/dev/null; then
        if [ -f /boot/config.txt ]; then
            echo "disable_splash=1" >> /boot/config.txt
            echo "   ✅ Rainbow splash disabled"
        fi
    else
        echo "   ℹ️  Rainbow splash already disabled"
    fi

    # Note about auto-login - let user configure manually
    echo "   ℹ️  Auto-login configuration skipped (manual setup recommended)"

    echo "   🖥️  Kiosk optimizations applied"
}

# Function to setup Python virtual environment and install dependencies
setup_python_environment() {
    echo "🐍 Setting up Python virtual environment..."

    # Create virtual environment if it doesn't exist
    if [ ! -d "$SCRIPT_DIR/venv" ]; then
        echo "   📦 Creating virtual environment..."
        python3 -m venv "$SCRIPT_DIR/venv" || {
            echo "   ⚠️  Could not create virtual environment. Installing python3-venv..."
            apt update && apt install -y python3-venv python3-full
            python3 -m venv "$SCRIPT_DIR/venv"
        }
    else
        echo "   ℹ️  Virtual environment already exists"
    fi

    # Activate virtual environment and install dependencies
    echo "   📦 Installing Python dependencies in virtual environment..."
    "$SCRIPT_DIR/venv/bin/python" -m pip install --upgrade pip

    # Install from requirements.txt if it exists, otherwise install manually
    if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
        "$SCRIPT_DIR/venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
    else
        "$SCRIPT_DIR/venv/bin/pip" install PySide6 requests
    fi

    # Change ownership to the actual user (not root)
    chown -R "$ACTUAL_USER:$ACTUAL_USER" "$SCRIPT_DIR/venv"

    echo "   🐍 Python virtual environment ready"
}

# Function to setup patterns directory permissions
setup_patterns_permissions() {
    echo "📁 Setting up patterns directory permissions..."

    # Determine patterns directory location (parent of touch app)
    PATTERNS_DIR="$(dirname "$SCRIPT_DIR")/patterns"

    if [ -d "$PATTERNS_DIR" ]; then
        echo "   📂 Found patterns directory: $PATTERNS_DIR"

        # Ensure cached_images directory exists
        CACHE_DIR="$PATTERNS_DIR/cached_images"
        if [ ! -d "$CACHE_DIR" ]; then
            echo "   📁 Creating cached_images directory..."
            mkdir -p "$CACHE_DIR"
        fi

        # Set ownership to the user who will run the service
        echo "   🔑 Setting ownership to $ACTUAL_USER..."
        chown -R "$ACTUAL_USER:$ACTUAL_USER" "$CACHE_DIR"

        # Set permissions: user can read/write, group can read, others can read
        echo "   🔒 Setting permissions (755 for dirs, 644 for files)..."
        find "$CACHE_DIR" -type d -exec chmod 755 {} \;
        find "$CACHE_DIR" -type f -exec chmod 644 {} \;

        echo "   ✅ Patterns cache directory permissions configured"
    else
        echo "   ⚠️  Patterns directory not found at $PATTERNS_DIR"
        echo "   ℹ️  If patterns exist elsewhere, manually run:"
        echo "      sudo chown -R $ACTUAL_USER:$ACTUAL_USER /path/to/patterns/cached_images"
    fi
}

# Main installation process
echo "Starting complete installation..."
echo ""

# Install everything
setup_python_environment
setup_patterns_permissions
install_scripts
setup_systemd
setup_screen_rotation
setup_kiosk_optimizations

echo ""
echo "🎉 Installation Complete!"
echo "========================"
echo ""
echo "✅ Python virtual environment created at: $SCRIPT_DIR/venv"
echo "✅ Patterns cache directory permissions configured"
echo "✅ System scripts installed in /usr/local/bin/"
echo "✅ Systemd service configured for auto-start"
echo "✅ Screen rotation (180°) configured"
echo "✅ Kiosk optimizations applied"
echo ""
echo "🔧 Service Management:"
echo "   Start now:  sudo systemctl start dune-weaver-touch"
echo "   Stop:       sudo systemctl stop dune-weaver-touch"
echo "   Status:     sudo systemctl status dune-weaver-touch"
echo "   Logs:       sudo journalctl -u dune-weaver-touch -f"
echo ""
echo "🚀 Next Steps:"
echo "   1. Configure auto-login (recommended for kiosk mode):"
echo "      sudo ./setup-autologin.sh    (automated setup)"
echo "      OR manually: sudo raspi-config → System Options → Boot/Auto Login → Desktop Autologin"
echo "   2. Reboot your system to see the full kiosk experience"
echo "   3. The app will start automatically on boot via systemd service"
echo "   4. Check the logs if you encounter any issues"
echo ""
echo "💡 To start the service now without rebooting:"
echo "   sudo systemctl start dune-weaver-touch"
echo ""
echo "🛠️  For development/testing (run manually):"
echo "   cd $SCRIPT_DIR"
echo "   ./run.sh"
echo ""
echo "⚙️  To change boot/login settings later:"
echo "   sudo ./configure-boot.sh"
echo ""

# Ask if user wants to start now
read -p "🤔 Would you like to start the service now? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🚀 Starting Dune Weaver Touch service..."
    systemctl start dune-weaver-touch
    sleep 2
    systemctl status dune-weaver-touch --no-pager -l
    echo ""
    echo "✅ Service started! Check the status above."
fi

echo ""
echo "🎯 Installation completed successfully!"