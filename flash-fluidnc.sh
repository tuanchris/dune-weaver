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

# ─── Step 1: Choose version ────────────────────────────────────────────────

echo -e "${BOLD}${CYAN}"
echo "  ╔═══════════════════════════════════════╗"
echo "  ║     FluidNC Firmware Flasher          ║"
echo "  ║         for Dune Weaver               ║"
echo "  ╚═══════════════════════════════════════╝"
echo -e "${NC}"

echo -e "${BOLD}Select FluidNC version:${NC}"
echo ""
echo -e "  ${GREEN}1)${NC} v${VERSION_ALL}  -  All tables (Dune Weaver, Pro, Gold, Mini Pro)"
echo -e "  ${GREEN}2)${NC} v${VERSION_MINI}  -  Mini Dune Weaver only"
echo ""
read -p "Enter choice [1/2]: " version_choice

case "$version_choice" in
    1)
        VERSION="$VERSION_ALL"
        echo -e "\nSelected: ${GREEN}FluidNC v${VERSION}${NC}"
        ;;
    2)
        VERSION="$VERSION_MINI"
        echo -e "\nSelected: ${GREEN}FluidNC v${VERSION}${NC}"
        ;;
    *)
        echo -e "${RED}Invalid choice. Exiting.${NC}"
        exit 1
        ;;
esac

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
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

# ─── Step 5: Flash firmware ────────────────────────────────────────────────

echo ""
echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"
echo -e "${BOLD}  Flashing FluidNC v${VERSION} to ${PORT}${NC}"
echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Do NOT disconnect the board during flashing!${NC}"
echo ""

FLASH_SUCCESS=true

# --- 5a: Flash WiFi firmware ---
echo -e "${BLUE}[1/2] Flashing WiFi firmware...${NC}"
echo ""

WIFI_OUTPUT=$($ESPTOOL --chip esp32 --port "$PORT" --baud 460800 \
    --before default_reset --after hard_reset \
    write_flash -z --flash_mode dio --flash_freq 80m --flash_size detect \
    0x1000  "$FLASH_DIR/wifi/bootloader.bin" \
    0x8000  "$FLASH_DIR/wifi/partitions.bin" \
    0xe000  "$FLASH_DIR/common/boot_app0.bin" \
    0x10000 "$FLASH_DIR/wifi/firmware.bin" 2>&1) || true

echo "$WIFI_OUTPUT"
echo ""

if echo "$WIFI_OUTPUT" | grep -q "Hard resetting via RTS pin"; then
    echo -e "${GREEN}Firmware flash successful!${NC}"
else
    echo -e "${RED}Firmware flash may have failed!${NC}"
    FLASH_SUCCESS=false
fi

# --- 5b: Flash filesystem (LittleFS) ---
echo ""
echo -e "${BLUE}[2/2] Flashing filesystem (LittleFS)...${NC}"
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

# ─── Step 6: Summary ──────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"
if [[ "$FLASH_SUCCESS" == true ]]; then
    echo -e "${GREEN}  FluidNC v${VERSION} flashed successfully!${NC}"
    echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"
    echo ""
    echo "The board has been reset and should now be running FluidNC."
    echo "Connect to the 'FluidNC' WiFi network to access the web UI."
else
    echo -e "${RED}  Flashing completed with errors!${NC}"
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
