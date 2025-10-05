#!/bin/bash
# Quick script to update the systemd service without full reinstall

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTUAL_USER="${SUDO_USER:-$USER}"

echo "🔧 Updating Dune Weaver Touch Service"
echo "======================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run with sudo"
    echo ""
    echo "Usage: sudo ./update-service.sh"
    exit 1
fi

echo "📁 Application directory: $SCRIPT_DIR"
echo "👤 User: $ACTUAL_USER"
echo ""

# Make wrapper script executable
echo "1️⃣  Making startup wrapper executable..."
chmod +x "$SCRIPT_DIR/start-with-fb-check.sh"
chmod +x "$SCRIPT_DIR/run.sh"
echo "   ✅ Scripts are executable"
echo ""

# Update service file with correct paths
echo "2️⃣  Updating service file..."
sed "s|/home/pi/dune-weaver-touch|$SCRIPT_DIR|g" "$SCRIPT_DIR/dune-weaver-touch.service" > /tmp/dune-weaver-touch.service
sed -i "s|User=pi|User=$ACTUAL_USER|g" /tmp/dune-weaver-touch.service
sed -i "s|Group=pi|Group=$ACTUAL_USER|g" /tmp/dune-weaver-touch.service

# Show what will be installed
echo "   Service file contents:"
echo "   ----------------------"
cat /tmp/dune-weaver-touch.service | grep -E "User=|Group=|WorkingDirectory=|ExecStart=" | sed 's/^/   /'
echo ""

# Copy to systemd
cp /tmp/dune-weaver-touch.service /etc/systemd/system/dune-weaver-touch.service
echo "   ✅ Service file updated"
echo ""

# Reload systemd
echo "3️⃣  Reloading systemd..."
systemctl daemon-reload
echo "   ✅ Systemd reloaded"
echo ""

# Enable service
echo "4️⃣  Enabling service for auto-start..."
systemctl enable dune-weaver-touch.service
echo "   ✅ Service enabled"
echo ""

# Check status
echo "5️⃣  Current service status:"
systemctl status dune-weaver-touch --no-pager -l | head -n 8 || true
echo ""

echo "======================================"
echo "✅ Service Update Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo ""
echo "Option 1 - Start service now:"
echo "  sudo systemctl restart dune-weaver-touch"
echo "  sudo journalctl -u dune-weaver-touch -f"
echo ""
echo "Option 2 - Test on next boot:"
echo "  sudo reboot"
echo ""
echo "To check logs after boot:"
echo "  sudo journalctl -u dune-weaver-touch -b"
echo ""
