#!/bin/bash
#
# Dune Weaver - Autohotspot Setup
#
# Sets up the autohotspot system so the Pi creates a "Dune Weaver" WiFi
# hotspot when no known network is available. Users connect to the hotspot
# and configure WiFi through the Dune Weaver app.
#
# DNS redirect for captive portal is handled by NetworkManager's built-in
# dnsmasq (via dnsmasq-shared.d config), not a separate dnsmasq instance.
#
# Run: bash wifi/setup-wifi.sh
# Or:  dw wifi setup
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Determine script and project directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

HOTSPOT_CON_NAME="DuneWeaver-Hotspot"
HOTSPOT_SSID="Dune Weaver"
HOTSPOT_IP="10.42.0.1/24"
IFACE="wlan0"
NM_DNSMASQ_DIR="/etc/NetworkManager/dnsmasq-shared.d"

print_step() {
    echo -e "\n${BLUE}==>${NC} ${GREEN}$1${NC}"
}

print_success() {
    echo -e "${GREEN}$1${NC}"
}

print_warning() {
    echo -e "${YELLOW}Warning:${NC} $1"
}

print_error() {
    echo -e "${RED}Error:${NC} $1"
}

# Check prerequisites
check_prereqs() {
    print_step "Checking prerequisites..."

    # Check for NetworkManager
    if ! command -v nmcli &>/dev/null; then
        print_error "NetworkManager (nmcli) not found. This requires Pi OS Trixie or later."
        exit 1
    fi

    # Check for wlan0
    if ! nmcli dev show "$IFACE" &>/dev/null; then
        print_warning "WiFi interface '$IFACE' not found. Hotspot may not work."
    fi

    print_success "Prerequisites OK"
}

# Create the NetworkManager hotspot connection profile
create_hotspot_profile() {
    print_step "Creating hotspot connection profile..."

    # Remove existing profile if present
    if nmcli con show "$HOTSPOT_CON_NAME" &>/dev/null; then
        echo "Removing existing hotspot profile..."
        sudo nmcli con delete "$HOTSPOT_CON_NAME" 2>/dev/null || true
    fi

    # Read app name from state.json if available
    local ssid="$HOTSPOT_SSID"
    local state_file="$PROJECT_DIR/state.json"
    if [ -f "$state_file" ]; then
        local app_name
        app_name=$(python3 -c "import json; print(json.load(open('$state_file')).get('app_name', ''))" 2>/dev/null || true)
        if [ -n "$app_name" ]; then
            ssid="$app_name"
            echo "Using app name from state.json: $ssid"
        fi
    fi

    # Create the hotspot profile (open network, no password)
    sudo nmcli con add type wifi ifname "$IFACE" mode ap con-name "$HOTSPOT_CON_NAME" \
        ssid "$ssid" autoconnect no \
        ipv4.method shared ipv4.addresses "$HOTSPOT_IP"

    print_success "Hotspot profile created: SSID='$ssid', IP=${HOTSPOT_IP%/*}"
}

# Install DNS redirect config for captive portal
install_dns_redirect() {
    print_step "Installing DNS redirect for captive portal..."

    # NetworkManager's shared mode runs its own dnsmasq.
    # Configs in dnsmasq-shared.d/ are loaded automatically when a shared
    # connection is active. This redirects ALL DNS to the Pi's hotspot IP,
    # triggering captive portal detection on phones/tablets.
    sudo mkdir -p "$NM_DNSMASQ_DIR"
    sudo cp "$SCRIPT_DIR/dnsmasq-hotspot.conf" "$NM_DNSMASQ_DIR/dune-weaver-captive.conf"

    print_success "DNS redirect installed at $NM_DNSMASQ_DIR/dune-weaver-captive.conf"
}

# Copy autohotspot script and service
install_configs() {
    print_step "Installing autohotspot script..."

    # Copy autohotspot script
    sudo cp "$SCRIPT_DIR/autohotspot" /usr/local/bin/autohotspot
    sudo chmod +x /usr/local/bin/autohotspot
    echo "Installed /usr/local/bin/autohotspot"

    print_success "Autohotspot script installed"
}

# Install and enable the systemd service
install_service() {
    print_step "Installing autohotspot service..."

    sudo cp "$SCRIPT_DIR/autohotspot.service" /etc/systemd/system/autohotspot.service
    sudo systemctl daemon-reload
    sudo systemctl enable autohotspot.service

    print_success "autohotspot.service installed and enabled"
}

# Main
main() {
    echo -e "${GREEN}Dune Weaver Autohotspot Setup${NC}"
    echo ""

    check_prereqs
    create_hotspot_profile
    install_dns_redirect
    install_configs
    install_service

    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}   Autohotspot Setup Complete!${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo "On next boot, the Pi will:"
    echo "  1. Scan for known WiFi networks (30s timeout)"
    echo "  2. If found → connect normally"
    echo "  3. If not found → create a '$(nmcli -t -f 802-11-wireless.ssid con show "$HOTSPOT_CON_NAME" 2>/dev/null | cut -d: -f2 || echo "$HOTSPOT_SSID")' hotspot"
    echo ""
    echo "Users can connect to the hotspot and open the Dune Weaver app"
    echo "to configure WiFi credentials."
    echo ""
    echo "Commands:"
    echo "  dw wifi status   — Show current WiFi mode"
    echo "  dw wifi hotspot  — Manually switch to hotspot mode"
    echo "  dw wifi scan     — Scan for available networks"
}

main "$@"
