#!/bin/bash
# Diagnostic script to check boot auto-start issues

echo "=========================================="
echo "Dune Weaver Touch Boot Diagnostics"
echo "=========================================="
echo ""

# Check if service file is installed
echo "1. Service Installation:"
if [ -f /etc/systemd/system/dune-weaver-touch.service ]; then
    echo "   ✅ Service file exists"
    echo "   Path: /etc/systemd/system/dune-weaver-touch.service"
else
    echo "   ❌ Service file NOT found!"
fi
echo ""

# Check if service is enabled
echo "2. Service Enabled Status:"
if systemctl is-enabled dune-weaver-touch >/dev/null 2>&1; then
    echo "   ✅ Service is enabled for auto-start"
else
    echo "   ❌ Service is NOT enabled!"
    echo "   Run: sudo systemctl enable dune-weaver-touch"
fi
echo ""

# Check service status
echo "3. Current Service Status:"
systemctl status dune-weaver-touch --no-pager -l | head -n 10
echo ""

# Check framebuffer device
echo "4. Framebuffer Device:"
if [ -c /dev/fb0 ]; then
    echo "   ✅ /dev/fb0 exists"
    ls -la /dev/fb0
    if command -v fbset >/dev/null 2>&1; then
        echo ""
        echo "   Framebuffer info:"
        fbset -fb /dev/fb0 2>&1 | head -n 5
    fi
else
    echo "   ❌ /dev/fb0 NOT found!"
fi
echo ""

# Check wrapper script
echo "5. Startup Wrapper Script:"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/start-with-fb-check.sh" ]; then
    echo "   ✅ Wrapper script exists"
    ls -la "$SCRIPT_DIR/start-with-fb-check.sh"
    if [ -x "$SCRIPT_DIR/start-with-fb-check.sh" ]; then
        echo "   ✅ Wrapper is executable"
    else
        echo "   ❌ Wrapper is NOT executable!"
        echo "   Run: chmod +x $SCRIPT_DIR/start-with-fb-check.sh"
    fi
else
    echo "   ❌ Wrapper script NOT found!"
fi
echo ""

# Check service logs
echo "6. Recent Service Logs (last 20 lines):"
echo "   ----------------------------------------"
sudo journalctl -u dune-weaver-touch -n 20 --no-pager
echo ""

# Check boot logs
echo "7. Service Logs from Last Boot:"
echo "   ----------------------------------------"
sudo journalctl -u dune-weaver-touch -b --no-pager | tail -n 30
echo ""

# Check Python and venv
echo "8. Python Virtual Environment:"
if [ -d "$SCRIPT_DIR/venv" ]; then
    echo "   ✅ Virtual environment exists"
    if [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
        echo "   ✅ Python binary exists"
        echo "   Version: $("$SCRIPT_DIR/venv/bin/python" --version)"
    else
        echo "   ❌ Python binary NOT found in venv!"
    fi
else
    echo "   ❌ Virtual environment NOT found!"
    echo "   Run: sudo ./install.sh"
fi
echo ""

# Check main.py
echo "9. Application Files:"
if [ -f "$SCRIPT_DIR/main.py" ]; then
    echo "   ✅ main.py exists"
else
    echo "   ❌ main.py NOT found!"
fi
echo ""

# Recommendations
echo "=========================================="
echo "Recommendations:"
echo "=========================================="

# Check if any critical issues
ISSUES=0

if ! systemctl is-enabled dune-weaver-touch >/dev/null 2>&1; then
    echo "❌ Enable the service: sudo systemctl enable dune-weaver-touch"
    ISSUES=$((ISSUES + 1))
fi

if [ ! -x "$SCRIPT_DIR/start-with-fb-check.sh" ]; then
    echo "❌ Make wrapper executable: chmod +x $SCRIPT_DIR/start-with-fb-check.sh"
    ISSUES=$((ISSUES + 1))
fi

if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "❌ Reinstall: sudo ./install.sh"
    ISSUES=$((ISSUES + 1))
fi

if systemctl is-failed dune-weaver-touch >/dev/null 2>&1; then
    echo "⚠️  Service has failed - check logs above"
    echo "   Try: sudo systemctl restart dune-weaver-touch"
    ISSUES=$((ISSUES + 1))
fi

if [ $ISSUES -eq 0 ]; then
    echo "✅ No critical issues detected"
    echo ""
    echo "If auto-start still doesn't work:"
    echo "1. Check logs: sudo journalctl -u dune-weaver-touch -b"
    echo "2. Try manual start: sudo systemctl start dune-weaver-touch"
    echo "3. Check for errors in output above"
fi

echo ""
echo "=========================================="
