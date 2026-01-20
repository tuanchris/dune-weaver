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
#   --no-docker     Use Python venv instead of Docker
#   --no-wifi-fix   Skip WiFi stability fix
#   --help          Show help
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default options
USE_DOCKER=true
FIX_WIFI=true  # Applied by default for stability
INSTALL_DIR="$HOME/dune-weaver"
REPO_URL="https://github.com/tuanchris/dune-weaver"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-docker)
            USE_DOCKER=false
            shift
            ;;
        --no-wifi-fix)
            FIX_WIFI=false
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
            echo "  --no-docker     Use Python venv instead of Docker"
            echo "  --no-wifi-fix   Skip WiFi stability fix (applied by default)"
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

# Install essential packages (git, vim)
install_essentials() {
    print_step "Installing essential packages..."
    sudo apt update
    sudo apt install -y git vim
    print_success "Essential packages installed"
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
    sudo apt full-upgrade -y
    print_success "System updated"
}

# Install Docker
install_docker() {
    print_step "Installing Docker..."

    if command -v docker &> /dev/null; then
        echo "Docker already installed: $(docker --version)"
    else
        curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
        sudo sh /tmp/get-docker.sh
        rm /tmp/get-docker.sh
        print_success "Docker installed"
    fi

    # Add user to docker group
    if ! groups $USER | grep -q docker; then
        print_step "Adding $USER to docker group..."
        sudo usermod -aG docker $USER
        DOCKER_GROUP_ADDED=true
        print_warning "You'll need to log out and back in for docker group changes to take effect"
    fi
}

# Install Python dependencies (non-Docker)
install_python_deps() {
    print_step "Installing Python dependencies..."

    # Install system packages
    sudo apt install -y python3-venv python3-pip git

    print_success "Python dependencies installed"
}

# Verify we're in the dune-weaver directory
ensure_repo() {
    print_step "Setting up dune-weaver repository..."

    # Check if we're already in the dune-weaver directory
    if [[ -f "docker-compose.yml" ]] && [[ -f "main.py" ]]; then
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

    # Clone the repository
    print_step "Cloning dune-weaver repository..."
    git clone "$REPO_URL" --single-branch "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    print_success "Cloned to $INSTALL_DIR"
}

# Install dw CLI command
install_cli() {
    print_step "Installing 'dw' command..."

    # Copy dw script to /usr/local/bin
    sudo cp "$INSTALL_DIR/dw" /usr/local/bin/dw
    sudo chmod +x /usr/local/bin/dw

    print_success "'dw' command installed"
}

# Install update watcher service (for Docker deployments)
install_update_watcher() {
    if [[ "$USE_DOCKER" != "true" ]]; then
        # Update watcher only needed for Docker deployments
        return
    fi

    print_step "Installing update watcher service..."

    # Make watcher script executable
    chmod +x "$INSTALL_DIR/scripts/update-watcher.sh"

    # Create systemd service with correct paths
    sudo tee /etc/systemd/system/dune-weaver-update.service > /dev/null << EOF
[Unit]
Description=Dune Weaver Update Watcher
After=multi-user.target docker.service
Wants=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/scripts/update-watcher.sh
Restart=always
RestartSec=10
StartLimitInterval=200
StartLimitBurst=5

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable dune-weaver-update
    sudo systemctl start dune-weaver-update

    print_success "Update watcher service installed"
}

# Deploy with Docker
deploy_docker() {
    print_step "Deploying Dune Weaver with Docker Compose..."

    cd "$INSTALL_DIR"
    sudo docker compose up -d --quiet-pull

    print_success "Docker deployment complete!"
}

# Deploy with Python venv
deploy_python() {
    print_step "Setting up Python virtual environment..."

    cd "$INSTALL_DIR"

    # Create venv
    python3 -m venv .venv
    source .venv/bin/activate

    # Install dependencies
    print_step "Installing Python packages..."
    pip install --upgrade pip
    pip install -r requirements.txt

    # Create systemd service
    print_step "Creating systemd service..."

    sudo tee /etc/systemd/system/dune-weaver.service > /dev/null << EOF
[Unit]
Description=Dune Weaver Backend
After=network.target

[Service]
ExecStart=$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/main.py
WorkingDirectory=$INSTALL_DIR
Restart=always
User=$USER
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

    # Enable and start service
    sudo systemctl daemon-reload
    sudo systemctl enable dune-weaver
    sudo systemctl start dune-weaver

    print_success "Python deployment complete!"
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
    echo -e "  ${BLUE}http://$IP:8080${NC}"
    echo -e "  ${BLUE}http://$HOSTNAME.local:8080${NC}"
    echo ""

    echo "Manage with the 'dw' command:"
    echo "  dw logs        View live logs"
    echo "  dw restart     Restart Dune Weaver"
    echo "  dw update      Pull latest and restart"
    echo "  dw stop        Stop Dune Weaver"
    echo "  dw status      Show status"
    echo "  dw help        Show all commands"
    echo ""

    if [[ "$DOCKER_GROUP_ADDED" == "true" ]]; then
        print_warning "Please log out and back in for docker group changes to take effect"
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

    # Detect deployment method
    if [[ "$USE_DOCKER" == "true" ]]; then
        echo "Deployment method: Docker (recommended)"
    else
        echo "Deployment method: Python virtual environment"
    fi
    echo "Install directory: $INSTALL_DIR"
    echo ""

    # Run setup steps
    check_raspberry_pi
    install_essentials
    ensure_repo
    update_system
    disable_wlan_powersave

    if [[ "$FIX_WIFI" == "true" ]]; then
        apply_wifi_fix
    fi

    if [[ "$USE_DOCKER" == "true" ]]; then
        install_docker
        deploy_docker
    else
        install_python_deps
        deploy_python
    fi

    install_cli
    install_update_watcher
    print_final_instructions
}

# Run main
main
