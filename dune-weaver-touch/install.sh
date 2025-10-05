#!/bin/bash
# Dune Weaver Touch - One-Command Installer
# This script sets up everything needed to run Dune Weaver Touch on boot

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

# Function to install system packages
install_system_packages() {
    echo "📦 Installing system dependencies..."

    apt-get update
    apt-get install -y \
        libegl1 \
        libgles2 \
        libgl1-mesa-dri \
        libgbm1 \
        qt6-wayland \
        libgbm-dev \
        libdrm-dev \
        libinput-dev \
        libudev-dev \
        libxkbcommon-dev \
        fbset \
        evtest || {
        echo "   ⚠️  Some packages may not be available, continuing..."
    }

    # Install Qt6 virtual keyboard packages if available (optional)
    apt-get install -y \
        qtvirtualkeyboard-plugin \
        qml-module-qtquick-virtualkeyboard \
        qt6-virtualkeyboard-plugin \
        qml6-module-qt-labs-qmlmodels 2>/dev/null || {
        echo "   ℹ️  Qt6 virtual keyboard not available on this system"
    }

    echo "   📦 System packages installed"
}

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
    
    # Update paths in the service file
    sed "s|/home/pi/dune-weaver-touch|$SCRIPT_DIR|g" "$SCRIPT_DIR/dune-weaver-touch.service" > /tmp/dune-weaver-touch.service
    sed -i "s|User=pi|User=$ACTUAL_USER|g" /tmp/dune-weaver-touch.service
    sed -i "s|Group=pi|Group=$ACTUAL_USER|g" /tmp/dune-weaver-touch.service
    
    # Ensure the ExecStart uses the venv python
    sed -i "s|ExecStart=.*python.*|ExecStart=$SCRIPT_DIR/venv/bin/python $SCRIPT_DIR/main.py|g" /tmp/dune-weaver-touch.service
    
    # Copy service file
    cp /tmp/dune-weaver-touch.service /etc/systemd/system/
    
    # Enable service
    systemctl daemon-reload
    systemctl enable dune-weaver-touch.service
    
    echo "   🚀 Systemd service installed and enabled"
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
        # Ensure python3-venv is installed first
        apt-get install -y python3-venv python3-pip python3-full 2>/dev/null || true
        python3 -m venv "$SCRIPT_DIR/venv" --system-site-packages
    else
        echo "   ℹ️  Virtual environment already exists"
        # Check if venv has pip, if not recreate it
        if [ ! -f "$SCRIPT_DIR/venv/bin/pip" ]; then
            echo "   ⚠️  Virtual environment is broken, recreating..."
            rm -rf "$SCRIPT_DIR/venv"
            apt-get install -y python3-venv python3-pip python3-full 2>/dev/null || true
            python3 -m venv "$SCRIPT_DIR/venv" --system-site-packages
        fi
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

# Main installation process
echo "Starting complete installation..."
echo ""

# Install everything
install_system_packages
setup_python_environment
install_scripts
setup_systemd
setup_kiosk_optimizations

echo ""
echo "🎉 Installation Complete!"
echo "========================"
echo ""
echo "✅ System packages installed (Qt6, EGL, OpenGL ES, etc.)"
echo "✅ Python virtual environment created at: $SCRIPT_DIR/venv"
echo "✅ System scripts installed in /usr/local/bin/"
echo "✅ Systemd service configured for auto-start"
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