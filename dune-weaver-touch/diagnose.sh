#!/bin/bash
# Diagnostic script for Dune Weaver Touch service issues

echo "🔍 Dune Weaver Touch - Service Diagnostics"
echo "=========================================="
echo ""

# Check if service exists
echo "📋 Service Status:"
if systemctl list-unit-files | grep -q "dune-weaver-touch.service"; then
    echo "   ✅ Service file exists"
    systemctl status dune-weaver-touch.service --no-pager -l || true
else
    echo "   ❌ Service not installed"
fi
echo ""

# Check service logs
echo "📝 Recent Service Logs (last 20 lines):"
journalctl -u dune-weaver-touch.service -n 20 --no-pager || echo "   ℹ️  No logs available"
echo ""

# Check backend availability
echo "🌐 Backend Status:"
if curl -s --connect-timeout 2 http://localhost:8080/serial_status > /dev/null 2>&1; then
    echo "   ✅ Backend is running at localhost:8080"
else
    echo "   ❌ Backend not available at localhost:8080"
    echo "   💡 Start backend with: cd ~/dune-weaver && python main.py"
fi
echo ""

# Check virtual environment
echo "🐍 Virtual Environment:"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "$SCRIPT_DIR/venv" ]; then
    echo "   ✅ Virtual environment exists"
    if [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
        echo "   ✅ Python executable found"
        PYTHON_VERSION=$("$SCRIPT_DIR/venv/bin/python" --version 2>&1)
        echo "      Version: $PYTHON_VERSION"
    else
        echo "   ❌ Python executable missing"
    fi
    if [ -f "$SCRIPT_DIR/venv/bin/pip" ]; then
        echo "   ✅ pip is available"
    else
        echo "   ❌ pip is missing - run: sudo ./fix-venv.sh"
    fi
else
    echo "   ❌ Virtual environment not found"
    echo "   💡 Run: sudo ./install.sh"
fi
echo ""

# Check required Python packages
echo "📦 Required Packages:"
if [ -f "$SCRIPT_DIR/venv/bin/pip" ]; then
    PACKAGES="PySide6 requests qasync"
    for pkg in $PACKAGES; do
        if "$SCRIPT_DIR/venv/bin/pip" show "$pkg" > /dev/null 2>&1; then
            VERSION=$("$SCRIPT_DIR/venv/bin/pip" show "$pkg" | grep "Version:" | cut -d' ' -f2)
            echo "   ✅ $pkg ($VERSION)"
        else
            echo "   ❌ $pkg - not installed"
        fi
    done
else
    echo "   ⚠️  Cannot check packages - pip not available"
fi
echo ""

# Check graphics/display
echo "🖥️  Graphics Environment:"
if [ -n "$DISPLAY" ]; then
    echo "   DISPLAY=$DISPLAY"
else
    echo "   ℹ️  No DISPLAY variable (OK for EGLFS mode)"
fi

if [ -c "/dev/fb0" ]; then
    echo "   ✅ Framebuffer device available (/dev/fb0)"
    if [ -r "/dev/fb0" ] && [ -w "/dev/fb0" ]; then
        echo "      ✅ Framebuffer is readable/writable"
    else
        echo "      ⚠️  Framebuffer permissions issue"
        echo "      Current user: $(whoami)"
        echo "      Groups: $(groups)"
        echo "      💡 Add user to 'video' group: sudo usermod -a -G video $(whoami)"
    fi
else
    echo "   ❌ Framebuffer device not found"
fi
echo ""

# Check if desktop is running
echo "🪟 Desktop Environment:"
if pgrep -x "lxsession" > /dev/null || pgrep -x "startx" > /dev/null || pgrep -x "xinit" > /dev/null; then
    echo "   ⚠️  Desktop environment is running"
    echo "   💡 For kiosk mode, disable desktop auto-start:"
    echo "      sudo raspi-config → System Options → Boot/Auto Login → Console Autologin"
    echo "   💡 Or the service will take over the display in EGLFS mode"
else
    echo "   ✅ No desktop environment detected (good for kiosk)"
fi
echo ""

# Check auto-login
echo "👤 Auto-Login Status:"
if [ -f "/etc/systemd/system/getty@tty1.service.d/autologin.conf" ]; then
    echo "   ✅ Auto-login configured"
    cat /etc/systemd/system/getty@tty1.service.d/autologin.conf | grep "ExecStart"
else
    echo "   ❌ Auto-login not configured"
    echo "   💡 Run: sudo ./setup-autologin.sh"
fi
echo ""

# Recommendations
echo "💡 Troubleshooting Tips:"
echo ""
echo "1. Test manually first:"
echo "   cd $SCRIPT_DIR"
echo "   ./run.sh --kiosk"
echo ""
echo "2. If backend isn't running, start it:"
echo "   cd ~/dune-weaver && python main.py &"
echo ""
echo "3. Check service logs in real-time:"
echo "   sudo journalctl -u dune-weaver-touch -f"
echo ""
echo "4. Restart the service:"
echo "   sudo systemctl restart dune-weaver-touch"
echo ""
echo "5. If desktop conflicts, disable it:"
echo "   sudo raspi-config → Boot Options → Console Autologin"
echo ""
