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
- **Patterns** come from `GET /sand_patterns`; previews are rendered locally and cached
  under `preview_cache/`. The `.thr` source is read from the co-located backend catalog
  (`../patterns/`, matched by path suffix / unique basename) when available — fetching
  from the board's SD (`/sd/patterns/...`) is the slow fallback for board-only patterns.
- **Password-protected boards** are supported: the `$Sand/Password` key is stored
  (base64) in `touch_settings.json` and sent as `X-Sand-Key` on every request; set it
  under Control → Table Connection. `503 busy: low memory` responses are retried with
  backoff, and the clock sync pushes epoch + POSIX timezone (quiet-hours/autostart
  schedules run on board-local time).
- **Playlists** are `.txt` files on the SD card — listed via `GET /sand_playlists`,
  read from `/sd/playlists/...`, and created/edited by uploading/deleting files.
- **LEDs** use the firmware's named effect/palette catalogue (`$LED/*` / `/sand_led`).
- **Screen / LCD backlight** control stays local to the touch host (sysfs + sudo scripts).

See the firmware's `API.md` for the full contract.

## Features

- **Five pages**: Browse, Playlists, Control, Light (LED ring), and Now Playing
- **Pattern Browsing**: grid of circular sand-dish previews with search
- **Now Playing**: progress drawn as an ember arc around the live pattern disc,
  with the ball as the moving endpoint — plus transport and speed controls
- **Table Control**: mDNS table discovery, movement, auto-play, screen settings
- **"Table at night" design system**: warm basalt/bone night palette (default)
  and a sand day palette, one amber accent, all defined in
  `qml/components/ThemeManager.qml`; bundled Outfit + Material Icons Round
  fonts in `fonts/` (registered in `main.py`, no system fonts needed)
- **Touch Optimized**: 48px+ targets, pill controls, linuxfb-safe (no effects layers)

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
├── main.py                     # Application entry point (fonts, QML engine)
├── backend.py                  # Backend controller (status poll, actions, LEDs)
├── firmware_client.py          # Shared async HTTP client to the firmware
├── discovery.py                # mDNS table discovery
├── thr_preview.py              # .thr → cached PNG preview renderer
├── fonts/                      # Bundled Outfit + Material Icons Round fonts
├── models/
│   ├── pattern_model.py        # Pattern list model (firmware-backed)
│   └── playlist_model.py       # Playlist model (firmware-backed)
├── qml/
│   ├── main.qml                    # Main window, tab navigation, error dialog
│   ├── pages/
│   │   ├── ModernPatternListPage.qml  # Browse: grid + search
│   │   ├── PatternDetailPage.qml      # Pattern detail: clear mode + play
│   │   ├── ModernPlaylistPage.qml     # Playlists: list, detail, settings
│   │   ├── PatternSelectorPage.qml    # Add-to-playlist pattern picker
│   │   ├── TableControlPage.qml       # Connection, movement, system settings
│   │   ├── LedControlPage.qml         # Light: power, effects, ball tracker
│   │   └── ExecutionPage.qml          # Now Playing: progress ring + transport
│   └── components/
│       ├── ThemeManager.qml        # Design tokens (palettes, type, spacing)
│       ├── Icon.qml                # Material icon glyph by name
│       ├── ModernControlButton.qml # Pill button (filled / outlined)
│       ├── ChoiceChip.qml          # Selectable option chip
│       ├── DwSlider.qml / DwSwitch.qml / SectionLabel.qml / SettingsCard.qml
│       ├── ModernPatternCard.qml   # Pattern card with circular preview
│       └── BottomNavigation.qml / BottomNavTab.qml / ConnectionStatus.qml
├── requirements.txt
└── README.md
```

## Usage

### Navigation
- **Bottom tabs** switch between the five pages:
  - **Browse**: search and pick patterns
  - **Playlists**: create and run playlists
  - **Control**: connection, movement, and device settings
  - **Light**: the table's LED ring
  - **Now Playing**: live progress ring and transport controls

### Playing patterns
1. **Browse**: the Browse tab shows the pattern grid with thumbnail previews; use the
   search field to filter by name
2. **Select**: tap a pattern card to open its detail page
3. **Play**: pick a clear mode (adaptive / from center / from perimeter / none) with the
   chips, then tap Play — the firmware sequences the clear before the pattern

### While a pattern runs
1. **Now Playing** shows the live disc with the ember progress arc and the ball as the
   moving endpoint, plus Pause/Resume, Stop, Skip, and speed controls
2. **Control** handles the connection (discovered tables, password), movement/homing,
   auto-play, and screen settings; the header dot reflects the polled connection state

## Notes

- The touch interface talks directly to the table firmware; no host service is required
- The firmware's HTTP API is multi-client, so the app can run alongside other clients
  (phone/web app, Home Assistant) at the same time
- Pattern previews render locally the first time a pattern is seen, then load from cache
- Requires the table to be reachable on the network (mDNS or `DUNE_WEAVER_URL`)