#!/bin/bash
#
# Dune Weaver Raspberry Pi Setup Script
#
# ONE-COMMAND INSTALL (recommended):
#   curl -fsSL https://raw.githubusercontent.com/tuanchris/dune-weaver/main/setup-pi.sh | bash
#
# OR from existing clone:
#   git clone https://github.com/tuanchris/dune-weaver --single-branch
#   cd dune-weaver
#   bash setup-pi.sh
#
# Options:
#   --no-wifi-fix   Skip WiFi stability fix
#   --no-hotspot    Skip autohotspot setup
#   --help          Show help
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Resolve the real user when run via sudo
if [[ -n "$SUDO_USER" ]]; then
    REAL_USER="$SUDO_USER"
    REAL_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
else
    REAL_USER="$USER"
    REAL_HOME="$HOME"
fi

# Default options
FIX_WIFI=true  # Applied by default for stability
SETUP_HOTSPOT=true  # Autohotspot for first-time WiFi setup
INSTALL_DIR="$REAL_HOME/dune-weaver"
REPO_URL="https://github.com/tuanchris/dune-weaver"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-wifi-fix)
            FIX_WIFI=false
            shift
            ;;
        --no-hotspot)
            SETUP_HOTSPOT=false
            shift
            ;;
        --help|-h)
            echo "Dune Weaver Raspberry Pi Setup Script"
            echo ""
            echo "One-command install:"
            echo "  curl -fsSL https://raw.githubusercontent.com/tuanchris/dune-weaver/main/setup-pi.sh | bash"
            echo ""
            echo "Or from existing clone:"
            echo "  cd ~/dune-weaver && bash setup-pi.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --no-wifi-fix   Skip WiFi stability fix (applied by default)"
            echo "  --no-hotspot    Skip autohotspot setup"
            echo "  --help, -h      Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Helper functions
print_step() {
    echo -e "\n${BLUE}==>${NC} ${GREEN}$1${NC}"
}

print_warning() {
    echo -e "${YELLOW}Warning:${NC} $1"
}

print_error() {
    echo -e "${RED}Error:${NC} $1"
}

print_success() {
    echo -e "${GREEN}$1${NC}"
}

# Install system dependencies
install_system_deps() {
    print_step "Installing system dependencies..."
    sudo apt update
    sudo DEBIAN_FRONTEND=noninteractive apt install -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" \
        python3-venv python3-pip python3-dev \
        gcc g++ make swig scons \
        libjpeg-dev zlib1g-dev \
        libgpiod-dev gpiod \
        curl nginx git vim
    print_success "System dependencies installed"
}

# Install Node.js 20 via nodesource
install_nodejs() {
    print_step "Installing Node.js..."

    if command -v node &> /dev/null; then
        local node_version
        node_version=$(node --version)
        echo "Node.js already installed: $node_version"
        # Check if version is 20+
        local major
        major=$(echo "$node_version" | sed 's/v//' | cut -d. -f1)
        if [[ "$major" -ge 20 ]]; then
            print_success "Node.js version is sufficient"
            return
        fi
        echo "Upgrading to Node.js 20..."
    fi

    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo DEBIAN_FRONTEND=noninteractive apt install -y nodejs
    print_success "Node.js $(node --version) installed"
}

# Check if running on Raspberry Pi
check_raspberry_pi() {
    print_step "Checking system compatibility..."

    if [[ ! -f /proc/device-tree/model ]]; then
        print_warning "Could not detect Raspberry Pi model. Continuing anyway..."
        return
    fi

    MODEL=$(tr -d '\0' < /proc/device-tree/model)
    echo "Detected: $MODEL"

    # Check for 64-bit OS
    ARCH=$(uname -m)
    if [[ "$ARCH" != "aarch64" && "$ARCH" != "arm64" ]]; then
        print_error "64-bit OS required. Detected: $ARCH"
        echo "Please reinstall Raspberry Pi OS (64-bit) using Raspberry Pi Imager"
        exit 1
    fi
    print_success "64-bit OS detected ($ARCH)"
}

# Disable WLAN power save
disable_wlan_powersave() {
    print_step "Disabling WLAN power save for better stability..."

    # Check if already disabled
    if iwconfig wlan0 2>/dev/null | grep -q "Power Management:off"; then
        echo "WLAN power save already disabled"
        return
    fi

    # Create config to persist across reboots
    sudo tee /etc/NetworkManager/conf.d/wifi-powersave-off.conf > /dev/null << 'EOF'
[connection]
wifi.powersave = 2
EOF

    # Also try immediate disable
    sudo iwconfig wlan0 power off 2>/dev/null || true

    print_success "WLAN power save disabled"
}

# Apply WiFi stability fix
apply_wifi_fix() {
    print_step "Applying WiFi stability fix..."

    CMDLINE_FILE="/boot/firmware/cmdline.txt"
    if [[ ! -f "$CMDLINE_FILE" ]]; then
        CMDLINE_FILE="/boot/cmdline.txt"
    fi

    if [[ ! -f "$CMDLINE_FILE" ]]; then
        print_warning "Could not find cmdline.txt, skipping WiFi fix"
        return
    fi

    # Check if fix already applied
    if grep -q "brcmfmac.feature_disable=0x82000" "$CMDLINE_FILE"; then
        echo "WiFi fix already applied"
        return
    fi

    # Backup and apply fix
    sudo cp "$CMDLINE_FILE" "${CMDLINE_FILE}.backup"
    sudo sed -i 's/$/ brcmfmac.feature_disable=0x82000/' "$CMDLINE_FILE"

    print_success "WiFi fix applied. A reboot is recommended after setup."
    NEEDS_REBOOT=true
}

# Update system packages
update_system() {
    print_step "Updating system packages..."
    sudo apt update
    sudo DEBIAN_FRONTEND=noninteractive apt full-upgrade -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold"
    print_success "System updated"
}

# Verify we're in the dune-weaver directory
ensure_repo() {
    print_step "Setting up dune-weaver repository..."

    # Check if we're already in the dune-weaver directory
    if [[ -f "main.py" ]] && [[ -f "requirements.txt" ]]; then
        INSTALL_DIR="$(pwd)"
        print_success "Using existing repo at $INSTALL_DIR"
        return
    fi

    # Check if repo exists in home directory
    if [[ -d "$INSTALL_DIR" ]] && [[ -f "$INSTALL_DIR/main.py" ]]; then
        print_success "Found existing repo at $INSTALL_DIR"
        cd "$INSTALL_DIR"
        echo "Pulling latest changes..."
        git pull
        return
    fi

    # Clone the repository (as the real user, not root)
    print_step "Cloning dune-weaver repository..."
    if [[ -n "$SUDO_USER" ]]; then
        sudo -u "$REAL_USER" git clone "$REPO_URL" --single-branch "$INSTALL_DIR"
    else
        git clone "$REPO_URL" --single-branch "$INSTALL_DIR"
    fi
    cd "$INSTALL_DIR"
    print_success "Cloned to $INSTALL_DIR"
}

# Run a command as the real user (handles sudo case)
run_as_user() {
    if [[ -n "$SUDO_USER" ]]; then
        sudo -u "$REAL_USER" "$@"
    else
        "$@"
    fi
}

# Deploy native (venv + systemd + nginx)
deploy_native() {
    print_step "Setting up Python virtual environment..."

    cd "$INSTALL_DIR"

    # Create venv (as real user, not root)
    run_as_user python3 -m venv .venv

    # Install dependencies
    print_step "Installing Python packages..."
    run_as_user .venv/bin/pip install --upgrade pip
    run_as_user .venv/bin/pip install -r requirements.txt

    # Build frontend
    print_step "Building frontend..."
    cd "$INSTALL_DIR/frontend"
    run_as_user npm ci
    run_as_user npm run build
    cd "$INSTALL_DIR"

    # Configure nginx
    print_step "Configuring nginx..."
    sudo cp "$INSTALL_DIR/nginx/dune-weaver.conf" /etc/nginx/sites-available/dune-weaver.conf
    sudo sed -i "s|INSTALL_DIR_PLACEHOLDER|$INSTALL_DIR|g" /etc/nginx/sites-available/dune-weaver.conf
    sudo ln -sf /etc/nginx/sites-available/dune-weaver.conf /etc/nginx/sites-enabled/dune-weaver.conf
    sudo rm -f /etc/nginx/sites-enabled/default
    sudo nginx -t
    sudo systemctl restart nginx
    sudo systemctl enable nginx

    # Create systemd service
    print_step "Creating systemd service..."
    sudo cp "$INSTALL_DIR/dune-weaver.service" /etc/systemd/system/dune-weaver.service
    sudo sed -i "s|USER_PLACEHOLDER|$REAL_USER|g" /etc/systemd/system/dune-weaver.service
    sudo sed -i "s|INSTALL_DIR_PLACEHOLDER|$INSTALL_DIR|g" /etc/systemd/system/dune-weaver.service

    # Enable and start service
    sudo systemctl daemon-reload
    sudo systemctl enable dune-weaver
    sudo systemctl start dune-weaver

    # Create sudoers entry for passwordless systemctl commands
    print_step "Configuring sudo permissions..."
    sudo tee /etc/sudoers.d/dune-weaver > /dev/null << EOF
$REAL_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart dune-weaver
$REAL_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop dune-weaver
$REAL_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl start dune-weaver
$REAL_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl poweroff
$REAL_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart nginx
EOF
    sudo chmod 0440 /etc/sudoers.d/dune-weaver

    print_success "Native deployment complete!"
}

# Install dw CLI command
install_cli() {
    print_step "Installing 'dw' command..."

    # Copy dw script to /usr/local/bin
    sudo cp "$INSTALL_DIR/dw" /usr/local/bin/dw
    sudo chmod +x /usr/local/bin/dw

    print_success "'dw' command installed"
}

# Setup autohotspot
setup_autohotspot() {
    print_step "Setting up autohotspot..."

    if [[ ! -f "$INSTALL_DIR/wifi/setup-wifi.sh" ]]; then
        print_warning "wifi/setup-wifi.sh not found, skipping autohotspot setup"
        return
    fi

    bash "$INSTALL_DIR/wifi/setup-wifi.sh"
    print_success "Autohotspot setup complete"
}

# Get IP address
get_ip_address() {
    # Try multiple methods to get IP
    IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    if [[ -z "$IP" ]]; then
        IP=$(ip route get 1 2>/dev/null | awk '{print $7}' | head -1)
    fi
    if [[ -z "$IP" ]]; then
        IP="<your-pi-ip>"
    fi
    echo "$IP"
}

# Print final instructions
print_final_instructions() {
    IP=$(get_ip_address)
    HOSTNAME=$(hostname)

    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}   Dune Weaver Setup Complete!${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo -e "Access the web interface at:"
    echo -e "  ${BLUE}http://$IP${NC}"
    echo -e "  ${BLUE}http://$HOSTNAME.local${NC}"
    echo ""

    echo "Manage with the 'dw' command:"
    echo "  dw logs        View live logs"
    echo "  dw restart     Restart Dune Weaver"
    echo "  dw update      Pull latest and restart"
    echo "  dw stop        Stop Dune Weaver"
    echo "  dw status      Show status"
    echo "  dw wifi help   WiFi and hotspot management"
    echo "  dw help        Show all commands"
    echo ""

    if [[ "$SETUP_HOTSPOT" == "true" ]]; then
        echo -e "${BLUE}Autohotspot:${NC} If no known WiFi is found on boot,"
        echo "a 'Dune Weaver' hotspot will be created automatically."
        echo "Connect to it and open the app to configure WiFi."
        echo ""
    fi

    if [[ "$NEEDS_REBOOT" == "true" ]]; then
        print_warning "A reboot is recommended to apply WiFi fixes"
        read -p "Reboot now? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            sudo reboot
        fi
    fi
}

# Main installation flow
main() {
    echo -e "${GREEN}"
    echo "  ____                   __        __                        "
    echo " |  _ \ _   _ _ __   ___\ \      / /__  __ ___   _____ _ __ "
    echo " | | | | | | | '_ \ / _ \\ \ /\ / / _ \/ _\` \ \ / / _ \ '__|"
    echo " | |_| | |_| | | | |  __/ \ V  V /  __/ (_| |\ V /  __/ |   "
    echo " |____/ \__,_|_| |_|\___|  \_/\_/ \___|\__,_| \_/ \___|_|   "
    echo -e "${NC}"
    echo "Raspberry Pi Setup Script"
    echo ""
    echo "Install directory: $INSTALL_DIR"
    echo ""

    # Run setup steps
    check_raspberry_pi
    install_system_deps
    install_nodejs
    ensure_repo
    update_system
    disable_wlan_powersave

    if [[ "$FIX_WIFI" == "true" ]]; then
        apply_wifi_fix
    fi

    if [[ "$SETUP_HOTSPOT" == "true" ]]; then
        setup_autohotspot
    fi

    deploy_native
    install_cli
    print_final_instructions
}

# Run main
main
