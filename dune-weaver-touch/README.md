# Dune Weaver Touch Interface

A PySide6/QML touch interface for the Dune Weaver sand table system that works alongside the existing FastAPI web server.

## Features

- **Modern SwipeView Navigation**: Swipe between Patterns, Playlists, and Control pages
- **Pattern Browsing**: Beautiful grid view with search and thumbnail previews
- **Pattern Execution**: Touch-optimized controls with pre-execution options
- **Table Control**: Dedicated control page with status monitoring and quick actions
- **Real-time Status**: WebSocket integration for live progress updates
- **Modern UI**: Material Design inspired interface with animations and shadows
- **Touch Optimized**: Large buttons, smooth animations, and intuitive gestures

## Architecture

- **Pattern Browsing**: Direct file system access for instant loading
- **Execution Control**: REST API calls to existing FastAPI endpoints  
- **Status Monitoring**: WebSocket connection for real-time updates
- **Navigation**: StackView-based page navigation

## Quick Installation (Auto-Start Setup)

**One command to set up everything for kiosk/production use:**

```bash
sudo ./install.sh
```

This will:
- ✅ Create Python virtual environment with dependencies (`venv/`)
- ✅ Install system scripts for screen control (`/usr/local/bin/screen-on`, `screen-off`, `touch-monitor`)
- ✅ Set up systemd service for auto-start on boot  
- ✅ Configure kiosk optimizations (clean boot, auto-login)
- ✅ Enable automatic startup

### Service Management
```bash
# Control the service
sudo systemctl start dune-weaver-touch    # Start now
sudo systemctl stop dune-weaver-touch     # Stop service
sudo systemctl status dune-weaver-touch   # Check status
sudo journalctl -u dune-weaver-touch -f   # View logs

# Disable auto-start
sudo systemctl disable dune-weaver-touch
```

## Manual Installation (Development)

1. Create virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # or: . venv/bin/activate
   pip install -r requirements.txt
   ```

2. Ensure the main Dune Weaver FastAPI server is running:
   ```bash
   cd ../  # Go to main dune-weaver directory
   python main.py
   ```

3. Run the touch interface:
   ```bash
   ./run.sh              # Uses virtual environment automatically
   # OR manually:
   ./venv/bin/python main.py
   ```

## Advanced Setup Options

For custom installations:
```bash
sudo ./setup-autostart.sh
```

Choose from multiple setup options including systemd service, desktop autostart, or kiosk optimizations.

## Project Structure

```
dune-weaver-touch/
├── main.py                     # Application entry point
├── backend.py                  # Backend controller with API/WebSocket integration
├── models/
│   ├── pattern_model.py        # Pattern list model with file system access
│   └── playlist_model.py       # Playlist model reading from JSON
├── qml/
│   ├── main.qml               # Main window with StackView navigation
│   ├── pages/
│   │   ├── PatternListPage.qml    # Grid view of patterns with search
│   │   ├── PatternDetailPage.qml  # Pattern details with execution controls
│   │   ├── PlaylistPage.qml       # Playlist selection and execution
│   │   └── ExecutionPage.qml      # Current execution status display
│   └── components/
│       └── PatternCard.qml        # Pattern thumbnail card
├── requirements.txt
└── README.md
```

## Usage

### Navigation
- **Swipe left/right** to navigate between the three main pages:
  - **Patterns**: Browse and search through all available patterns
  - **Playlists**: View and manage pattern playlists
  - **Control**: Monitor table status and quick control actions

### Pattern Management
1. **Browse Patterns**: Swipe to Patterns page to see grid view with thumbnail previews
2. **Search**: Use the search field to filter patterns by name
3. **Select Pattern**: Tap a pattern card to view details and execution options
4. **Execute**: Choose pre-execution action and tap "Play Pattern"

### Table Control
1. **Monitor Status**: Swipe to Control page to see current pattern and progress
2. **Control Execution**: Use Pause/Resume and Stop buttons
3. **Quick Actions**: Use Clear In, Clear Out, or Circle pattern shortcuts
4. **Connection Status**: View WebSocket connection status

## Notes

- The touch interface runs independently from the web UI
- Both interfaces can be used simultaneously
- Pattern browsing works even if the FastAPI server is offline
- Execution requires the FastAPI server to be running
- Paths are relative to the main dune-weaver directory