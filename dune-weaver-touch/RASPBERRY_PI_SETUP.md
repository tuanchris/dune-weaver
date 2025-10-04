# Raspberry Pi MIPI DSI Touchscreen Setup for Dune Weaver Touch

## Prerequisites
Make sure your Raspberry Pi is running a recent version of Raspberry Pi OS (Bullseye or newer).

**MIPI DSI Display Notes**: This guide is specifically configured for the **Freenove 5" MIPI DSI Touchscreen (800x480)** which uses driver-free configuration on modern Raspberry Pi OS.

## Install System Dependencies

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Qt6 system packages (includes eglfs platform plugin)
sudo apt install -y qt6-base-dev qt6-qml-dev qt6-quick-dev

# Install graphics and display dependencies
sudo apt install -y \
    libgl1-mesa-dev \
    libgles2-mesa-dev \
    libegl1-mesa-dev \
    libdrm2 \
    libxkbcommon0 \
    libinput10 \
    libudev1

# Install Python and pip
sudo apt install -y python3-dev python3-pip

# Install PySide6 from system packages (recommended for embedded)
sudo apt install -y python3-pyside6.qtcore python3-pyside6.qtgui python3-pyside6.qtqml python3-pyside6.qtquick python3-pyside6.qtwebsockets

# Alternative: Install PySide6 via pip (if system packages don't work)
# pip3 install PySide6
```

## Configure Freenove 5" MIPI DSI Display

### Step 1: Physical Connection
1. Connect the display ribbon cable to the MIPI DSI port (next to camera connector)
2. Connect the USB cable for touch (to any USB port)
3. Power on the Raspberry Pi

### Step 2: Configure Boot Settings

The Freenove display is driver-free on newer Pi OS, but needs proper configuration:

```bash
sudo nano /boot/config.txt

# Add these lines for Freenove 5" MIPI DSI display
dtoverlay=vc4-kms-v3d
max_framebuffers=2

# GPU memory for graphics acceleration  
gpu_mem=128

# Enable DSI display (driver-free detection)
display_auto_detect=1

# Force 800x480 resolution if auto-detect fails
# hdmi_group=2
# hdmi_mode=87
# hdmi_cvt=800 480 60 6 0 0 0

# Disable overscan for exact pixel mapping
disable_overscan=1

# Optional: Disable rainbow splash screen
disable_splash=1

# Optional: Rotate display if mounted upside down
# display_rotate=2
```

### Step 3: Configure Touch Input

The Freenove display uses USB for 5-point capacitive touch (driver-free):

```bash
# Verify touch is detected via USB
lsusb | grep -i touch
ls /dev/input/event*

# Check touch events
sudo evtest
# Select the touch device (usually event0 or event1)

# Touch should work automatically - no additional drivers needed
```

### Step 4: Reboot and Verify Display
```bash
sudo reboot

# After reboot, verify display is working
# Check framebuffer resolution
fbset -fb /dev/fb0

# Verify display resolution
xrandr
# Should show 800x480 resolution

# Test display with simple graphics
sudo apt install -y fbi
sudo fbi -T 1 /usr/share/pixmaps/debian-logo.png
```

## Configure Display for Application

### Option 1: Direct Framebuffer (Kiosk Mode - Recommended)
For a dedicated touchscreen kiosk:

```bash
# Add to ~/.bashrc or create a startup script
export QT_QPA_PLATFORM=eglfs
export QT_QPA_EGLFS_WIDTH=800
export QT_QPA_EGLFS_HEIGHT=480
export QT_QPA_EGLFS_PHYSICAL_WIDTH=154
export QT_QPA_EGLFS_PHYSICAL_HEIGHT=86
export QT_QPA_GENERIC_PLUGINS=evdevtouch
```

### Option 2: X11 with Touchscreen Support
If you need window management:

```bash
# Install X11 and touchscreen support
sudo apt install -y xinput-calibrator xserver-xorg-input-evdev

# Configure X11 for touchscreen
export DISPLAY=:0
export QT_QPA_PLATFORM=xcb
```

### Option 3: Wayland (Modern Alternative)
For newer systems:

```bash
sudo apt install -y qt6-wayland
export QT_QPA_PLATFORM=wayland
export WAYLAND_DISPLAY=wayland-1
```

## Running the Application

### Method 1: Direct Framebuffer (Fullscreen Kiosk)
```bash
cd /path/to/dune-weaver-touch
QT_QPA_PLATFORM=eglfs QT_QPA_EGLFS_WIDTH=800 QT_QPA_EGLFS_HEIGHT=480 python3 main.py
```

### Method 2: X11 Window
```bash
cd /path/to/dune-weaver-touch
DISPLAY=:0 QT_QPA_PLATFORM=xcb python3 main.py
```

### Method 3: Auto-detect Platform
```bash
cd /path/to/dune-weaver-touch
python3 main.py
```

## Touchscreen Calibration

If touch input doesn't align with display:

```bash
# Install calibration tool
sudo apt install -y xinput-calibrator

# Run calibration (follow on-screen instructions)
sudo xinput_calibrator

# Save the output to X11 configuration
sudo tee /etc/X11/xorg.conf.d/99-calibration.conf << EOF
Section "InputClass"
    Identifier "calibration"
    MatchProduct "your_touchscreen_name"
    Option "Calibration" "min_x max_x min_y max_y"
    Option "SwapAxes" "0"
EndSection
EOF
```

## Auto-start on Boot (Kiosk Mode)

### Automated Setup Script

We provide a comprehensive setup script that automatically configures your Raspberry Pi for kiosk mode:

```bash
# Navigate to the application directory
cd /home/pi/dune-weaver/dune-weaver-touch

# Make the setup script executable
chmod +x setup_kiosk.sh

# Run the setup script
./setup_kiosk.sh

# The script will:
# - Detect your Pi model (3/4/5)
# - Configure boot settings for DSI display
# - Install required dependencies
# - Create systemd service for auto-start
# - Set up proper Qt platform (EGLFS/LinuxFB)
# - Create uninstall script for easy removal
```

### Script Commands

```bash
# Install kiosk mode (default)
./setup_kiosk.sh

# Check service status
./setup_kiosk.sh status

# Test display configuration
./setup_kiosk.sh test

# Uninstall kiosk mode
./setup_kiosk.sh uninstall
# Or use the generated script:
./uninstall_kiosk.sh
```

### Manual Service Control

After installation, you can control the kiosk service:

```bash
# Start the service
sudo systemctl start dune-weaver-kiosk

# Stop the service
sudo systemctl stop dune-weaver-kiosk

# Check service status
sudo systemctl status dune-weaver-kiosk

# View live logs
journalctl -u dune-weaver-kiosk -f

# Disable auto-start
sudo systemctl disable dune-weaver-kiosk

# Re-enable auto-start
sudo systemctl enable dune-weaver-kiosk
```

### Manual Setup (Alternative)

If you prefer manual setup, create a systemd service:

```bash
sudo tee /etc/systemd/system/dune-weaver-touch.service << EOF
[Unit]
Description=Dune Weaver Touch Interface
After=multi-user.target graphical.target
Wants=network-online.target

[Service]
Type=simple
User=pi
Environment=QT_QPA_PLATFORM=eglfs
Environment=QT_QPA_EGLFS_WIDTH=800
Environment=QT_QPA_EGLFS_HEIGHT=480
Environment=QT_QPA_EGLFS_INTEGRATION=eglfs_kms
Environment=QT_QPA_EGLFS_HIDECURSOR=1
WorkingDirectory=/home/pi/dune-weaver/dune-weaver-touch
ExecStart=/home/pi/dune-weaver/dune-weaver-touch/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable the service
sudo systemctl enable dune-weaver-touch.service
sudo systemctl start dune-weaver-touch.service
```

## Troubleshooting

### "Could not find Qt platform plugin"
```bash
# Check available plugins
python3 -c "from PySide6.QtGui import QGuiApplication; import sys; app=QGuiApplication(sys.argv); print(app.platformName())"

# If eglfs missing, install system Qt packages
sudo apt install -y qt6-qpa-plugins
```

### "Cannot open display"
```bash
# Make sure X11 is running or use eglfs
export DISPLAY=:0
xhost +local:
```

### Touch not working
```bash
# Check input devices
ls /dev/input/
cat /proc/bus/input/devices

# Test touch events
sudo apt install -y evtest
sudo evtest
```

### Screen rotation
Add to boot config (`/boot/config.txt`):
```
# Rotate display 180 degrees
display_rotate=2

# Or rotate 90 degrees
display_rotate=1
```

## Performance Tips

1. **GPU Memory Split**: Increase GPU memory in `/boot/config.txt`:
   ```
   gpu_mem=128
   ```

2. **Disable unnecessary services**:
   ```bash
   sudo systemctl disable bluetooth
   sudo systemctl disable cups
   ```

3. **Use hardware acceleration**: Ensure Mesa drivers are properly installed

## Screen Power Management (Kiosk Mode)

The touch application includes built-in screen power management with touch-to-wake functionality.

### Automatic Screen Timeout
The screen will automatically turn off after 5 minutes (300 seconds) of inactivity and can be woken by touching the screen.

### Manual Screen Control
You can also control the screen manually from the command line:

```bash
# Turn screen OFF
sudo vcgencmd display_power 0

# Turn screen ON
sudo vcgencmd display_power 1

# Alternative: Control backlight
sudo sh -c 'echo "0" > /sys/class/backlight/*/brightness'  # OFF
sudo sh -c 'echo "255" > /sys/class/backlight/*/brightness'  # ON
```

### Configure Screen Timeout
The default timeout is 5 minutes, but you can modify it in your application by calling:

```python
# In your backend or QML code
backend.setScreenTimeout(600)  # 10 minutes
```

### Permissions for Screen Control
The application needs sudo permissions for screen control. Add these to sudoers:

```bash
sudo visudo
# Add these lines for the pi user:
pi ALL=(ALL) NOPASSWD: /usr/bin/vcgencmd
pi ALL=(ALL) NOPASSWD: /bin/sh -c echo * > /sys/class/backlight/*/brightness
pi ALL=(ALL) NOPASSWD: /bin/cat /dev/input/event*
```

### Features
- **Automatic timeout**: Screen turns off after configured inactivity period
- **Touch-to-wake**: Any touch on the screen will wake it up immediately  
- **Activity tracking**: All mouse/touch interactions reset the timeout timer
- **Fallback methods**: Uses vcgencmd first, falls back to backlight control
- **Background monitoring**: Monitors touch input devices when screen is off