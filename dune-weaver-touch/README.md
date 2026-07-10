# Dune Weaver Touch Interface

A PySide6/QML touch interface for the Dune Weaver sand table. It talks **directly to the
table's FluidNC firmware** over its stateless HTTP/JSON API — there is no separate host
(Raspberry Pi FastAPI) service in between.

## Connecting to the table

The firmware is headless and advertises itself over mDNS. On launch the app:

1. **Auto-discovers** tables via mDNS (`_http._tcp` advertisements with `model=dune-weaver`).
   If exactly one is found it connects automatically; otherwise pick one from the Control
   page's table list (tap **Refresh** to re-scan).
2. **Pin a table** by setting `DUNE_WEAVER_URL` in `.env` (e.g. `DUNE_WEAVER_URL=dunetable.local`
   or an IP). This skips discovery.

The chosen table is remembered in `touch_settings.json`.

### How it maps to the firmware API

- **Status** is polled from `GET /sand_status` (~1 Hz) instead of a WebSocket.
- **Actions** go out as `$...` commands via `/command` and the `/sand_*` routes
  (run/stop/pause/resume/home/goto/feed/LED).
- **Patterns** come from `GET /sand_patterns`; previews are rendered locally from the
  raw `.thr` files (`/sd/patterns/...`) and cached under `preview_cache/`.
- **Playlists** are `.txt` files on the SD card — listed via `GET /sand_playlists`,
  read from `/sd/playlists/...`, and created/edited by uploading/deleting files.
- **LEDs** use the firmware's named effect/palette catalogue (`$LED/*` / `/sand_led`).
- **Screen / LCD backlight** control stays local to the touch host (sysfs + sudo scripts).

See the firmware's `API.md` for the full contract.

## Features

- **Modern SwipeView Navigation**: Swipe between Patterns, Playlists, and Control pages
- **Pattern Browsing**: Beautiful grid view with search and thumbnail previews
- **Pattern Execution**: Touch-optimized controls with pre-execution options
- **Table Control**: Dedicated control page with status monitoring and quick actions
- **Real-time Status**: WebSocket integration for live progress updates
- **Modern UI**: Material Design inspired interface with animations and shadows
- **Touch Optimized**: Large buttons, smooth animations, and intuitive gestures

## Architecture

- **Pattern Browsing**: `GET /sand_patterns` on the table; `.thr` previews rendered locally
- **Execution Control**: firmware `$...` commands via `/command` + `/sand_*` routes
- **Status Monitoring**: polling `GET /sand_status` (~1 Hz)
- **Navigation**: StackView-based page navigation

### Key modules

- `firmware_client.py` — shared async HTTP client + LED/clear-mode maps (singleton)
- `discovery.py` — mDNS table discovery (zeroconf; degrades gracefully if absent)
- `thr_preview.py` — renders `.thr` → cached PNG previews
- `backend.py` — QML-facing controller (status poll, actions, LEDs, playlists, local screen)
- `models/` — `PatternModel` / `PlaylistModel`, both firmware-backed

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

2. Power on the sand table and make sure it's on the same network (or set
   `DUNE_WEAVER_URL` in `.env` to pin its address).

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

- The touch interface talks directly to the table firmware; no host service is required
- The firmware's HTTP API is multi-client, so the app can run alongside other clients
  (phone/web app, Home Assistant) at the same time
- Pattern previews render locally the first time a pattern is seen, then load from cache
- Requires the table to be reachable on the network (mDNS or `DUNE_WEAVER_URL`)