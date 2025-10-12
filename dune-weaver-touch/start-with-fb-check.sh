#!/bin/bash
# Startup wrapper that waits for framebuffer to be ready

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAX_WAIT=30  # Maximum 30 seconds to wait for framebuffer

echo "🖥️  Waiting for framebuffer device to be ready..."

# Wait for framebuffer device to exist and be accessible
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if [ -c /dev/fb0 ]; then
        echo "✅ Framebuffer /dev/fb0 is ready"

        # Additional check: try to read framebuffer info
        if command -v fbset >/dev/null 2>&1; then
            if fbset -fb /dev/fb0 >/dev/null 2>&1; then
                echo "✅ Framebuffer is initialized and readable"
                break
            else
                echo "⏳ Framebuffer exists but not fully initialized (${WAITED}s)..."
            fi
        else
            # If fbset not available, just check device existence
            echo "✅ Framebuffer device exists (fbset not available for detailed check)"
            break
        fi
    else
        echo "⏳ Waiting for framebuffer device (${WAITED}s)..."
    fi

    sleep 1
    WAITED=$((WAITED + 1))
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "❌ Timeout waiting for framebuffer after ${MAX_WAIT}s"
    echo "⚠️  Starting anyway - application may fail"
fi

# Additional delay for DRM/KMS subsystem to stabilize
echo "⏳ Waiting for graphics subsystem to stabilize..."
sleep 2

echo "🚀 Starting Dune Weaver Touch..."
cd "$SCRIPT_DIR"

# Configure Qt platform environment variables
export QT_QPA_PLATFORM=linuxfb
export QT_QPA_FB_DRM=1
export QT_QPA_FONTDIR=/usr/share/fonts

# Configure touch screen rotation (180 degrees)
export QT_QPA_EVDEV_TOUCHSCREEN_PARAMETERS=/dev/input/event0:rotate=180

exec ./venv/bin/python main.py
