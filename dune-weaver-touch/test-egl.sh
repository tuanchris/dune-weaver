#!/bin/bash
# Test EGL initialization with detailed debugging

echo "🔍 EGL Initialization Test"
echo "=========================="
echo ""

# Check current user
echo "👤 Current User:"
echo "   User: $(whoami)"
echo "   UID: $(id -u)"
echo "   Groups: $(groups)"
echo ""

# Check DRM/GPU devices and permissions
echo "🎨 DRM/GPU Devices:"
if [ -d "/dev/dri" ]; then
    echo "   /dev/dri contents:"
    ls -la /dev/dri/
    echo ""

    # Check which devices are accessible
    for device in /dev/dri/*; do
        if [ -r "$device" ] && [ -w "$device" ]; then
            echo "   ✅ $device - accessible"
        else
            echo "   ❌ $device - NOT accessible"
            ls -l "$device"
        fi
    done
else
    echo "   ⚠️  /dev/dri not found"
fi
echo ""

# Check framebuffer
echo "📺 Framebuffer:"
if [ -c "/dev/fb0" ]; then
    ls -l /dev/fb0
    if [ -r "/dev/fb0" ] && [ -w "/dev/fb0" ]; then
        echo "   ✅ /dev/fb0 accessible"
    else
        echo "   ❌ /dev/fb0 NOT accessible"
    fi
else
    echo "   ❌ /dev/fb0 not found"
fi
echo ""

# Check what's using the display
echo "🔒 Display Usage:"
if command -v lsof &> /dev/null; then
    echo "   Processes using /dev/fb0:"
    lsof /dev/fb0 2>/dev/null || echo "   (none)"
    echo ""

    if [ -d "/dev/dri" ]; then
        echo "   Processes using DRM devices:"
        for device in /dev/dri/*; do
            PROCS=$(lsof "$device" 2>/dev/null)
            if [ -n "$PROCS" ]; then
                echo "   $device:"
                echo "$PROCS"
            fi
        done
    fi
else
    echo "   lsof not available"
fi
echo ""

# Check for VC4 driver (Raspberry Pi)
echo "🎮 Graphics Driver:"
if lsmod | grep -q "vc4"; then
    echo "   ✅ vc4 driver loaded"
    lsmod | grep vc4
elif lsmod | grep -q "v3d"; then
    echo "   ✅ v3d driver loaded"
    lsmod | grep v3d
else
    echo "   ⚠️  No VC4/V3D driver detected"
fi
echo ""

# Check GPU memory (Raspberry Pi)
if command -v vcgencmd &> /dev/null; then
    echo "🧠 GPU Memory:"
    vcgencmd get_mem gpu
    echo ""
fi

# Test with minimal Qt app
echo "🧪 Testing Qt EGL Initialization..."
echo ""

# Create minimal test Python script
cat > /tmp/test_egl.py << 'EOF'
import sys
import os

# Set environment for EGLFS
os.environ['QT_QPA_PLATFORM'] = 'eglfs'
os.environ['QT_QPA_EGLFS_WIDTH'] = '800'
os.environ['QT_QPA_EGLFS_HEIGHT'] = '480'
os.environ['QT_LOGGING_RULES'] = 'qt.qpa.*=true'

print("Attempting to initialize Qt with EGLFS...")
print(f"User: {os.getuid()}")
print(f"Groups: {os.getgroups()}")

try:
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    print("✅ PySide6 imported successfully")

    app = QGuiApplication(sys.argv)
    print("✅ QGuiApplication created")

    # This is where EGL initialization happens
    print("Platform:", app.platformName())

    print("✅ SUCCESS: EGL initialized!")
    sys.exit(0)

except Exception as e:
    print(f"❌ FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
EOF

# Run the test
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
    echo "Running test with venv Python..."
    "$SCRIPT_DIR/venv/bin/python" /tmp/test_egl.py
    EXIT_CODE=$?
    echo ""

    if [ $EXIT_CODE -eq 0 ]; then
        echo "✅ EGL test PASSED - Qt can initialize EGLFS"
        echo "   The issue may be application-specific"
    else
        echo "❌ EGL test FAILED - System cannot initialize EGLFS"
        echo ""
        echo "Common fixes:"
        echo "1. Add user to video group: sudo usermod -a -G video $(whoami)"
        echo "2. Add user to render group: sudo usermod -a -G render $(whoami)"
        echo "3. Logout and login again (or: newgrp video)"
        echo "4. Stop any desktop: sudo systemctl stop lightdm"
        echo "5. Check GPU memory: vcgencmd get_mem gpu (should be ≥128M)"
    fi
else
    echo "❌ Virtual environment not found"
    echo "   Run: sudo ./install.sh"
fi

# Cleanup
rm -f /tmp/test_egl.py
echo ""
