#!/bin/bash
# Check display/framebuffer status before starting kiosk mode

echo "🔍 Display & Framebuffer Status Check"
echo "======================================"
echo ""

# Check if running as root (should NOT be)
if [ "$EUID" -eq 0 ]; then
    echo "⚠️  WARNING: You are running this as root/sudo"
    echo "   This is for checking only. When you run the app, do NOT use sudo!"
    echo "   EGL/GPU access fails when running as root."
    echo ""
fi

# Check for running display servers
echo "🖥️  Display Servers:"
if pgrep -x "Xorg" > /dev/null; then
    echo "   ⚠️  X11 (Xorg) is running - PID: $(pgrep -x Xorg)"
    echo "      This will conflict with EGLFS!"
    echo "      💡 Stop with: sudo systemctl stop lightdm"
elif pgrep -x "weston" > /dev/null; then
    echo "   ⚠️  Wayland (Weston) is running - PID: $(pgrep -x weston)"
    echo "      This will conflict with EGLFS!"
    echo "      💡 Stop with: pkill weston"
elif pgrep "lxsession" > /dev/null; then
    echo "   ⚠️  LXDE desktop is running"
    echo "      This will conflict with EGLFS!"
    echo "      💡 Stop with: sudo systemctl stop lightdm"
else
    echo "   ✅ No display server detected (good for EGLFS)"
fi
echo ""

# Check framebuffer
echo "📺 Framebuffer Device:"
if [ -c "/dev/fb0" ]; then
    echo "   ✅ /dev/fb0 exists"

    # Check permissions
    if [ -r "/dev/fb0" ] && [ -w "/dev/fb0" ]; then
        echo "   ✅ Readable and writable by current user"
    else
        echo "   ⚠️  Permission issue!"
        ls -l /dev/fb0
        echo "      Current user: $(whoami)"
        echo "      Groups: $(groups)"
        echo "      💡 Fix: sudo usermod -a -G video $(whoami)"
        echo "      Then logout and login again"
    fi

    # Check if framebuffer is in use
    if lsof /dev/fb0 2>/dev/null | grep -v "COMMAND" > /dev/null; then
        echo "   ⚠️  Framebuffer is in use by:"
        lsof /dev/fb0 2>/dev/null || true
    else
        echo "   ✅ Framebuffer is available (not in use)"
    fi
else
    echo "   ❌ /dev/fb0 not found!"
fi
echo ""

# Check DRM devices
echo "🎨 DRM/GPU Devices:"
if [ -d "/dev/dri" ]; then
    echo "   ✅ /dev/dri exists"
    ls -la /dev/dri/

    # Check permissions on DRM devices
    for device in /dev/dri/*; do
        if [ -r "$device" ] && [ -w "$device" ]; then
            echo "   ✅ $device is accessible"
        else
            echo "   ⚠️  $device has permission issues"
            echo "      💡 Fix: sudo usermod -a -G video,render $(whoami)"
        fi
    done
else
    echo "   ℹ️  /dev/dri not found (may use legacy fb0 only)"
fi
echo ""

# Check user groups
echo "👤 User Groups:"
CURRENT_USER=$(whoami)
GROUPS=$(groups)
echo "   User: $CURRENT_USER"
echo "   Groups: $GROUPS"

if echo "$GROUPS" | grep -q "video"; then
    echo "   ✅ In 'video' group"
else
    echo "   ⚠️  NOT in 'video' group"
    echo "      💡 Fix: sudo usermod -a -G video $CURRENT_USER"
fi

if echo "$GROUPS" | grep -q "render"; then
    echo "   ✅ In 'render' group (good for DRM)"
else
    echo "   ℹ️  Not in 'render' group (may be needed for some GPUs)"
    echo "      💡 Add with: sudo usermod -a -G render $CURRENT_USER"
fi
echo ""

# Check console
echo "🖥️  Console Status:"
if [ -n "$DISPLAY" ]; then
    echo "   ⚠️  DISPLAY=$DISPLAY is set"
    echo "      This suggests X11 is running"
    echo "      💡 For EGLFS, unset with: unset DISPLAY"
else
    echo "   ✅ DISPLAY not set (good for EGLFS)"
fi

if [ "$(tty)" = "not a tty" ]; then
    echo "   ⚠️  Not running from a TTY"
else
    echo "   ✅ Running from TTY: $(tty)"
fi
echo ""

# Recommendations
echo "💡 Recommendations:"
echo ""

ISSUES=0

if pgrep -x "Xorg\|weston\|lxsession" > /dev/null; then
    echo "1. ⚠️  CRITICAL: Stop the desktop environment"
    echo "   sudo systemctl stop lightdm"
    echo "   # OR for other DMs:"
    echo "   sudo systemctl stop gdm"
    echo "   sudo systemctl stop sddm"
    echo ""
    ISSUES=$((ISSUES + 1))
fi

if ! echo "$(groups)" | grep -q "video"; then
    echo "2. ⚠️  Add user to video group:"
    echo "   sudo usermod -a -G video $(whoami)"
    echo "   Then logout and login again"
    echo ""
    ISSUES=$((ISSUES + 1))
fi

if [ ! -r "/dev/fb0" ] || [ ! -w "/dev/fb0" ]; then
    echo "3. ⚠️  Fix framebuffer permissions"
    echo "   (Should be fixed by adding to video group)"
    echo ""
    ISSUES=$((ISSUES + 1))
fi

if [ $ISSUES -eq 0 ]; then
    echo "✅ All checks passed! Ready to run in EGLFS mode"
    echo ""
    echo "Start with:"
    echo "   ./run.sh --kiosk"
else
    echo "❌ Found $ISSUES issue(s) that need to be fixed"
    echo ""
    echo "After fixing, reboot or re-login for group changes to take effect"
fi
echo ""
