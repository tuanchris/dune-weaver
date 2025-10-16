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

# Check if backend is running at localhost:8080
echo "🔍 Checking backend availability at localhost:8080..."
BACKEND_URL="http://localhost:8080"
MAX_ATTEMPTS=30
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if curl -s --connect-timeout 2 "$BACKEND_URL/serial_status" > /dev/null 2>&1; then
        echo "✅ Backend is available at localhost:8080"
        break
    else
        ATTEMPT=$((ATTEMPT + 1))
        if [ $ATTEMPT -eq 1 ]; then
            echo "⏳ Waiting for backend to become available..."
            echo "   Make sure the main Dune Weaver application is running"
            echo "   Attempting connection ($ATTEMPT/$MAX_ATTEMPTS)..."
        elif [ $((ATTEMPT % 5)) -eq 0 ]; then
            echo "   Still waiting... ($ATTEMPT/$MAX_ATTEMPTS)"
        fi
        sleep 1
    fi
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo "❌ Backend not available after $MAX_ATTEMPTS attempts"
    echo "   Please ensure the main Dune Weaver application is running at localhost:8080"
    echo "   You can start it with: cd .. && python main.py"
    exit 1
fi

# Run the application using the virtual environment
echo ""
echo "🚀 Starting Dune Weaver Touch (development mode)"
echo "   Using virtual environment: $SCRIPT_DIR/venv"
echo "   Connected to backend: $BACKEND_URL"
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

        # Touchscreen configuration (adjust event number if needed)
        if [ -e /dev/input/event0 ]; then
            export QT_QPA_EVDEV_TOUCHSCREEN_PARAMETERS=/dev/input/event0:rotate=0
        fi

        # Use eglfs_config.json with corrected connector name (DSI-1)
        if [ -f "$SCRIPT_DIR/eglfs_config.json" ]; then
            echo "   Using eglfs config: $SCRIPT_DIR/eglfs_config.json"
            export QT_QPA_EGLFS_KMS_CONFIG="$SCRIPT_DIR/eglfs_config.json"
        else
            echo "   EGLFS mode: Auto-detection (no config file)"
        fi
    else
        echo "   Platform: Linux without DRM (using xcb/X11 backend)"
        export QT_QPA_PLATFORM=xcb
    fi
else
    echo "   Platform: Unknown (using default Qt backend)"
fi

exec ./venv/bin/python main.py