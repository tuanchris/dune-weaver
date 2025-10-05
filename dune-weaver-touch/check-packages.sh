#!/bin/bash
# Check for required system packages for Qt EGLFS on Raspberry Pi

echo "📦 System Package Check for Dune Weaver Touch"
echo "=============================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

MISSING_PACKAGES=()
INSTALLED_PACKAGES=()

# Function to check if package is installed
check_package() {
    local package=$1
    local description=$2

    if dpkg -l | grep -q "^ii  $package "; then
        echo -e "   ${GREEN}✅${NC} $package - $description"
        INSTALLED_PACKAGES+=("$package")
        return 0
    else
        echo -e "   ${RED}❌${NC} $package - $description"
        MISSING_PACKAGES+=("$package")
        return 1
    fi
}

# Core Python packages
echo "🐍 Python & Build Tools:"
check_package "python3" "Python 3 interpreter"
check_package "python3-pip" "Python package installer"
check_package "python3-venv" "Python virtual environment"
check_package "python3-dev" "Python development headers"
check_package "build-essential" "C/C++ compiler and build tools"
echo ""

# Qt6 and graphics libraries
echo "🎨 Qt6 & Graphics Libraries:"
check_package "qt6-base-dev" "Qt6 base development files"
check_package "qt6-declarative-dev" "Qt6 QML/QtQuick development"
check_package "libqt6core6" "Qt6 core library"
check_package "libqt6gui6" "Qt6 GUI library"
check_package "libqt6qml6" "Qt6 QML library"
check_package "libqt6quick6" "Qt6 Quick library"
check_package "qml6-module-qtquick" "Qt6 Quick QML module"
check_package "qml6-module-qtquick-controls" "Qt6 Quick Controls"
check_package "qml6-module-qtquick-layouts" "Qt6 Quick Layouts"
check_package "qml6-module-qtquick-window" "Qt6 Quick Window"
echo ""

# EGL and OpenGL ES
echo "🖼️  EGL & OpenGL ES:"
check_package "libegl1" "EGL library"
check_package "libgles2" "OpenGL ES 2.0 library"
check_package "libegl1-mesa" "Mesa EGL library"
check_package "libgles2-mesa" "Mesa OpenGL ES library" || check_package "libgles2" "OpenGL ES library (alternative)"
check_package "libgl1-mesa-dri" "Mesa DRI drivers"
check_package "libgbm1" "Generic Buffer Management"
echo ""

# DRM and input
echo "🎮 DRM & Input:"
check_package "libdrm2" "Direct Rendering Manager"
check_package "libdrm-dev" "DRM development files"
check_package "libgbm-dev" "GBM development files"
check_package "libinput10" "Input device handling"
check_package "libinput-dev" "Input development files"
check_package "libudev1" "udev library"
check_package "libudev-dev" "udev development files"
check_package "libxkbcommon0" "XKB common library"
check_package "libxkbcommon-dev" "XKB development files"
echo ""

# Qt6 Virtual Keyboard (optional but recommended)
echo "⌨️  Qt6 Virtual Keyboard (Optional):"
check_package "qt6-virtualkeyboard-plugin" "Qt6 virtual keyboard plugin"
check_package "qml6-module-qtquick-virtualkeyboard" "Qt6 virtual keyboard QML module"
echo ""

# Qt6 Wayland support (for desktop testing)
echo "🪟 Qt6 Wayland (For Desktop Testing):"
check_package "qt6-wayland" "Qt6 Wayland platform plugin"
echo ""

# Utilities
echo "🔧 Utilities:"
check_package "fbset" "Framebuffer device maintenance"
check_package "evtest" "Input device event testing"
check_package "curl" "HTTP client for API calls"
echo ""

# Raspberry Pi specific firmware/tools
echo "🥧 Raspberry Pi Specific:"
if [ -f /boot/config.txt ]; then
    echo -e "   ${GREEN}✅${NC} Raspberry Pi detected"

    # Check for VC4/V3D graphics driver
    if lsmod | grep -q "vc4"; then
        echo -e "   ${GREEN}✅${NC} VC4 graphics driver loaded"
    elif lsmod | grep -q "v3d"; then
        echo -e "   ${GREEN}✅${NC} V3D graphics driver loaded"
    else
        echo -e "   ${YELLOW}⚠️${NC}  No VC4/V3D driver loaded (may need to enable)"
        echo "      Check /boot/config.txt for: dtoverlay=vc4-kms-v3d"
    fi

    # Check for firmware
    if [ -d /opt/vc ]; then
        echo -e "   ${GREEN}✅${NC} VideoCore firmware present"
    fi
else
    echo -e "   ${YELLOW}ℹ️${NC}  Not a Raspberry Pi"
fi
echo ""

# Summary
echo "📊 Summary:"
echo "=========="
echo -e "Installed packages: ${GREEN}${#INSTALLED_PACKAGES[@]}${NC}"
echo -e "Missing packages:   ${RED}${#MISSING_PACKAGES[@]}${NC}"
echo ""

if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
    echo -e "${RED}❌ Missing Required Packages:${NC}"
    for pkg in "${MISSING_PACKAGES[@]}"; do
        echo "   - $pkg"
    done
    echo ""

    echo "💡 Install missing packages with:"
    echo ""
    echo "sudo apt update"
    echo "sudo apt install -y \\"
    for pkg in "${MISSING_PACKAGES[@]}"; do
        echo "    $pkg \\"
    done | sed '$ s/ \\$//'
    echo ""
else
    echo -e "${GREEN}✅ All required packages are installed!${NC}"
    echo ""
fi

# Additional checks
echo "🔍 Additional Checks:"
echo ""

# Check kernel modules
echo "Kernel Modules:"
REQUIRED_MODULES="drm vc4"
for mod in $REQUIRED_MODULES; do
    if lsmod | grep -q "^$mod "; then
        echo -e "   ${GREEN}✅${NC} $mod loaded"
    else
        echo -e "   ${YELLOW}⚠️${NC}  $mod not loaded (may be built-in or not needed)"
    fi
done
echo ""

# Check GPU memory (Raspberry Pi specific)
if command -v vcgencmd &> /dev/null; then
    echo "GPU Memory:"
    GPU_MEM=$(vcgencmd get_mem gpu | cut -d= -f2)
    GPU_MEM_NUM=$(echo $GPU_MEM | sed 's/M//')
    if [ "$GPU_MEM_NUM" -ge 128 ]; then
        echo -e "   ${GREEN}✅${NC} GPU Memory: $GPU_MEM (sufficient)"
    else
        echo -e "   ${YELLOW}⚠️${NC}  GPU Memory: $GPU_MEM (recommend at least 128M)"
        echo "      💡 Edit /boot/config.txt and add: gpu_mem=128"
    fi
    echo ""
fi

# Check for conflicting packages
echo "🚫 Checking for Conflicts:"
DESKTOP_PACKAGES="xserver-xorg lightdm gdm3 sddm lxde"
FOUND_DESKTOP=0
for pkg in $DESKTOP_PACKAGES; do
    if dpkg -l | grep -q "^ii  $pkg "; then
        echo -e "   ${YELLOW}⚠️${NC}  $pkg installed (may conflict with EGLFS kiosk mode)"
        FOUND_DESKTOP=1
    fi
done

if [ $FOUND_DESKTOP -eq 0 ]; then
    echo -e "   ${GREEN}✅${NC} No conflicting desktop packages found"
else
    echo ""
    echo "   💡 For kiosk mode, consider:"
    echo "      sudo systemctl disable lightdm  # Disable desktop auto-start"
    echo "      sudo systemctl set-default multi-user.target  # Boot to console"
fi
echo ""

# Final recommendation
if [ ${#MISSING_PACKAGES[@]} -eq 0 ]; then
    echo "🎉 System is ready for Dune Weaver Touch!"
    echo ""
    echo "Next steps:"
    echo "   1. Run: ./check-display.sh    # Check display/framebuffer"
    echo "   2. Run: ./run.sh --kiosk      # Test the application"
else
    echo "⚠️  Install missing packages first, then run this script again"
fi
echo ""
