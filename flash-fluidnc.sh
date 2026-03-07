#!/bin/bash
#
# Flash FluidNC firmware onto a connected ESP32 board
#
# Usage: bash flash-fluidnc.sh
#
# Interactive script that:
#   1. Lets user choose FluidNC version (v3.9.5 for all tables, v3.8.3 for Mini Dune Weaver)
#   2. Lets user select a serial port
#   3. Downloads, extracts, and flashes the firmware
#   4. Confirms success by checking esptool output
#

set -e

# Warn if running as root/sudo — venv and pip won't work correctly
if [[ $EUID -eq 0 ]]; then
    echo -e "\033[1;33mWarning:\033[0m Running as root is not recommended."
    echo "If you need serial port access, add your user to the dialout group instead:"
    echo "  sudo usermod -a -G dialout \$USER"
    echo "Then log out and back in, and run: bash flash-fluidnc.sh"
    echo ""
    read -p "Continue anyway? [y/N]: " root_confirm
    if [[ ! "$root_confirm" =~ ^[Yy] ]]; then
        exit 1
    fi
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Script directory (for finding firmware configs)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Versions
VERSION_ALL="3.9.5"
VERSION_MINI="3.8.3"
GITHUB_BASE="https://github.com/bdring/FluidNC/releases/download"

cleanup() {
    if [[ -n "${WORK_DIR:-}" && -d "$WORK_DIR" ]]; then
        echo -e "\n${BLUE}Cleaning up temporary files...${NC}"
        rm -rf "$WORK_DIR"
    fi
}
trap cleanup EXIT

# ─── Step 1: Choose table type and version ────────────────────────────────

echo -e "${BOLD}${CYAN}"
echo "  ╔═══════════════════════════════════════╗"
echo "  ║     FluidNC Firmware Flasher          ║"
echo "  ║         for Dune Weaver               ║"
echo "  ╚═══════════════════════════════════════╝"
echo -e "${NC}"

echo -e "${BOLD}Select your table type:${NC}"
echo ""
echo -e "  ${GREEN}1)${NC} Dune Weaver Pro"
echo -e "  ${GREEN}2)${NC} Dune Weaver Mini Pro"
echo -e "  ${GREEN}3)${NC} Dune Weaver Gold"
echo -e "  ${GREEN}4)${NC} Dune Weaver"
echo -e "  ${GREEN}5)${NC} Dune Weaver Mini"
echo ""
read -p "Enter choice [1-5]: " table_choice

case "$table_choice" in
    1)
        TABLE_NAME="Dune Weaver Pro"
        CONFIG_DIR="dune_weaver_pro"
        VERSION="$VERSION_ALL"
        ;;
    2)
        TABLE_NAME="Dune Weaver Mini Pro"
        CONFIG_DIR="dune_weaver_mini_pro"
        VERSION="$VERSION_ALL"
        ;;
    3)
        TABLE_NAME="Dune Weaver Gold"
        CONFIG_DIR="dune_weaver_gold"
        VERSION="$VERSION_ALL"
        ;;
    4)
        TABLE_NAME="Dune Weaver"
        CONFIG_DIR="dune_weaver"
        VERSION="$VERSION_ALL"
        ;;
    5)
        TABLE_NAME="Dune Weaver Mini"
        CONFIG_DIR="dune_weaver_mini"
        VERSION="$VERSION_MINI"
        ;;
    *)
        echo -e "${RED}Invalid choice. Exiting.${NC}"
        exit 1
        ;;
esac

echo -e "\nSelected: ${GREEN}${TABLE_NAME}${NC} (FluidNC v${VERSION})"

# Locate the config file for the selected table
CONFIG_FILE="$SCRIPT_DIR/firmware/${CONFIG_DIR}/config.yaml"
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo -e "${RED}Config file not found: ${CONFIG_FILE}${NC}"
    exit 1
fi
echo -e "Config: ${GREEN}${CONFIG_FILE}${NC}"

# ─── Step 2: Detect and select serial port ─────────────────────────────────

echo ""
echo -e "${BOLD}Detecting serial ports...${NC}"

# Collect available serial ports (Linux + macOS patterns)
PORTS=()
for port in /dev/ttyUSB* /dev/ttyACM* /dev/cu.usbserial* /dev/cu.wchusbserial* /dev/cu.SLAB_USBtoUART*; do
    if [[ -e "$port" ]]; then
        PORTS+=("$port")
    fi
done

if [[ ${#PORTS[@]} -eq 0 ]]; then
    echo -e "${RED}No serial ports found!${NC}"
    echo ""
    echo "Make sure your ESP32 board is connected via USB."
    echo "On Linux, you may need to add your user to the 'dialout' group:"
    echo "  sudo usermod -a -G dialout \$USER"
    exit 1
fi

if [[ ${#PORTS[@]} -eq 1 ]]; then
    PORT="${PORTS[0]}"
    echo -e "Found port: ${GREEN}${PORT}${NC}"
    read -p "Use this port? [Y/n]: " confirm
    if [[ "$confirm" =~ ^[Nn] ]]; then
        echo -e "${RED}Exiting.${NC}"
        exit 1
    fi
else
    echo -e "Found ${GREEN}${#PORTS[@]}${NC} serial ports:"
    echo ""
    for i in "${!PORTS[@]}"; do
        echo -e "  ${GREEN}$((i + 1)))${NC} ${PORTS[$i]}"
    done
    echo ""
    read -p "Select port [1-${#PORTS[@]}]: " port_choice

    if [[ "$port_choice" -ge 1 && "$port_choice" -le ${#PORTS[@]} ]] 2>/dev/null; then
        PORT="${PORTS[$((port_choice - 1))]}"
    else
        echo -e "${RED}Invalid choice. Exiting.${NC}"
        exit 1
    fi
fi

echo -e "Using port: ${GREEN}${PORT}${NC}"

# ─── Step 3: Check for esptool ─────────────────────────────────────────────

# Find a working pip/venv to install esptool (avoids PEP 668 externally-managed errors)
VENV_DIR=""
if [[ -f "$SCRIPT_DIR/.venv/bin/activate" ]]; then
    VENV_DIR="$SCRIPT_DIR/.venv"
elif [[ -f "$HOME/dune-weaver/.venv/bin/activate" ]]; then
    VENV_DIR="$HOME/dune-weaver/.venv"
fi

if [[ -n "$VENV_DIR" ]]; then
    source "$VENV_DIR/bin/activate"
fi

if ! command -v esptool.py &> /dev/null && ! command -v esptool &> /dev/null; then
    echo ""
    echo -e "${YELLOW}esptool not found. Installing...${NC}"

    # Try the venv pip directly first, then fall back to creating a temp venv
    if [[ -n "$VENV_DIR" && -x "$VENV_DIR/bin/pip" ]]; then
        "$VENV_DIR/bin/pip" install esptool
    elif python3 -m venv /tmp/esptool-venv 2>/dev/null; then
        echo -e "${YELLOW}Creating temporary venv for esptool...${NC}"
        source /tmp/esptool-venv/bin/activate
        pip install esptool
    else
        # Last resort: override PEP 668 restriction
        pip install --break-system-packages esptool 2>/dev/null || pip install esptool
    fi
fi

# Determine the esptool command name
if command -v esptool.py &> /dev/null; then
    ESPTOOL="esptool.py"
elif command -v esptool &> /dev/null; then
    ESPTOOL="esptool"
else
    echo -e "${RED}Failed to install esptool. Please install manually: pip install esptool${NC}"
    exit 1
fi

# ─── Step 4: Download and extract ──────────────────────────────────────────

ZIP_NAME="fluidnc-v${VERSION}-posix.zip"
DOWNLOAD_URL="${GITHUB_BASE}/v${VERSION}/${ZIP_NAME}"
EXTRACT_DIR="fluidnc-v${VERSION}-posix"

WORK_DIR=$(mktemp -d)
echo ""
echo -e "${BLUE}Downloading FluidNC v${VERSION}...${NC}"
if ! curl -L --fail --progress-bar "$DOWNLOAD_URL" -o "$WORK_DIR/$ZIP_NAME"; then
    echo -e "${RED}Download failed!${NC}"
    echo "URL: $DOWNLOAD_URL"
    exit 1
fi

echo -e "${BLUE}Extracting...${NC}"
unzip -q "$WORK_DIR/$ZIP_NAME" -d "$WORK_DIR"

if [[ ! -d "$WORK_DIR/$EXTRACT_DIR" ]]; then
    echo -e "${RED}Expected directory $EXTRACT_DIR not found after extraction.${NC}"
    exit 1
fi

FLASH_DIR="$WORK_DIR/$EXTRACT_DIR"

# ─── Step 5: Flash filesystem ─────────────────────────────────────────────

echo ""
echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"
echo -e "${BOLD}  Flashing FluidNC v${VERSION} to ${PORT}${NC}"
echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Do NOT disconnect the board during flashing!${NC}"
echo ""

FLASH_SUCCESS=true

# Flash filesystem (LittleFS) only — firmware is already on the board
echo -e "${BLUE}[1/2] Flashing filesystem (LittleFS)...${NC}"
echo ""

FS_OUTPUT=$($ESPTOOL --chip esp32 --port "$PORT" --baud 460800 \
    --before default_reset --after hard_reset \
    write_flash -z --flash_mode dio --flash_freq 80m --flash_size detect \
    0x3d0000 "$FLASH_DIR/wifi/littlefs.bin" 2>&1) || true

echo "$FS_OUTPUT"
echo ""

if echo "$FS_OUTPUT" | grep -q "Hard resetting via RTS pin"; then
    echo -e "${GREEN}Filesystem flash successful!${NC}"
else
    echo -e "${RED}Filesystem flash may have failed!${NC}"
    FLASH_SUCCESS=false
fi

# ─── Step 6: Upload config via xmodem ────────────────────────────────────

if [[ "$FLASH_SUCCESS" == true ]]; then
    echo ""
    echo -e "${BLUE}[2/2] Uploading ${TABLE_NAME} config...${NC}"
    echo ""

    # Ensure xmodem and pyserial are available
    if [[ -n "$VENV_DIR" && -x "$VENV_DIR/bin/pip" ]]; then
        "$VENV_DIR/bin/pip" install -q xmodem pyserial 2>/dev/null
    elif [[ -d "/tmp/esptool-venv" ]]; then
        /tmp/esptool-venv/bin/pip install -q xmodem pyserial 2>/dev/null
    else
        pip install -q xmodem pyserial 2>/dev/null || true
    fi

    # Wait for the board to boot after flash reset
    echo -e "${YELLOW}Waiting for board to boot...${NC}"
    sleep 4

    # Upload config.yaml via xmodem using a Python helper
    PYTHON_CMD="python3"
    if [[ -n "$VENV_DIR" && -x "$VENV_DIR/bin/python3" ]]; then
        PYTHON_CMD="$VENV_DIR/bin/python3"
    elif [[ -x "/tmp/esptool-venv/bin/python3" ]]; then
        PYTHON_CMD="/tmp/esptool-venv/bin/python3"
    fi

    UPLOAD_OUTPUT=$($PYTHON_CMD - "$PORT" "$CONFIG_FILE" <<'PYEOF'
import sys
import time
import serial
from xmodem import XMODEM

port = sys.argv[1]
config_path = sys.argv[2]
dest_name = "config.yaml"

try:
    ser = serial.Serial(port, 115200, timeout=2)
    time.sleep(1)

    # Drain any boot messages
    while ser.in_waiting:
        ser.read(ser.in_waiting)
        time.sleep(0.1)

    # Send xmodem receive command
    cmd = f"$Xmodem/Receive={dest_name}\n"
    ser.write(cmd.encode())
    time.sleep(1)

    # Drain response to get into xmodem receive mode
    while ser.in_waiting:
        ser.read(ser.in_waiting)
        time.sleep(0.1)

    def getc(size, timeout=1):
        ser.timeout = timeout
        data = ser.read(size)
        return data or None

    def putc(data, timeout=1):
        return ser.write(data) or None

    modem = XMODEM(getc, putc, mode='xmodem')
    with open(config_path, 'rb') as f:
        success = modem.send(f)

    if success:
        print("CONFIG_UPLOAD_OK")
    else:
        print("CONFIG_UPLOAD_FAIL")

    # Drain any xmodem response data before sending commands
    time.sleep(2)
    while ser.in_waiting:
        ser.read(ser.in_waiting)
        time.sleep(0.1)

    # Set this config as the active one
    ser.write(b"$Config/Filename=config.yaml\n")
    ser.flush()
    time.sleep(1)
    # Drain response
    while ser.in_waiting:
        ser.read(ser.in_waiting)
        time.sleep(0.1)

    # Restart to apply the new config
    ser.write(b"$System/Control=RESTART\n")
    ser.flush()
    time.sleep(2)
    ser.close()

except Exception as e:
    print(f"CONFIG_UPLOAD_ERROR: {e}")
PYEOF
    ) 2>&1 || true

    echo "$UPLOAD_OUTPUT"
    echo ""

    if echo "$UPLOAD_OUTPUT" | grep -q "CONFIG_UPLOAD_OK"; then
        echo -e "${GREEN}Config uploaded successfully!${NC}"
    else
        echo -e "${RED}Config upload failed!${NC}"
        echo ""
        echo "You can upload the config manually:"
        echo "  1. Connect to the 'FluidNC' WiFi network"
        echo "  2. Open http://192.168.0.1 in a browser"
        echo "  3. Upload: firmware/${CONFIG_DIR}/config.yaml"
        FLASH_SUCCESS=false
    fi
fi

# ─── Step 7: Summary ──────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"
if [[ "$FLASH_SUCCESS" == true ]]; then
    echo -e "${GREEN}  ${TABLE_NAME} setup complete!${NC}"
    echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"
    echo ""
    echo "FluidNC v${VERSION} filesystem + ${TABLE_NAME} config flashed."
    echo "The board is restarting with the new configuration."
else
    echo -e "${RED}  Setup completed with errors!${NC}"
    echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"
    echo ""
    echo "Review the output above for error details."
    echo "Common fixes:"
    echo "  - Hold the BOOT button on the ESP32 while flashing"
    echo "  - Try a different USB cable (data cable, not charge-only)"
    echo "  - Check port permissions: sudo chmod 666 $PORT"
    echo "  - Try a lower baud rate by editing this script (change 460800 to 115200)"
    exit 1
fi
