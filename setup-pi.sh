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

# Default options
FIX_WIFI=true  # Applied by default for stability
SETUP_HOTSPOT=true  # Autohotspot for first-time WiFi setup
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME="$(eval echo ~"$REAL_USER")"
# Fallback: if tilde didn't expand, read from /etc/passwd
if [[ "$REAL_HOME" == "~$REAL_USER" ]]; then
    REAL_HOME="$(grep "^$REAL_USER:" /etc/passwd | cut -d: -f6)"
fi
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
        gcc g++ make swig unzip wget \
        libjpeg-dev zlib1g-dev \
        libgpiod-dev gpiod \
        nginx git vim
    print_success "System dependencies installed"
}

# Ensure lgpio C library is available for pip to build against
install_lgpio() {
    local syslib="/usr/lib/aarch64-linux-gnu"

    # Raspberry Pi OS Trixie ships liblgpio.so.1 but no unversioned
    # liblgpio.so symlink (normally provided by a -dev package).
    # The build-time linker needs the unversioned name (-llgpio → liblgpio.so).
    if [[ ! -e "$syslib/liblgpio.so" ]]; then
        # Check if the versioned library exists (from Pi OS)
        local versioned
        versioned=$(ls "$syslib"/liblgpio.so.* 2>/dev/null | head -1)

        if [[ -n "$versioned" ]]; then
            print_step "Creating liblgpio.so build symlink..."
            sudo ln -sf "$versioned" "$syslib/liblgpio.so"
            sudo ldconfig
            print_success "liblgpio.so symlink created (-> $(basename "$versioned"))"
        else
            # Not in system paths — build from source
            print_step "Building lgpio C library from source..."
            local tmpdir
            tmpdir=$(mktemp -d)
            cd "$tmpdir"
            wget -q https://github.com/joan2937/lg/archive/master.zip
            unzip -q master.zip
            cd lg-master
            make
            sudo make install
            cd /
            rm -rf "$tmpdir"
            # Symlink from /usr/local/lib into system path
            if [[ -f /usr/local/lib/liblgpio.so ]]; then
                sudo ln -sf /usr/local/lib/liblgpio.so "$syslib/liblgpio.so"
            fi
            sudo ldconfig
            print_success "lgpio C library built and installed"
        fi
    else
        echo "liblgpio.so already available for linking"
    fi
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
        # Fix ownership after pull (new files may be created as root)
        if [[ $EUID -eq 0 && -n "$SUDO_USER" ]]; then
            chown -R "$SUDO_USER:$SUDO_USER" "$INSTALL_DIR"
        fi
        return
    fi

    # Clone the repository
    print_step "Cloning dune-weaver repository..."
    git clone "$REPO_URL" --single-branch "$INSTALL_DIR"
    # When running as sudo, git clone creates files as root.
    # Fix ownership so the real user can write to the repo (e.g. create .venv).
    if [[ $EUID -eq 0 && -n "$SUDO_USER" ]]; then
        chown -R "$SUDO_USER:$SUDO_USER" "$INSTALL_DIR"
    fi
    cd "$INSTALL_DIR"
    print_success "Cloned to $INSTALL_DIR"
}

# Deploy native (venv + systemd + nginx)
deploy_native() {
    print_step "Setting up Python virtual environment..."

    cd "$INSTALL_DIR"

    # Ensure repo is owned by real user before creating venv
    if [[ $EUID -eq 0 && -n "$SUDO_USER" ]]; then
        chown -R "$SUDO_USER:$SUDO_USER" "$INSTALL_DIR"
    fi

    # Create venv — if running as root (sudo), create as the real user
    local real_user="${SUDO_USER:-$USER}"
    if [[ $EUID -eq 0 && -n "$SUDO_USER" ]]; then
        sudo -u "$SUDO_USER" python3 -m venv .venv
    else
        python3 -m venv .venv
    fi
    source .venv/bin/activate

    # Install dependencies
    print_step "Installing Python packages..."
    pip install --upgrade pip
    pip install -r requirements.txt

    # Ensure venv is owned by the real user (not root)
    if [[ $EUID -eq 0 && -n "$SUDO_USER" ]]; then
        chown -R "$SUDO_USER:$SUDO_USER" .venv
    fi

    # Ensure nginx (www-data) can traverse to static files
    # chmod o+x grants traversal only, not directory listing
    local dir="$INSTALL_DIR"
    while [[ "$dir" != "/" ]]; do
        sudo chmod o+x "$dir"
        dir=$(dirname "$dir")
    done

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
    sudo sed -i "s|USER_PLACEHOLDER|$USER|g" /etc/systemd/system/dune-weaver.service
    sudo sed -i "s|INSTALL_DIR_PLACEHOLDER|$INSTALL_DIR|g" /etc/systemd/system/dune-weaver.service

    # Enable and start service
    sudo systemctl daemon-reload
    sudo systemctl enable dune-weaver
    sudo systemctl start dune-weaver

    # Create sudoers entry for passwordless systemctl commands
    print_step "Configuring sudo permissions..."
    sudo tee /etc/sudoers.d/dune-weaver > /dev/null << EOF
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart dune-weaver
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop dune-weaver
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl start dune-weaver
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl poweroff
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart nginx
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

# Configure UART for GPIO pin connection to DLC32/ESP32
configure_uart() {
    local CONFIG_FILE="/boot/firmware/config.txt"
    if [[ ! -f "$CONFIG_FILE" ]]; then
        CONFIG_FILE="/boot/config.txt"
    fi

    echo ""
    echo -e "${GREEN}How is your Raspberry Pi connected to the sand table controller (DLC32/ESP32)?${NC}"
    echo ""
    echo "  1) USB cable"
    echo "  2) UART over GPIO pins (TX/RX wired to header pins)"
    echo ""
    echo -e "  ${YELLOW}Note: USB is not reliable on Pi 3B+. Use UART for Pi 3B+.${NC}"
    echo ""
    read -p "Enter choice [1/2] (default: 1): " -n 1 -r uart_choice
    echo ""

    if [[ "$uart_choice" == "2" ]]; then
        echo ""
        echo -e "${YELLOW}============================================${NC}"
        echo -e "${YELLOW}  UART Setup — raspi-config will run next${NC}"
        echo -e "${YELLOW}============================================${NC}"
        echo ""
        echo -e "  When prompted, select:"
        echo -e "    Login shell over serial?     →  ${GREEN}No${NC}"
        echo -e "    Serial port hardware?        →  ${GREEN}Yes${NC}"
        echo ""
        read -p "Press Enter to continue..." -r
        echo ""

        # Disable serial console, enable serial hardware
        if command -v raspi-config &> /dev/null; then
            sudo raspi-config nonint do_serial 2
            echo "Serial console disabled, serial hardware enabled"
        else
            print_warning "raspi-config not found, please run 'sudo raspi-config' manually"
            print_warning "Go to: 3 Interface Options > I6 Serial Port > No (console) > Yes (hardware)"
        fi

        print_step "Configuring UART overlays..."

        # Add UART overlays to config.txt if not already present
        local needs_change=false
        for overlay in "dtoverlay=pi3-miniuart-bt" "dtoverlay=miniuart-bt" "enable_uart=1"; do
            if ! grep -q "^${overlay}$" "$CONFIG_FILE" 2>/dev/null; then
                echo "$overlay" | sudo tee -a "$CONFIG_FILE" > /dev/null
                needs_change=true
            fi
        done

        if [[ "$needs_change" == "true" ]]; then
            echo "Added UART overlays to $CONFIG_FILE"
        else
            echo "UART overlays already present in $CONFIG_FILE"
        fi

        NEEDS_REBOOT=true
        print_success "UART configured. A reboot is required for changes to take effect."
    else
        # USB mode — check if UART config exists and offer to clean it up
        local has_uart=false
        for overlay in "dtoverlay=pi3-miniuart-bt" "dtoverlay=miniuart-bt" "enable_uart=1"; do
            if grep -q "^${overlay}$" "$CONFIG_FILE" 2>/dev/null; then
                has_uart=true
                break
            fi
        done

        if [[ "$has_uart" == "true" ]]; then
            echo -e "${YELLOW}UART overlays found in $CONFIG_FILE from a previous setup.${NC}"
            read -p "Remove them? (y/N): " -n 1 -r remove_uart
            echo ""
            if [[ "$remove_uart" =~ ^[Yy]$ ]]; then
                sudo sed -i '/^dtoverlay=pi3-miniuart-bt$/d' "$CONFIG_FILE"
                sudo sed -i '/^dtoverlay=miniuart-bt$/d' "$CONFIG_FILE"
                sudo sed -i '/^enable_uart=1$/d' "$CONFIG_FILE"
                NEEDS_REBOOT=true
                print_success "UART overlays removed. A reboot is recommended."
            fi
        else
            echo "USB connection selected, no UART changes needed."
        fi
    fi
}

# Remove software that is no longer needed on the Pi
cleanup_unused() {
    print_step "Cleaning up unused software..."

    # Remove Node.js / npm if present from a prior install
    if dpkg -l nodejs 2>/dev/null | grep -q '^ii'; then
        echo "Removing Node.js (no longer needed — frontend is pre-built)..."
        sudo apt purge -y nodejs || true
        sudo rm -f /etc/apt/sources.list.d/nodesource.list \
                    /etc/apt/keyrings/nodesource.gpg 2>/dev/null || true
        sudo apt autoremove -y
        print_success "Node.js removed"
    fi

    # Remove Docker if present from old Docker-based deployment
    if dpkg -l docker-ce 2>/dev/null | grep -q '^ii'; then
        echo "Removing Docker (old deployment method)..."
        # Stop running containers
        sudo docker stop $(sudo docker ps -aq) 2>/dev/null || true
        sudo apt purge -y docker-ce docker-ce-cli containerd.io docker-compose-plugin 2>/dev/null || true
        sudo rm -rf /var/lib/docker
        sudo apt autoremove -y
        print_success "Docker removed"
    fi
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
        print_warning "A reboot is required to apply configuration changes"
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

    # Ask connection type upfront (before long-running installs)
    configure_uart

    # Run setup steps
    check_raspberry_pi
    install_system_deps
    ensure_repo
    disable_wlan_powersave

    if [[ "$FIX_WIFI" == "true" ]]; then
        apply_wifi_fix
    fi

    if [[ "$SETUP_HOTSPOT" == "true" ]]; then
        setup_autohotspot
    fi

    install_lgpio
    deploy_native
    install_cli
    cleanup_unused
    print_final_instructions
}

# Run main
main
