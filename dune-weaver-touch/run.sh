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
    # Linux/Raspberry Pi - use linuxfb for all Pi models
    if [ -e /dev/fb0 ]; then
        # Check if Pi 5 - needs explicit rotation
        PI_MODEL=$(cat /proc/device-tree/model 2>/dev/null | tr -d '\0' || echo "unknown")
        if [[ "$PI_MODEL" == *"Pi 5"* ]]; then
            echo "   Platform: Raspberry Pi 5 (using linuxfb with 180° rotation)"
            export QT_QPA_PLATFORM=linuxfb:fb=/dev/fb0:rotation=180
        else
            echo "   Platform: Linux (using linuxfb backend)"
            export QT_QPA_PLATFORM=linuxfb:fb=/dev/fb0
        fi
        export QT_QPA_FB_HIDECURSOR=1
    else
        echo "   Platform: Linux (using xcb/X11 backend)"
        export QT_QPA_PLATFORM=xcb
    fi
else
    echo "   Platform: Unknown (using default Qt backend)"
fi

exec ./venv/bin/python main.py