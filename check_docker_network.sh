#!/bin/bash
# Helper script to determine how Docker should access Hyperion on the host

echo "=== Docker Network Configuration Helper ==="
echo ""
echo "Checking your network configuration..."
echo ""

# Check if running in Docker
if [ -f /.dockerenv ]; then
    echo "✓ Running inside Docker container"
    echo ""

    # Show container's network info
    echo "Container IP addresses:"
    ip addr show | grep "inet " | grep -v 127.0.0.1
    echo ""

    # Try to find gateway
    echo "Docker gateway (try this IP for Hyperion):"
    ip route | grep default | awk '{print $3}'
    echo ""

    # Test if we can reach common IPs
    echo "Testing connectivity to potential Hyperion IPs..."

    for IP in "127.0.0.1" "172.17.0.1" "host.docker.internal"; do
        echo -n "  Testing $IP:8090 ... "
        if timeout 2 bash -c "echo > /dev/tcp/$IP/8090" 2>/dev/null; then
            echo "✓ REACHABLE (use this!)"
        else
            echo "✗ Not reachable"
        fi
    done
else
    echo "✓ Running on host (not in Docker)"
    echo ""

    # Show host network info
    echo "Host IP addresses:"
    if command -v ip &> /dev/null; then
        ip addr show | grep "inet " | grep -v 127.0.0.1
    else
        ifconfig | grep "inet " | grep -v 127.0.0.1
    fi
    echo ""

    echo "For Docker containers to reach Hyperion on this host, use one of:"
    echo "  1. Run container with --network host, then use: 127.0.0.1"
    echo "  2. Use Docker gateway IP: 172.17.0.1 (most common)"
    echo "  3. Use host's LAN IP (shown above)"
fi

echo ""
echo "=== Recommendations ==="
echo "If your Docker container is on Raspberry Pi:"
echo "  • Best: Add --network host to docker run, use 127.0.0.1:8090"
echo "  • Alternative: Use 172.17.0.1:8090 (Docker bridge gateway)"
echo ""
