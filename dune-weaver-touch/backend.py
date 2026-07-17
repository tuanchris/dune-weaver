from PySide6.QtCore import QObject, Signal, Property, Slot, QTimer
from PySide6.QtQml import QmlElement
import asyncio
import base64
import json
import logging
import subprocess
import threading
import time
from pathlib import Path
import os

from firmware_client import (FirmwareClient, LED_EFFECTS, LED_PALETTES,
                             friendly_error, posix_tz)
import discovery

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("DuneWeaver")

QML_IMPORT_NAME = "DuneWeaver"
QML_IMPORT_MAJOR_VERSION = 1

# Firmware clear-mode -> touch UI pre-execution option (reverse of CLEAR_MODE_MAP)
_FW_TO_UI_CLEAR = {
    "in": "clear_center", "out": "clear_perimeter",
    "adaptive": "adaptive", "none": "none",
    "sideway": "adaptive", "random": "adaptive",
}


def _run(coro):
    """Schedule a coroutine on the running (qasync) event loop, if any."""
    try:
        asyncio.get_event_loop().create_task(coro)
    except RuntimeError:
        logger.warning("No running event loop to schedule task")


def _clamp_int(value, default, lo, hi):
    """Coerce ``value`` to an int within [lo, hi], falling back to ``default``."""
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


@QmlElement
class Backend(QObject):
    """Backend controller: drives a headless FluidNC sand table over HTTP."""

    # Constants
    SETTINGS_FILE = "touch_settings.json"
    DEFAULT_SCREEN_TIMEOUT = 300  # 5 minutes in seconds
    STATUS_POLL_MS = 1000         # /sand_status poll interval
    # Consecutive poll failures before the UI flips to "disconnected". The
    # board's single-threaded web server stalls status reads for seconds while
    # it serves file transfers, so one slow/failed poll means "busy", not
    # "gone". A hard-down board fails fast (connection refused), so real
    # disconnects are still detected within a few seconds.
    STATUS_FAIL_THRESHOLD = 3

    # Predefined timeout options (in seconds)
    TIMEOUT_OPTIONS = {
        "30 seconds": 30,
        "1 minute": 60,
        "5 minutes": 300,
        "10 minutes": 600,
        "Never": 0  # 0 means never timeout
    }

    # Predefined speed options (motor feed, mm/min)
    SPEED_OPTIONS = {
        "50": 50,
        "100": 100,
        "150": 150,
        "200": 200,
        "300": 300,
        "500": 500
    }

    # Predefined pause between patterns options (in seconds)
    PAUSE_OPTIONS = {
        "0s": 0, "1 min": 60, "5 min": 300, "15 min": 900, "30 min": 1800,
        "1 hour": 3600, "2 hour": 7200, "3 hour": 10800, "4 hour": 14400,
        "5 hour": 18000, "6 hour": 21600, "12 hour": 43200
    }

    # Signals
    statusChanged = Signal()
    progressChanged = Signal()
    connectionChanged = Signal()
    executionStarted = Signal(str, str)  # patternName, patternPreview
    patternPreviewReady = Signal(str, str)  # patternName, preview rendered late
    executionStopped = Signal()
    errorOccurred = Signal(str)
    serialPortsUpdated = Signal(list)          # now: list of discovered table URLs
    discoveredTablesUpdated = Signal(list)     # [{name, url}] from mDNS discovery
    serialConnectionChanged = Signal(bool)     # now: table reachable
    currentPortChanged = Signal(str)           # now: current table URL
    speedChanged = Signal(int)
    settingsLoaded = Signal()
    screenStateChanged = Signal(bool)
    screenTimeoutChanged = Signal(int)
    pauseBetweenPatternsChanged = Signal(int)
    pausedChanged = Signal(bool)
    playlistSettingsChanged = Signal()
    patternsRefreshCompleted = Signal(bool, str)

    # Playlist management signals
    playlistCreated = Signal(bool, str)
    playlistDeleted = Signal(bool, str)
    patternAddedToPlaylist = Signal(bool, str)
    playlistModified = Signal(bool, str)

    # Backend/table connection status signals
    backendConnectionChanged = Signal(bool)
    reconnectStatusChanged = Signal(str)

    # LED control signals
    ledStatusChanged = Signal()
    ledEffectsLoaded = Signal(list)
    ledPalettesLoaded = Signal(list)

    # LCD brightness signals
    lcdBrightnessChanged = Signal()

    def __init__(self):
        super().__init__()
        self.client = FirmwareClient.instance()

        # Status properties
        self._current_file = ""
        self._progress = 0
        self._is_running = False
        self._is_paused = False
        self._is_connected = False
        self._serial_ports = []
        self._serial_connected = False
        self._current_port = ""
        self._current_speed = 130
        self._auto_play_on_boot = False
        self._pause_between_patterns = 10800

        # Playlist settings (mirror the table's NVS; also persisted locally)
        self._playlist_shuffle = True
        self._playlist_run_mode = "loop"
        self._playlist_clear_pattern = "adaptive"

        # Connection status
        self._backend_connected = False
        self._reconnect_status = "Looking for table..."
        self._saved_table_url = ""

        # LCD brightness state
        self._lcd_brightness = 255
        self._lcd_brightness_path = ""
        self._lcd_max_brightness = 0

        # LED control state
        self._led_provider = "none"       # "none" or "dw_leds"
        self._led_connected = False
        self._led_power_on = False
        self._led_brightness = 100        # 0..100 for QML (firmware is 0..255)
        self._led_effects = []
        self._led_palettes = []
        self._led_current_effect = 0
        self._led_current_palette = 0
        self._led_color = "#ffffff"
        self._led_last_effect = 2         # remembered on power-off (default rainbow)

        # 'ball' tracker state (firmware-native effect id 38; the blob follows
        # the sand ball). Mirrors the board's NVS; written live via /sand_led.
        self._led_color2 = "#000000"      # background colour when bg == "static"
        self._led_ball_fgbright = 255     # blob brightness (0..255)
        self._led_ball_bgbright = 255     # background brightness (0..255)
        self._led_ball_size = 3           # glow size in LEDs (1..30 in the UI)
        self._led_ball_bg = "static"      # "static" | "off" | any effect name
        self._led_ball_direction = "cw"   # "cw" | "ccw"
        self._led_ball_align = 0          # rotate the blob onto the ball (0..359)
        self._led_last_non_ball_effect = 2  # restored when the ball toggle is off

        # Screen management
        self._screen_on = True
        self._screen_timeout = self.DEFAULT_SCREEN_TIMEOUT
        self._last_activity = time.time()
        self._screen_transition_lock = threading.Lock()
        self._last_screen_change = 0
        self._screen_timer = QTimer()
        self._screen_timer.timeout.connect(self._check_screen_timeout)
        self._screen_timer.start(1000)

        # Load local settings first
        self._load_local_settings()
        self._detect_backlight()

        # Apply the saved table password ($Sand/Password key) to the client.
        self.client.set_api_key(self._decode_password(self._table_password_b64))

        # Point the shared client at the saved / env-configured table.
        env_url = os.environ.get("DUNE_WEAVER_URL", "")
        initial_url = env_url or self._saved_table_url
        if initial_url:
            self.client.set_base_url(initial_url)
            self._current_port = self.client.base_url

        # Status polling replaces the old WebSocket status stream.
        self._status_timer = QTimer()
        self._status_timer.timeout.connect(self._tick_status)
        self._time_synced = False
        self._poll_inflight = False   # never stack polls on the busy board
        self._poll_failures = 0       # consecutive failures (see threshold)
        self._discovered_tables = []  # [{name, url}] from the last mDNS browse
        self._table_name = ""         # firmware hostname from /sand_status
        self._table_password_b64 = "" # $Sand/Password, base64 like the backend

        # Playlist run state from /sand_status's playlist object (firmware
        # sequences playlists; this is read-only telemetry, like the
        # backend's translate_status).
        self._playlist_active = False
        self._playlist_index = 0      # 0-based position in the playlist
        self._playlist_total = 0
        self._playlist_name = ""
        self._next_pattern = ""       # next pattern (display name, no path/.thr)
        self._playlist_clearing = False
        self._pause_remaining = -1    # seconds until next pattern; -1 = not pausing
        self._pause_total = -1

        # Kick everything off once the event loop is running.
        QTimer.singleShot(200, self._start)

    @Slot()
    def _start(self):
        self._status_timer.start(self.STATUS_POLL_MS)
        if not self.client.base_url:
            # No configured table -> try to discover one automatically.
            _run(self._discover(auto_connect=True))

    async def _discover(self, auto_connect=False):
        """mDNS-browse for tables; auto_connect picks one on startup.

        Preference order: the last-connected table (saved URL) if it's on the
        network, otherwise the first table found — the touch panel should
        come up connected without being asked.
        """
        self._set_reconnect_status("Searching for tables (mDNS)...")
        try:
            tables = await discovery.discover_tables(timeout=3.0)
        except Exception as exc:
            logger.warning(f"Discovery failed: {exc}")
            tables = []
        self._serial_ports = [t.base_url for t in tables]
        self._discovered_tables = [{"name": t.name, "url": t.base_url} for t in tables]
        self.serialPortsUpdated.emit(self._serial_ports)
        self.discoveredTablesUpdated.emit(self._discovered_tables)
        if not auto_connect:
            return
        if not tables:
            self._set_reconnect_status("No table found. Enter the table address.")
            return
        target = next((t for t in tables if t.base_url == self._saved_table_url),
                      tables[0])
        which = "last-connected" if target.base_url == self._saved_table_url else "first discovered"
        logger.info(f"Auto-connecting to the {which} table: {target.base_url}")
        self._connect_to(target.base_url)

    # ==================== Status polling ====================
    @Slot()
    def _tick_status(self):
        _run(self._poll_status())

    async def _poll_status(self):
        if not self.client.base_url or self._poll_inflight:
            return
        self._poll_inflight = True
        try:
            data = await self.client.status()
        except Exception as exc:
            self._poll_failures += 1
            reason = str(exc) or type(exc).__name__
            # 401 = board is password-locked; deterministic, so say so
            # instead of the generic "retrying" message.
            if getattr(exc, "status", None) == 401:
                self._on_unreachable(reason)
                self._set_reconnect_status(
                    "Table requires a password — set it below.")
            elif self._poll_failures >= self.STATUS_FAIL_THRESHOLD:
                self._on_unreachable(reason)
            else:
                logger.debug(f"Status poll failed ({self._poll_failures}/"
                             f"{self.STATUS_FAIL_THRESHOLD}): {reason}")
            return
        finally:
            self._poll_inflight = False
        self._poll_failures = 0
        self._on_status(data)

    def _on_status(self, status):
        # Reachability
        if not self._backend_connected:
            self._backend_connected = True
            self._is_connected = True
            self._serial_connected = True
            self._current_port = self.client.base_url
            self._reconnect_status = "Connected"
            self.connectionChanged.emit()
            self.backendConnectionChanged.emit(True)
            self.serialConnectionChanged.emit(True)
            self.currentPortChanged.emit(self._current_port)
            self.reconnectStatusChanged.emit("Connected")
            # Load settings + LED config on (re)connect.
            self.loadControlSettings()
            self.loadLedConfig()
            _run(self._sync_time_once())

        # GRBL states can carry a substate suffix ("Hold:0") — strip it, like
        # the backend's execution._state() does, or pause is never detected.
        state = (status.get("state") or "").split(":", 1)[0]
        self._table_name = status.get("hostname", "") or self._table_name

        # Current pattern / execution start detection
        raw_file = status.get("file", "") or ""
        new_file = raw_file
        for prefix in ("/sd/patterns/", "/patterns/", "/sd/", "/"):
            if new_file.startswith(prefix):
                new_file = new_file[len(prefix):]
                break
        if new_file and new_file != self._current_file:
            logger.info(f"Pattern changed to '{new_file}'")
            preview = self._preview_path(new_file)
            self.executionStarted.emit(new_file, preview)
            if not preview:
                _run(self._render_preview_late(new_file))
        self._current_file = new_file

        self._is_running = bool(status.get("running", False))

        # Playlist telemetry (between-patterns pause countdown + position)
        pl = status.get("playlist") or {}
        self._playlist_active = bool(pl.get("active"))
        self._playlist_index = int(pl.get("index", 0) or 0)
        self._playlist_total = int(pl.get("total", 0) or 0)
        self._playlist_name = str(pl.get("name") or "")
        nxt = str(pl.get("next") or "").rsplit("/", 1)[-1]
        self._next_pattern = nxt[:-4] if nxt.endswith(".thr") else nxt
        self._playlist_clearing = bool(pl.get("clearing"))

        def _secs(v):
            return int(v) if isinstance(v, (int, float)) and v >= 0 else -1
        self._pause_remaining = _secs(pl.get("pause_remaining", -1))
        self._pause_total = _secs(pl.get("pause_total", -1))

        new_paused = (state == "Hold")
        if new_paused != self._is_paused:
            self._is_paused = new_paused
            self.pausedChanged.emit(new_paused)

        feed = status.get("feed")
        if feed and int(feed) != self._current_speed:
            self._current_speed = int(feed)
            self.speedChanged.emit(self._current_speed)

        prog = status.get("progress")
        if prog is not None:
            self._progress = 0 if prog < 0 else float(prog) * 100.0

        # Live LED snapshot (effect/brightness) from status
        led = status.get("led")
        if isinstance(led, dict):
            self._ingest_led_status(led)

        self.statusChanged.emit()
        self.progressChanged.emit()

    def _on_unreachable(self, reason):
        if self._backend_connected or self._is_connected:
            logger.warning(f"Table unreachable: {reason}")
        self._backend_connected = False
        self._is_connected = False
        if self._serial_connected:
            self._serial_connected = False
            self.serialConnectionChanged.emit(False)
        self._reconnect_status = "Table connection lost, retrying..."
        self.connectionChanged.emit()
        self.backendConnectionChanged.emit(False)
        self.reconnectStatusChanged.emit(self._reconnect_status)

    def _set_reconnect_status(self, msg):
        self._reconnect_status = msg
        self.reconnectStatusChanged.emit(msg)

    async def _sync_time_once(self):
        if self._time_synced:
            return
        try:
            # epoch + POSIX tz, like the backend — board-side quiet-hours and
            # autostart schedules run on the board's local time.
            await self.client.sync_time(int(time.time()), tz=posix_tz())
            self._time_synced = True
        except Exception as exc:
            logger.debug(f"time sync failed: {exc}")

    # ==================== Table password ($Sand/Password) ====================
    @staticmethod
    def _decode_password(b64: str):
        if not b64:
            return None
        try:
            return base64.b64decode(b64).decode("utf-8")
        except Exception:
            return None

    @Slot(str)
    def setTablePassword(self, password):
        """Store the table's API password (empty string clears it)."""
        password = (password or "").strip()
        self._table_password_b64 = (
            base64.b64encode(password.encode("utf-8")).decode("ascii")
            if password else "")
        self.client.set_api_key(password or None)
        self._save_local_settings()
        logger.info("Table password %s", "set" if password else "cleared")
        _run(self._poll_status())

    @Property(bool, notify=settingsLoaded)
    def hasTablePassword(self):
        return bool(self._table_password_b64)

    def _preview_path(self, rel_name):
        """Best-effort cached preview path for a pattern (may be empty)."""
        try:
            import thr_preview
            return thr_preview.cached_preview(self.client.base_url, rel_name)
        except Exception:
            return ""

    async def _render_preview_late(self, rel_name):
        """Render an uncached preview for the executing pattern, then notify.

        The Execution page otherwise only ever sees whatever was cached at
        the moment the pattern started."""
        try:
            import thr_preview
            path = await thr_preview.render_preview(
                self.client, self.client.base_url, rel_name)
        except Exception as exc:
            logger.debug(f"late preview render failed for {rel_name}: {exc}")
            return
        if path:
            self.patternPreviewReady.emit(rel_name, path)

    # ==================== Properties ====================
    @Property(str, notify=statusChanged)
    def currentFile(self):
        return self._current_file

    @Property(float, notify=progressChanged)
    def progress(self):
        return self._progress

    @Property(bool, notify=statusChanged)
    def isRunning(self):
        return self._is_running

    @Property(bool, notify=pausedChanged)
    def isPaused(self):
        return self._is_paused

    @Property(bool, notify=connectionChanged)
    def isConnected(self):
        return self._is_connected

    @Property(str, notify=statusChanged)
    def tableName(self):
        return self._table_name

    @Property(bool, notify=statusChanged)
    def playlistActive(self):
        return self._playlist_active

    @Property(int, notify=statusChanged)
    def playlistIndex(self):
        return self._playlist_index

    @Property(int, notify=statusChanged)
    def playlistTotal(self):
        return self._playlist_total

    @Property(str, notify=statusChanged)
    def playlistName(self):
        return self._playlist_name

    @Property(str, notify=statusChanged)
    def nextPattern(self):
        return self._next_pattern

    @Property(bool, notify=statusChanged)
    def playlistClearing(self):
        return self._playlist_clearing

    @Property(int, notify=statusChanged)
    def pauseRemaining(self):
        return self._pause_remaining

    @Property(int, notify=statusChanged)
    def pauseTotal(self):
        return self._pause_total

    @Property(list, notify=discoveredTablesUpdated)
    def discoveredTables(self):
        return self._discovered_tables

    @Property(list, notify=serialPortsUpdated)
    def serialPorts(self):
        return self._serial_ports

    @Property(bool, notify=serialConnectionChanged)
    def serialConnected(self):
        return self._serial_connected

    @Property(str, notify=currentPortChanged)
    def currentPort(self):
        return self._current_port

    @Property(int, notify=speedChanged)
    def currentSpeed(self):
        return self._current_speed

    @Property(bool, notify=settingsLoaded)
    def autoPlayOnBoot(self):
        return self._auto_play_on_boot

    @Property(bool, notify=backendConnectionChanged)
    def backendConnected(self):
        return self._backend_connected

    @Property(str, notify=reconnectStatusChanged)
    def reconnectStatus(self):
        return self._reconnect_status

    # ==================== Connection management ====================
    @Slot()
    def retryConnection(self):
        logger.debug("Manual connection retry requested")
        if self.client.base_url:
            _run(self._poll_status())
        else:
            _run(self._discover(auto_connect=True))

    @Slot()
    def refreshSerialPorts(self):
        """Re-run mDNS discovery to populate the table picker (list only —
        never switches tables; connecting is an explicit user tap)."""
        logger.info("Discovering tables...")
        _run(self._discover())

    @Slot(str)
    def connectSerial(self, port):
        """Point the app at a table (URL or host)."""
        logger.info(f"Connecting to table: {port}")
        self._connect_to(port)

    def _connect_to(self, url):
        self.client.set_base_url(url)
        self._current_port = self.client.base_url
        self._saved_table_url = self.client.base_url
        self._time_synced = False
        self._poll_failures = 0  # fresh table, fresh streak
        self._save_local_settings()
        self.currentPortChanged.emit(self._current_port)
        self._set_reconnect_status(f"Connecting to {self._current_port}...")
        _run(self._poll_status())

    @Slot()
    def disconnectSerial(self):
        logger.info("Disconnecting from table...")
        self.client.set_base_url("")
        self._current_port = ""
        self._table_name = ""
        self._serial_connected = False
        self._backend_connected = False
        self._is_connected = False
        self.serialConnectionChanged.emit(False)
        self.currentPortChanged.emit("")
        self.backendConnectionChanged.emit(False)
        self.connectionChanged.emit()

    # ==================== Pattern execution ====================
    @Slot(str, str)
    def executePattern(self, fileName, preExecution="adaptive"):
        logger.info(f"ExecutePattern: '{fileName}' (clear={preExecution})")
        _run(self._execute_pattern(fileName, preExecution))

    async def _execute_pattern(self, fileName, preExecution):
        try:
            await self.client.run_pattern(fileName, preExecution)
            preview = self._preview_path(fileName)
            self.executionStarted.emit(fileName, preview)
            if not preview:
                _run(self._render_preview_late(fileName))
        except Exception as exc:
            logger.error(f"executePattern failed: {exc}")
            self.errorOccurred.emit("Couldn't start the pattern. " + friendly_error(exc))

    @Slot()
    def stopExecution(self):
        _run(self._simple_action(self.client.stop, on_ok=self.executionStopped.emit,
                                 label="stop"))

    @Slot()
    def pauseExecution(self):
        logger.info("Pausing execution...")
        _run(self._simple_action(self.client.pause, label="pause"))

    @Slot()
    def resumeExecution(self):
        logger.info("Resuming execution...")
        _run(self._simple_action(self.client.resume, label="resume"))

    @Slot()
    def skipPattern(self):
        logger.info("Skipping pattern...")
        _run(self._simple_action(self.client.playlist_skip, label="skip"))

    async def _simple_action(self, coro_fn, *, on_ok=None, label="action"):
        try:
            await coro_fn()
            if on_ok:
                on_ok()
        except Exception as exc:
            logger.error(f"{label} failed: {exc}")
            self.errorOccurred.emit(f"Couldn't {label}. " + friendly_error(exc))

    @Slot(str, float, str, str, bool)
    def executePlaylist(self, playlistName, pauseTime=0.0, clearPattern="adaptive",
                        runMode="single", shuffle=False):
        logger.info(f"ExecutePlaylist: '{playlistName}' pause={pauseTime} "
                    f"clear={clearPattern} mode={runMode} shuffle={shuffle}")
        _run(self._execute_playlist(playlistName, pauseTime, clearPattern, runMode, shuffle))

    async def _execute_playlist(self, name, pauseTime, clearPattern, runMode, shuffle):
        try:
            await self.client.run_playlist(
                name, pause_time=pauseTime, clear_pattern=clearPattern,
                run_mode=runMode, shuffle=shuffle)
        except Exception as exc:
            logger.error(f"executePlaylist failed: {exc}")
            self.errorOccurred.emit("Couldn't start the playlist. " + friendly_error(exc))

    # ==================== Hardware movement ====================
    @Slot()
    def sendHome(self):
        logger.debug("Sending home command...")
        _run(self._simple_action(self.client.home, label="home"))

    @Slot()
    def moveToCenter(self):
        logger.info("Moving to center...")
        _run(self._simple_action(lambda: self.client.goto(rho=0), label="move to center"))

    @Slot()
    def moveToPerimeter(self):
        logger.info("Moving to perimeter...")
        _run(self._simple_action(lambda: self.client.goto(rho=1), label="move to perimeter"))

    # ==================== Speed ====================
    @Slot(int)
    def setSpeed(self, speed):
        logger.debug(f"Setting speed (feed) to: {speed}")
        _run(self._set_speed(speed))

    async def _set_speed(self, speed):
        try:
            await self.client.set_feed_mm(speed)
            self._current_speed = speed
            self.speedChanged.emit(speed)
        except Exception as exc:
            logger.error(f"set speed failed: {exc}")
            self.errorOccurred.emit("Couldn't change the speed. " + friendly_error(exc))

    @Slot(result='QStringList')
    def getSpeedOptions(self):
        return list(self.SPEED_OPTIONS.keys())

    @Slot(result=str)
    def getCurrentSpeedOption(self):
        for option, value in self.SPEED_OPTIONS.items():
            if value == self._current_speed:
                return option
        return str(self._current_speed)

    @Slot(str)
    def setSpeedByOption(self, option):
        if option in self.SPEED_OPTIONS:
            self.setSpeed(self.SPEED_OPTIONS[option])
        else:
            logger.warning(f"Unknown speed option: {option}")

    # ==================== Auto play on boot ====================
    @Slot(bool)
    def setAutoPlayOnBoot(self, enabled):
        logger.info(f"Setting auto play on boot: {enabled}")
        # The firmware auto-plays a *named* playlist ($Playlist/Autostart). We
        # can reliably disable it here; enabling requires choosing a playlist
        # (done from the playlist page), so True is best-effort.
        if not enabled:
            _run(self._simple_action(lambda: self.client.set_autostart(""),
                                     label="clear autostart"))
        else:
            logger.info("Enable auto-play: select a playlist to autostart on the playlist page")
        self._auto_play_on_boot = enabled
        self.settingsLoaded.emit()

    # ==================== Load settings from the table ====================
    @Slot()
    def loadControlSettings(self):
        logger.debug("Loading control settings from table...")
        _run(self._load_settings())

    async def _load_settings(self):
        try:
            settings = await self.client.settings()
        except Exception as exc:
            logger.debug(f"Could not load settings: {exc}")
            return

        def as_int(key, default):
            try:
                return int(float(settings.get(key, default)))
            except (TypeError, ValueError):
                return default

        # Speed / feed
        feed = as_int("THR/Feed", self._current_speed)
        if feed and feed != self._current_speed:
            self._current_speed = feed
            self.speedChanged.emit(feed)

        # Playlist settings (mirror the table)
        mode = settings.get("Playlist/Mode", self._playlist_run_mode)
        if mode in ("single", "loop"):
            self._playlist_run_mode = mode
        self._playlist_shuffle = str(settings.get("Playlist/Shuffle", "ON")).upper() == "ON"
        self._pause_between_patterns = as_int("Playlist/PauseTime", self._pause_between_patterns)
        fw_clear = settings.get("Playlist/ClearPattern", "adaptive")
        self._playlist_clear_pattern = _FW_TO_UI_CLEAR.get(fw_clear, "adaptive")
        self._auto_play_on_boot = bool(settings.get("Playlist/Autostart", "").strip())

        self.playlistSettingsChanged.emit()
        self.pauseBetweenPatternsChanged.emit(self._pause_between_patterns)
        self.settingsLoaded.emit()
        logger.info("Settings loaded from table")

    # ==================== Screen management ====================
    @Property(bool, notify=screenStateChanged)
    def screenOn(self):
        return self._screen_on

    @Property(int, notify=screenTimeoutChanged)
    def screenTimeout(self):
        return self._screen_timeout

    @screenTimeout.setter
    def setScreenTimeout(self, timeout):
        if self._screen_timeout != timeout:
            self._screen_timeout = timeout
            self._save_local_settings()
            self.screenTimeoutChanged.emit(timeout)

    @Slot(result='QStringList')
    def getScreenTimeoutOptions(self):
        return list(self.TIMEOUT_OPTIONS.keys())

    @Slot(result=str)
    def getCurrentScreenTimeoutOption(self):
        current_timeout = self._screen_timeout
        for option, value in self.TIMEOUT_OPTIONS.items():
            if value == current_timeout:
                return option
        if current_timeout == 0:
            return "Never"
        elif current_timeout < 60:
            return f"{current_timeout} seconds"
        elif current_timeout < 3600:
            minutes = current_timeout // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        else:
            hours = current_timeout // 3600
            return f"{hours} hour{'s' if hours != 1 else ''}"

    @Slot(str)
    def setScreenTimeoutByOption(self, option):
        if option in self.TIMEOUT_OPTIONS:
            timeout_value = self.TIMEOUT_OPTIONS[option]
            if self._screen_timeout != timeout_value:
                self._screen_timeout = timeout_value
                self._save_local_settings()
                self.screenTimeoutChanged.emit(timeout_value)
        else:
            logger.warning(f"Unknown timeout option: {option}")

    @Slot()
    def turnScreenOn(self):
        if not self._screen_on:
            self._turn_screen_on()
        self._reset_activity_timer()

    @Slot()
    def turnScreenOff(self):
        self._turn_screen_off()

    @Slot()
    def resetActivityTimer(self):
        self._reset_activity_timer()
        if not self._screen_on:
            self._turn_screen_on()

    def _turn_screen_on(self):
        with self._screen_transition_lock:
            time_since_change = time.time() - self._last_screen_change
            if time_since_change < 2.0:
                return
            if self._screen_on:
                return
            try:
                restore_brightness = self._lcd_brightness if self._lcd_brightness > 0 else self._lcd_max_brightness or 255
                screen_on_script = Path('/usr/local/bin/screen-on')
                if screen_on_script.exists():
                    result = subprocess.run(['sudo', '/usr/local/bin/screen-on'],
                                            capture_output=True, text=True, timeout=5)
                    if result.returncode != 0:
                        logger.warning(f"screen-on script failed: {result.stderr}")
                    if self._lcd_brightness_path and restore_brightness < (self._lcd_max_brightness or 255):
                        subprocess.run(
                            ['sudo', 'sh', '-c', f'echo {restore_brightness} > {self._lcd_brightness_path}'],
                            check=False, timeout=5)
                else:
                    if self._lcd_brightness_path:
                        subprocess.run(['sudo', 'sh', '-c',
                                        f'echo 0 > /sys/class/graphics/fb0/blank && echo {restore_brightness} > {self._lcd_brightness_path}'],
                                       check=False, timeout=5)
                    else:
                        subprocess.run(['sudo', 'sh', '-c',
                                        f'echo 0 > /sys/class/graphics/fb0/blank && echo {restore_brightness} > /sys/class/backlight/*/brightness'],
                                       check=False, timeout=5)
                self._screen_on = True
                self._last_screen_change = time.time()
                self.screenStateChanged.emit(True)
            except Exception as e:
                logger.error(f"Failed to turn screen on: {e}")

    def _turn_screen_off(self):
        with self._screen_transition_lock:
            time_since_change = time.time() - self._last_screen_change
            if time_since_change < 2.0:
                return
            if not self._screen_on:
                return
        try:
            screen_off_script = Path('/usr/local/bin/screen-off')
            if screen_off_script.exists():
                result = subprocess.run(['sudo', '/usr/local/bin/screen-off'],
                                        capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    logger.info("Screen turned OFF (screen-off script)")
                else:
                    logger.warning(f"screen-off script failed: return code {result.returncode}")
            else:
                subprocess.run(['sudo', 'sh', '-c',
                                'echo 0 > /sys/class/backlight/*/brightness && echo 1 > /sys/class/graphics/fb0/blank'],
                               check=False, timeout=5)
            self._screen_on = False
            self._last_screen_change = time.time()
            self.screenStateChanged.emit(False)
        except Exception as e:
            logger.error(f"Failed to turn screen off: {e}")

    def _reset_activity_timer(self):
        self._last_activity = time.time()

    def _check_screen_timeout(self):
        if self._screen_on and self._screen_timeout > 0:
            idle_time = time.time() - self._last_activity
            if idle_time > self._screen_timeout:
                self._turn_screen_off()

    # ==================== Local settings persistence ====================
    def _load_local_settings(self):
        try:
            if os.path.exists(self.SETTINGS_FILE):
                with open(self.SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)
                screen_timeout = settings.get('screen_timeout', self.DEFAULT_SCREEN_TIMEOUT)
                if isinstance(screen_timeout, (int, float)) and screen_timeout >= 0:
                    self._screen_timeout = int(screen_timeout)
                self._lcd_brightness = settings.get('lcd_brightness', 255)
                self._lcd_brightness_path = settings.get('lcd_brightness_path', "")
                self._lcd_max_brightness = settings.get('lcd_max_brightness', 0)
                self._pause_between_patterns = settings.get('pause_between_patterns', 10800)
                self._playlist_shuffle = settings.get('playlist_shuffle', True)
                self._playlist_run_mode = settings.get('playlist_run_mode', "loop")
                self._playlist_clear_pattern = settings.get('playlist_clear_pattern', "adaptive")
                self._saved_table_url = settings.get('table_url', "")
                self._table_password_b64 = settings.get('table_password', "")
            else:
                self._save_local_settings()
        except Exception as e:
            logger.error(f"Error loading local settings: {e}, using defaults")
            self._screen_timeout = self.DEFAULT_SCREEN_TIMEOUT

    def _save_local_settings(self):
        try:
            settings = {
                'screen_timeout': self._screen_timeout,
                'lcd_brightness': self._lcd_brightness,
                'lcd_brightness_path': self._lcd_brightness_path,
                'lcd_max_brightness': self._lcd_max_brightness,
                'pause_between_patterns': self._pause_between_patterns,
                'playlist_shuffle': self._playlist_shuffle,
                'playlist_run_mode': self._playlist_run_mode,
                'playlist_clear_pattern': self._playlist_clear_pattern,
                'table_url': self._saved_table_url,
                'table_password': self._table_password_b64,
                'version': '2.0'
            }
            with open(self.SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving local settings: {e}")

    # ==================== Pause between patterns ====================
    @Slot(result='QStringList')
    def getPauseOptions(self):
        return list(self.PAUSE_OPTIONS.keys())

    @Slot(result=str)
    def getCurrentPauseOption(self):
        current_pause = self._pause_between_patterns
        for option, value in self.PAUSE_OPTIONS.items():
            if value == current_pause:
                return option
        if current_pause == 0:
            return "0s"
        elif current_pause < 60:
            return f"{current_pause}s"
        elif current_pause < 3600:
            return f"{current_pause // 60} min"
        else:
            return f"{current_pause // 3600} hour"

    @Slot(str)
    def setPauseByOption(self, option):
        if option in self.PAUSE_OPTIONS:
            pause_value = self.PAUSE_OPTIONS[option]
            if self._pause_between_patterns != pause_value:
                self._pause_between_patterns = pause_value
                self._save_local_settings()
                _run(self._simple_action(
                    lambda: self.client.command(f"$Playlist/PauseTime={pause_value}"),
                    label="set pause"))
                self.pauseBetweenPatternsChanged.emit(pause_value)
        else:
            logger.warning(f"Unknown pause option: {option}")

    @Property(int, notify=pauseBetweenPatternsChanged)
    def pauseBetweenPatterns(self):
        return self._pause_between_patterns

    # ==================== Playlist settings ====================
    @Property(bool, notify=playlistSettingsChanged)
    def playlistShuffle(self):
        return self._playlist_shuffle

    @Slot(bool)
    def setPlaylistShuffle(self, enabled):
        if self._playlist_shuffle != enabled:
            self._playlist_shuffle = enabled
            self._save_local_settings()
            _run(self._simple_action(
                lambda: self.client.command(f"$Playlist/Shuffle={'ON' if enabled else 'OFF'}"),
                label="set shuffle"))
            self.playlistSettingsChanged.emit()

    @Property(str, notify=playlistSettingsChanged)
    def playlistRunMode(self):
        return self._playlist_run_mode

    @Slot(str)
    def setPlaylistRunMode(self, mode):
        if mode in ("single", "loop") and self._playlist_run_mode != mode:
            self._playlist_run_mode = mode
            self._save_local_settings()
            _run(self._simple_action(
                lambda: self.client.command(f"$Playlist/Mode={mode}"),
                label="set run mode"))
            self.playlistSettingsChanged.emit()

    @Property(str, notify=playlistSettingsChanged)
    def playlistClearPattern(self):
        return self._playlist_clear_pattern

    @Slot(str)
    def setPlaylistClearPattern(self, pattern):
        valid = ["adaptive", "clear_center", "clear_perimeter", "none"]
        if pattern in valid and self._playlist_clear_pattern != pattern:
            self._playlist_clear_pattern = pattern
            self._save_local_settings()
            from firmware_client import CLEAR_MODE_MAP
            fw = CLEAR_MODE_MAP.get(pattern, "adaptive")
            _run(self._simple_action(
                lambda: self.client.command(f"$Playlist/ClearPattern={fw}"),
                label="set clear pattern"))
            self.playlistSettingsChanged.emit()

    # ==================== LED control ====================
    @Property(str, notify=ledStatusChanged)
    def ledProvider(self):
        return self._led_provider

    @Property(bool, notify=ledStatusChanged)
    def ledConnected(self):
        return self._led_connected

    @Property(bool, notify=ledStatusChanged)
    def ledPowerOn(self):
        return self._led_power_on

    @Property(int, notify=ledStatusChanged)
    def ledBrightness(self):
        return self._led_brightness

    @Property(list, notify=ledEffectsLoaded)
    def ledEffects(self):
        return self._led_effects

    @Property(list, notify=ledPalettesLoaded)
    def ledPalettes(self):
        return self._led_palettes

    @Property(int, notify=ledStatusChanged)
    def ledCurrentEffect(self):
        return self._led_current_effect

    @Property(int, notify=ledStatusChanged)
    def ledCurrentPalette(self):
        return self._led_current_palette

    @Property(str, notify=ledStatusChanged)
    def ledColor(self):
        return self._led_color

    # -- 'ball' tracker properties (firmware effect id 38) -----------------
    @Property(str, notify=ledStatusChanged)
    def ledColor2(self):
        return self._led_color2

    @Property(int, notify=ledStatusChanged)
    def ledBallFgBright(self):
        return self._led_ball_fgbright

    @Property(int, notify=ledStatusChanged)
    def ledBallBgBright(self):
        return self._led_ball_bgbright

    @Property(int, notify=ledStatusChanged)
    def ledBallSize(self):
        return self._led_ball_size

    @Property(str, notify=ledStatusChanged)
    def ledBallBg(self):
        return self._led_ball_bg

    @Property(str, notify=ledStatusChanged)
    def ledBallDirection(self):
        return self._led_ball_direction

    @Property(int, notify=ledStatusChanged)
    def ledBallAlign(self):
        return self._led_ball_align

    @Slot()
    def loadLedConfig(self):
        logger.debug("Loading LED configuration...")
        _run(self._load_led_config())

    async def _load_led_config(self):
        try:
            settings = await self.client.settings()
        except Exception as exc:
            logger.debug(f"LED config load failed: {exc}")
            return

        has_leds = any(k.startswith("LED/") for k in settings)
        self._led_provider = "dw_leds" if has_leds else "none"
        self._led_connected = has_leds

        if has_leds:
            # Expose the fixed catalogues as {id, name} lists for the QML page.
            self._led_effects = [{"id": i, "name": n} for i, n in enumerate(LED_EFFECTS)]
            self._led_palettes = [{"id": i, "name": n} for i, n in enumerate(LED_PALETTES)]
            self.ledEffectsLoaded.emit(self._led_effects)
            self.ledPalettesLoaded.emit(self._led_palettes)

            effect = settings.get("LED/Effect", "off")
            if effect in LED_EFFECTS:
                self._led_current_effect = LED_EFFECTS.index(effect)
            palette = settings.get("LED/Palette", "rainbow")
            if palette in LED_PALETTES:
                self._led_current_palette = LED_PALETTES.index(palette)
            self._led_power_on = (effect != "off")
            if self._led_power_on:
                self._led_last_effect = self._led_current_effect
            try:
                self._led_brightness = round(int(settings.get("LED/Brightness", 255)) * 100 / 255)
            except (TypeError, ValueError):
                self._led_brightness = 100
            color = settings.get("LED/Color", "ffffff")
            self._led_color = f"#{color.lstrip('#')}"

            # 'ball' tracker params (read NVS names, written live via /sand_led).
            color2 = settings.get("LED/Color2", "000000")
            self._led_color2 = f"#{color2.lstrip('#')}"
            self._led_ball_fgbright = _clamp_int(settings.get("LED/BallBright"), 255, 0, 255)
            self._led_ball_bgbright = _clamp_int(settings.get("LED/BallBgBright"), 255, 0, 255)
            self._led_ball_size = _clamp_int(settings.get("LED/BallSize"), 3, 1, 200)
            self._led_ball_align = _clamp_int(settings.get("LED/Align"), 0, 0, 359)
            self._led_ball_bg = (settings.get("LED/BallBg") or "static").lower()
            direction = (settings.get("LED/Direction") or "cw").lower()
            self._led_ball_direction = direction if direction in ("cw", "ccw") else "cw"
            if effect != "ball":
                self._led_last_non_ball_effect = self._led_current_effect

        self.ledStatusChanged.emit()

    def _ingest_led_status(self, led):
        """Update live LED effect/brightness from a /sand_status snapshot."""
        changed = False
        effect = led.get("effect")
        if effect in LED_EFFECTS:
            idx = LED_EFFECTS.index(effect)
            if idx != self._led_current_effect:
                self._led_current_effect = idx
                changed = True
            power = (effect != "off")
            if power != self._led_power_on:
                self._led_power_on = power
                changed = True
            if power:
                self._led_last_effect = idx
            if effect not in ("ball", "off"):
                self._led_last_non_ball_effect = idx
        b = led.get("brightness")
        if b is not None:
            scaled = round(int(b) * 100 / 255)
            if scaled != self._led_brightness:
                self._led_brightness = scaled
                changed = True
        if changed:
            self.ledStatusChanged.emit()

    @Slot()
    def refreshLedStatus(self):
        logger.debug("Refreshing LED status...")
        _run(self._load_led_config())

    @Slot()
    def toggleLedPower(self):
        self.setLedPower(not self._led_power_on)

    @Slot(bool)
    def setLedPower(self, on):
        logger.debug(f"Setting LED power: {on}")
        if on:
            effect = LED_EFFECTS[self._led_last_effect] if self._led_last_effect else "rainbow"
            if effect == "off":
                effect = "rainbow"
            _run(self._apply_led(effect=effect))
            self._led_power_on = True
            self._led_current_effect = LED_EFFECTS.index(effect)
        else:
            if self._led_current_effect:
                self._led_last_effect = self._led_current_effect
            _run(self._apply_led(effect="off"))
            self._led_power_on = False
        self.ledStatusChanged.emit()

    async def _apply_led(self, **kwargs):
        try:
            await self.client.set_led(**kwargs)
        except Exception as exc:
            logger.error(f"LED update failed: {exc}")
            self.errorOccurred.emit("Couldn't update the light. " + friendly_error(exc))

    @Slot(int)
    def setLedBrightness(self, value):
        logger.debug(f"Setting LED brightness: {value}")
        value = max(0, min(100, value))
        self._led_brightness = value
        _run(self._apply_led(brightness=round(value * 255 / 100)))
        self.ledStatusChanged.emit()

    @Slot(int, int, int)
    def setLedColor(self, r, g, b):
        self.setLedColorHex(f"#{r:02x}{g:02x}{b:02x}")

    @Slot(str)
    def setLedColorHex(self, hexColor):
        hexColor = hexColor.lstrip('#')
        if len(hexColor) != 6:
            logger.warning(f"Invalid hex color: {hexColor}")
            return
        self._led_color = f"#{hexColor}"
        _run(self._apply_led(color=hexColor))
        self.ledStatusChanged.emit()

    @Slot(int)
    def setLedEffect(self, effectId):
        logger.debug(f"Setting LED effect: {effectId}")
        if 0 <= effectId < len(LED_EFFECTS):
            name = LED_EFFECTS[effectId]
            self._led_current_effect = effectId
            self._led_power_on = (name != "off")
            if self._led_power_on:
                self._led_last_effect = effectId
            if name not in ("ball", "off"):
                self._led_last_non_ball_effect = effectId
            _run(self._apply_led(effect=name))
            self.ledStatusChanged.emit()

    @Slot(int)
    def setLedPalette(self, paletteId):
        logger.debug(f"Setting LED palette: {paletteId}")
        if 0 <= paletteId < len(LED_PALETTES):
            self._led_current_palette = paletteId
            _run(self._apply_led(palette=LED_PALETTES[paletteId]))
            self.ledStatusChanged.emit()

    # -- 'ball' tracker control (firmware-native effect id 38) -------------
    BALL_EFFECT_ID = LED_EFFECTS.index("ball")

    @Slot(bool)
    def setBallTracker(self, on):
        """Enable/disable the ball tracker by toggling the 'ball' effect.
        Mirrors the mobile app's ball switch: remembers the previous non-ball
        effect and restores it when turned off."""
        if on:
            if self._led_current_effect != self.BALL_EFFECT_ID:
                self._led_last_non_ball_effect = self._led_current_effect
            self.setLedEffect(self.BALL_EFFECT_ID)
        else:
            restore = self._led_last_non_ball_effect or LED_EFFECTS.index("rainbow")
            self.setLedEffect(restore)

    @Slot(str)
    def setLedColor2Hex(self, hexColor):
        """Background colour for the ball tracker (used when bg == 'static')."""
        hexColor = hexColor.lstrip('#')
        if len(hexColor) != 6:
            logger.warning(f"Invalid hex color2: {hexColor}")
            return
        self._led_color2 = f"#{hexColor}"
        _run(self._apply_led(color2=hexColor))
        self.ledStatusChanged.emit()

    @Slot(int)
    def setLedBallFgBright(self, value):
        self._led_ball_fgbright = _clamp_int(value, 255, 0, 255)
        _run(self._apply_led(fgbright=self._led_ball_fgbright))
        self.ledStatusChanged.emit()

    @Slot(int)
    def setLedBallBgBright(self, value):
        self._led_ball_bgbright = _clamp_int(value, 255, 0, 255)
        _run(self._apply_led(bgbright=self._led_ball_bgbright))
        self.ledStatusChanged.emit()

    @Slot(int)
    def setLedBallSize(self, value):
        self._led_ball_size = _clamp_int(value, 3, 1, 200)
        _run(self._apply_led(size=self._led_ball_size))
        self.ledStatusChanged.emit()

    @Slot(int)
    def setLedBallAlign(self, value):
        self._led_ball_align = _clamp_int(value, 0, 0, 359)
        _run(self._apply_led(align=self._led_ball_align))
        self.ledStatusChanged.emit()

    @Slot(str)
    def setLedBallDirection(self, direction):
        if direction not in ("cw", "ccw"):
            return
        self._led_ball_direction = direction
        _run(self._apply_led(direction=direction))
        self.ledStatusChanged.emit()

    @Slot(str)
    def setLedBallBg(self, bg):
        if not bg:
            return
        self._led_ball_bg = str(bg)
        _run(self._apply_led(bg=self._led_ball_bg))
        self.ledStatusChanged.emit()

    # ==================== LCD brightness ====================
    def _detect_backlight(self):
        if not self._lcd_brightness_path:
            try:
                result = subprocess.run(['ls', '/sys/class/backlight'],
                                        capture_output=True, text=True, timeout=2)
                if result.returncode == 0 and result.stdout.strip():
                    device = result.stdout.strip().split('\n')[0]
                    self._lcd_brightness_path = f"/sys/class/backlight/{device}/brightness"
                    logger.info(f"Auto-detected backlight path: {self._lcd_brightness_path}")
                else:
                    logger.warning("No backlight device found")
                    return
            except Exception as e:
                logger.warning(f"Failed to detect backlight path: {e}")
                return

        backlight_dir = str(Path(self._lcd_brightness_path).parent)
        if self._lcd_max_brightness == 0:
            try:
                result = subprocess.run(['cat', f"{backlight_dir}/max_brightness"],
                                        capture_output=True, text=True, timeout=2)
                if result.returncode == 0 and result.stdout.strip():
                    self._lcd_max_brightness = int(result.stdout.strip())
                else:
                    self._lcd_max_brightness = 255
            except Exception:
                self._lcd_max_brightness = 255

        try:
            result = subprocess.run(['cat', self._lcd_brightness_path],
                                    capture_output=True, text=True, timeout=2)
            if result.returncode == 0 and result.stdout.strip():
                self._lcd_brightness = int(result.stdout.strip())
        except Exception as e:
            logger.warning(f"Failed to read current brightness: {e}")

    @Property(int, notify=lcdBrightnessChanged)
    def lcdBrightness(self):
        return self._lcd_brightness

    @Property(int, notify=lcdBrightnessChanged)
    def lcdMaxBrightness(self):
        return self._lcd_max_brightness

    @Slot(int)
    def setLcdBrightness(self, value):
        value = max(0, min(value, self._lcd_max_brightness))
        if not self._lcd_brightness_path:
            logger.warning("No backlight path configured")
            return
        try:
            subprocess.run(['sudo', 'sh', '-c', f'echo {value} > {self._lcd_brightness_path}'],
                           check=False, timeout=5)
            self._lcd_brightness = value
            self._save_local_settings()
            self.lcdBrightnessChanged.emit()
        except Exception as e:
            logger.error(f"Failed to set LCD brightness: {e}")

    # ==================== Pattern refresh ====================
    @Slot()
    def refreshPatterns(self):
        """Re-fetch the pattern catalogue from the table (models reload)."""
        logger.debug("Refreshing patterns...")
        # onPatternsRefreshCompleted in QML triggers patternModel.refresh().
        self.patternsRefreshCompleted.emit(True, "Patterns refreshed")

    # ==================== System control ====================
    @Slot()
    def restartBackend(self):
        """Reboot the table controller (closest analog to the old backend restart)."""
        logger.info("Rebooting the table...")
        _run(self._simple_action(self.client.reboot, label="reboot table"))

    @Slot()
    def shutdownPi(self):
        """Shut down the local touch host (Raspberry Pi)."""
        logger.info("Shutting down the Pi...")
        try:
            subprocess.run(['sudo', 'shutdown', '-h', 'now'], check=False, timeout=5)
        except Exception as e:
            logger.error(f"Shutdown failed: {e}")
            self.errorOccurred.emit("Couldn't shut down the Pi. " + friendly_error(e))

    # ==================== Playlist management ====================
    @Slot(str)
    def createPlaylist(self, playlistName):
        logger.debug(f"Creating playlist: {playlistName}")
        _run(self._create_playlist(playlistName))

    async def _create_playlist(self, name):
        try:
            content = f"# {name}\n".encode("utf-8")
            await self.client.upload_file(f"{name}.txt", content, path="/playlists")
            self.playlistCreated.emit(True, f"Created: {name}")
        except Exception as exc:
            logger.error(f"create playlist failed: {exc}")
            self.playlistCreated.emit(False, f"Failed: {exc}")

    @Slot(str)
    def deletePlaylist(self, playlistName):
        logger.info(f"Deleting playlist: {playlistName}")
        _run(self._delete_playlist(playlistName))

    async def _delete_playlist(self, name):
        try:
            await self.client.delete_file(f"{name}.txt", path="/playlists")
            self.playlistDeleted.emit(True, f"Deleted: {name}")
        except Exception as exc:
            logger.error(f"delete playlist failed: {exc}")
            self.playlistDeleted.emit(False, f"Failed: {exc}")

    @Slot(str, str)
    def addPatternToPlaylist(self, playlistName, patternPath):
        logger.info(f"Adding pattern to playlist: {patternPath} -> {playlistName}")
        _run(self._add_pattern_to_playlist(playlistName, patternPath))

    async def _add_pattern_to_playlist(self, name, patternPath):
        try:
            # Fetch current contents, append the SD path, re-upload.
            try:
                raw = await self.client.fetch_sd_file(f"/playlists/{name}.txt")
                lines = raw.decode("utf-8", errors="ignore").splitlines()
            except Exception:
                lines = [f"# {name}"]
            sd_path = self._to_sd_pattern_path(patternPath)
            lines.append(sd_path)
            content = ("\n".join(lines) + "\n").encode("utf-8")
            await self.client.upload_file(f"{name}.txt", content, path="/playlists")
            self.patternAddedToPlaylist.emit(True, f"Added to {name}")
        except Exception as exc:
            logger.error(f"add pattern failed: {exc}")
            self.patternAddedToPlaylist.emit(False, f"Failed: {exc}")

    @Slot(str, list)
    def updatePlaylistPatterns(self, playlistName, patterns):
        logger.debug(f"Updating playlist {playlistName} -> {len(patterns)} patterns")
        _run(self._update_playlist_patterns(playlistName, patterns))

    async def _update_playlist_patterns(self, name, patterns):
        try:
            lines = [f"# {name}"]
            lines += [self._to_sd_pattern_path(p) for p in patterns]
            content = ("\n".join(lines) + "\n").encode("utf-8")
            await self.client.upload_file(f"{name}.txt", content, path="/playlists")
            self.playlistModified.emit(True, f"Updated: {name}")
        except Exception as exc:
            logger.error(f"update playlist failed: {exc}")
            self.playlistModified.emit(False, f"Failed: {exc}")

    @staticmethod
    def _to_sd_pattern_path(pattern):
        """Normalize a pattern reference to an SD-absolute /patterns path."""
        p = str(pattern).strip()
        if p.startswith("/patterns/") or p.startswith("/sd/"):
            return p.replace("/sd/", "/", 1) if p.startswith("/sd/") else p
        return "/patterns/" + p.lstrip("/")

    @Slot(result=list)
    def getPlaylistNames(self):
        """Synchronous accessor kept for QML compatibility (best-effort)."""
        # Playlists now live on the table; the PlaylistModel is the source of
        # truth. This returns an empty list rather than reading a local file.
        return []
