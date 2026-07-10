#!/bin/bash
# Development runner - uses the virtual environment

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if virtual environment exists
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "   Run: sudo ./install.sh"
    echo "   Or manually create: python3 -m venv venv && venv/bin/pip install -r requirements.txt"
    exit 1
fi

# The table (FluidNC firmware) is reached over the network and auto-discovered
# via mDNS, or pinned with DUNE_WEAVER_URL. No local backend is required.
echo ""
echo "🚀 Starting Dune Weaver Touch (development mode)"
echo "   Using virtual environment: $SCRIPT_DIR/venv"
if [ -n "$DUNE_WEAVER_URL" ]; then
    echo "   Table (pinned): $DUNE_WEAVER_URL"
else
    echo "   Table: auto-discovering over mDNS..."
fi
echo "   Press Ctrl+C to stop"
echo ""

cd "$SCRIPT_DIR"

# Detect platform and set appropriate Qt backend
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS - use native cocoa backend (default, no need to set)
    echo "   Platform: macOS (using native cocoa backend)"
    export QT_QPA_PLATFORM=""  # Let Qt use default
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux - check for DRM devices to determine if eglfs is available
    if [ -e /dev/dri/card0 ] || [ -e /dev/dri/card1 ]; then
        echo "   Platform: Linux with DRM (using eglfs backend)"
        export QT_QPA_PLATFORM=eglfs
        export QT_QPA_EGLFS_INTEGRATION=eglfs_kms
        export QT_QPA_EGLFS_KMS_ATOMIC=1
        export QT_QPA_EGLFS_HIDECURSOR=1
        export QT_QPA_EGLFS_ALWAYS_SET_MODE=1

        # Use eglfs_config.json if available
        if [ -f "$SCRIPT_DIR/eglfs_config.json" ]; then
            echo "   Using eglfs config: $SCRIPT_DIR/eglfs_config.json"
            export QT_QPA_EGLFS_KMS_CONFIG="$SCRIPT_DIR/eglfs_config.json"
        fi
    else
        echo "   Platform: Linux without DRM (using xcb/X11 backend)"
        export QT_QPA_PLATFORM=xcb
    fi
else
    echo "   Platform: Unknown (using default Qt backend)"
fi

exec ./venv/bin/python main.py