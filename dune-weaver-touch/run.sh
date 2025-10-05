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

# Parse command line arguments
KIOSK_FLAG=""
if [ "$1" == "--kiosk" ] || [ "$1" == "-k" ]; then
    KIOSK_FLAG="--kiosk"
fi

# Run the application using the virtual environment
echo ""
if [ -n "$KIOSK_FLAG" ]; then
    echo "🚀 Starting Dune Weaver Touch (KIOSK MODE - fullscreen)"
else
    echo "🚀 Starting Dune Weaver Touch (development mode - windowed)"
    echo "   💡 Use './run.sh --kiosk' for fullscreen mode"
fi
echo "   Using virtual environment: $SCRIPT_DIR/venv"
echo "   Connected to backend: $BACKEND_URL"
echo "   Press Ctrl+C to stop"
echo ""

cd "$SCRIPT_DIR"
exec ./venv/bin/python main.py $KIOSK_FLAG