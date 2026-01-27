from PySide6.QtCore import QObject, Signal, Property, Slot, QTimer
from PySide6.QtQml import QmlElement
from PySide6.QtWebSockets import QWebSocket
from PySide6.QtNetwork import QAbstractSocket
import aiohttp
import asyncio
import json
import logging
import subprocess
import threading
import time
from pathlib import Path
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("DuneWeaver")

QML_IMPORT_NAME = "DuneWeaver"
QML_IMPORT_MAJOR_VERSION = 1

@QmlElement
class Backend(QObject):
    """Backend controller for API and WebSocket communication"""
    
    # Constants
    SETTINGS_FILE = "touch_settings.json"
    DEFAULT_SCREEN_TIMEOUT = 300  # 5 minutes in seconds
    
    # Predefined timeout options (in seconds)
    TIMEOUT_OPTIONS = {
        "30 seconds": 30,
        "1 minute": 60, 
        "5 minutes": 300,
        "10 minutes": 600,
        "Never": 0  # 0 means never timeout
    }
    
    # Predefined speed options
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
        "0s": 0,        # No pause
        "1 min": 60,    # 1 minute
        "5 min": 300,   # 5 minutes
        "15 min": 900,  # 15 minutes
        "30 min": 1800, # 30 minutes
        "1 hour": 3600, # 1 hour
        "2 hour": 7200, # 2 hours
        "3 hour": 10800, # 3 hours
        "4 hour": 14400, # 4 hours
        "5 hour": 18000, # 5 hours
        "6 hour": 21600, # 6 hours
        "12 hour": 43200 # 12 hours
    }
    
    # Signals
    statusChanged = Signal()
    progressChanged = Signal()
    connectionChanged = Signal()
    executionStarted = Signal(str, str)  # patternName, patternPreview
    executionStopped = Signal()
    errorOccurred = Signal(str)
    serialPortsUpdated = Signal(list)
    serialConnectionChanged = Signal(bool)
    currentPortChanged = Signal(str)
    speedChanged = Signal(int)
    settingsLoaded = Signal()
    screenStateChanged = Signal(bool)  # True = on, False = off
    screenTimeoutChanged = Signal(int)  # New signal for timeout changes
    pauseBetweenPatternsChanged = Signal(int)  # New signal for pause changes
    pausedChanged = Signal(bool)  # Signal when pause state changes
    playlistSettingsChanged = Signal()  # Signal when any playlist setting changes
    patternsRefreshCompleted = Signal(bool, str)  # (success, message) for pattern refresh

    # Playlist management signals
    playlistCreated = Signal(bool, str)      # (success, message)
    playlistDeleted = Signal(bool, str)      # (success, message)
    patternAddedToPlaylist = Signal(bool, str)  # (success, message)
    playlistModified = Signal(bool, str)     # (success, message)

    # Backend connection status signals
    backendConnectionChanged = Signal(bool)  # True = backend reachable, False = unreachable
    reconnectStatusChanged = Signal(str)  # Current reconnection status message

    # LED control signals
    ledStatusChanged = Signal()
    ledEffectsLoaded = Signal(list)  # List of available effects
    ledPalettesLoaded = Signal(list)  # List of available palettes
    
    def __init__(self):
        super().__init__()
        # Load base URL from environment variable, default to localhost
        self.base_url = os.environ.get("DUNE_WEAVER_URL", "http://localhost:8080")
        
        # Initialize all status properties first
        self._current_file = ""
        self._progress = 0
        self._is_running = False
        self._is_paused = False  # Track pause state separately
        self._is_connected = False
        self._serial_ports = []
        self._serial_connected = False
        self._current_port = ""
        self._current_speed = 130
        self._auto_play_on_boot = False
        self._pause_between_patterns = 10800  # Default: 3 hours (10800 seconds)

        # Playlist settings (persisted locally)
        self._playlist_shuffle = True  # Default: shuffle on
        self._playlist_run_mode = "loop"  # Default: loop mode
        self._playlist_clear_pattern = "adaptive"  # Default: adaptive
        
        # Backend connection status
        self._backend_connected = False
        self._reconnect_status = "Connecting to backend..."

        # LED control state
        self._led_provider = "none"  # "none", "wled", or "dw_leds"
        self._led_connected = False
        self._led_power_on = False
        self._led_brightness = 100
        self._led_effects = []
        self._led_palettes = []
        self._led_current_effect = 0
        self._led_current_palette = 0
        self._led_color = "#ffffff"
        
        # WebSocket for status with reconnection
        self.ws = QWebSocket()
        self.ws.connected.connect(self._on_ws_connected)
        self.ws.disconnected.connect(self._on_ws_disconnected)
        self.ws.errorOccurred.connect(self._on_ws_error)
        self.ws.textMessageReceived.connect(self._on_ws_message)
        
        # WebSocket reconnection management
        self._reconnect_timer = QTimer()
        self._reconnect_timer.timeout.connect(self._attempt_ws_reconnect)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_attempts = 0
        self._reconnect_delay = 1000  # Fixed 1 second delay between retries
        
        # Screen management
        self._screen_on = True
        self._screen_timeout = self.DEFAULT_SCREEN_TIMEOUT  # Will be loaded from settings
        self._last_activity = time.time()
        self._screen_transition_lock = threading.Lock()  # Prevent rapid state changes
        self._last_screen_change = 0  # Track last state change time
        self._screen_timer = QTimer()
        self._screen_timer.timeout.connect(self._check_screen_timeout)
        self._screen_timer.start(1000)  # Check every second
        # Load local settings first
        self._load_local_settings()
        logger.debug(f"Screen management initialized: timeout={self._screen_timeout}s, timer started")
        
        # HTTP session - initialize lazily
        self.session = None
        self._session_initialized = False
        
        # Use QTimer to defer session initialization until event loop is running
        QTimer.singleShot(100, self._delayed_init)
        
        # Start initial WebSocket connection (after all attributes are initialized)
        # Use QTimer to ensure it happens after constructor completes
        QTimer.singleShot(200, self._attempt_ws_reconnect)
    
    @Slot()
    def _delayed_init(self):
        """Initialize session after Qt event loop is running"""
        if not self._session_initialized:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._init_session())
                else:
                    # If no loop is running, try again later
                    QTimer.singleShot(500, self._delayed_init)
            except RuntimeError:
                # No event loop yet, try again
                QTimer.singleShot(500, self._delayed_init)
    
    async def _init_session(self):
        """Initialize aiohttp session"""
        if not self._session_initialized:
            # Create connector with SSL disabled for localhost
            connector = aiohttp.TCPConnector(ssl=False)
            self.session = aiohttp.ClientSession(connector=connector)
            self._session_initialized = True
    
    # Properties
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
    
    # WebSocket handlers
    @Slot()
    def _on_ws_connected(self):
        logger.info("WebSocket connected successfully")
        self._is_connected = True
        self._backend_connected = True
        self._reconnect_attempts = 0  # Reset reconnection counter
        self._reconnect_status = "Connected to backend"
        self.connectionChanged.emit()
        self.backendConnectionChanged.emit(True)
        self.reconnectStatusChanged.emit("Connected to backend")

        # Load initial settings when we connect
        self.loadControlSettings()
        # Also load LED config automatically
        self.loadLedConfig()
    
    @Slot()
    def _on_ws_disconnected(self):
        logger.error("WebSocket disconnected")
        self._is_connected = False
        self._backend_connected = False
        self._reconnect_status = "Backend connection lost..."
        self.connectionChanged.emit()
        self.backendConnectionChanged.emit(False)
        self.reconnectStatusChanged.emit("Backend connection lost...")
        # Start reconnection attempts
        self._schedule_reconnect()
    
    @Slot()
    def _on_ws_error(self, error):
        logger.error(f"WebSocket error: {error}")
        self._is_connected = False
        self._backend_connected = False
        self._reconnect_status = f"Backend error: {error}"
        self.connectionChanged.emit()
        self.backendConnectionChanged.emit(False)
        self.reconnectStatusChanged.emit(f"Backend error: {error}")
        # Start reconnection attempts
        self._schedule_reconnect()
    
    def _schedule_reconnect(self):
        """Schedule a reconnection attempt with fixed 1-second delay."""
        # Always retry - no maximum attempts for touch interface
        status_msg = f"Reconnecting in 1s... (attempt {self._reconnect_attempts + 1})"
        logger.debug(f"{status_msg}")
        self._reconnect_status = status_msg
        self.reconnectStatusChanged.emit(status_msg)
        self._reconnect_timer.start(self._reconnect_delay)  # Always 1 second
    
    @Slot()
    def _attempt_ws_reconnect(self):
        """Attempt to reconnect WebSocket."""
        if self.ws.state() == QAbstractSocket.SocketState.ConnectedState:
            logger.info("WebSocket already connected")
            return
            
        self._reconnect_attempts += 1
        status_msg = f"Connecting to backend... (attempt {self._reconnect_attempts})"
        logger.debug(f"{status_msg}")
        self._reconnect_status = status_msg
        self.reconnectStatusChanged.emit(status_msg)
        
        # Close existing connection if any
        if self.ws.state() != QAbstractSocket.SocketState.UnconnectedState:
            self.ws.close()
        
        # Attempt new connection - derive WebSocket URL from base URL
        ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws/status"
        self.ws.open(ws_url)
    
    @Slot()
    def retryConnection(self):
        """Manually retry connection (reset attempts and try again)."""
        logger.debug("Manual connection retry requested")
        self._reconnect_attempts = 0
        self._reconnect_timer.stop()  # Stop any scheduled reconnect
        self._attempt_ws_reconnect()
    
    @Slot(str)
    def _on_ws_message(self, message):
        try:
            data = json.loads(message)
            if data.get("type") == "status_update":
                status = data.get("data", {})
                new_file = status.get("current_file", "")

                # Detect pattern change and emit executionStarted signal
                if new_file and new_file != self._current_file:
                    logger.info(f"Pattern changed from '{self._current_file}' to '{new_file}'")
                    # Find preview for the new pattern
                    preview_path = self._find_pattern_preview(new_file)
                    logger.debug(f"Preview path for new pattern: {preview_path}")
                    # Emit signal so UI can update
                    self.executionStarted.emit(new_file, preview_path)

                self._current_file = new_file
                self._is_running = status.get("is_running", False)

                # Handle pause state from WebSocket
                new_paused = status.get("is_paused", False)
                if new_paused != self._is_paused:
                    logger.info(f"Pause state changed: {self._is_paused} -> {new_paused}")
                    self._is_paused = new_paused
                    self.pausedChanged.emit(new_paused)

                # Handle serial connection status from WebSocket
                ws_connection_status = status.get("connection_status", False)
                if ws_connection_status != self._serial_connected:
                    logger.info(f"WebSocket serial connection status changed: {ws_connection_status}")
                    self._serial_connected = ws_connection_status
                    self.serialConnectionChanged.emit(ws_connection_status)

                    # If we're connected, we need to get the current port
                    if ws_connection_status:
                        # We'll need to fetch the current port via HTTP since WS doesn't include port info
                        asyncio.create_task(self._get_current_port())
                    else:
                        self._current_port = ""
                        self.currentPortChanged.emit("")

                # Handle speed updates from WebSocket
                ws_speed = status.get("speed", None)
                if ws_speed and ws_speed != self._current_speed:
                    logger.debug(f"WebSocket speed changed: {ws_speed}")
                    self._current_speed = ws_speed
                    self.speedChanged.emit(ws_speed)

                if status.get("progress"):
                    self._progress = status["progress"].get("percentage", 0)

                self.statusChanged.emit()
                self.progressChanged.emit()
        except json.JSONDecodeError:
            pass
    
    async def _get_current_port(self):
        """Fetch the current port when we detect a connection via WebSocket"""
        if not self.session:
            return
        
        try:
            async with self.session.get(f"{self.base_url}/serial_status") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    current_port = data.get("port", "")
                    if current_port:
                        self._current_port = current_port
                        self.currentPortChanged.emit(current_port)
                        logger.info(f"Updated current port from WebSocket trigger: {current_port}")
        except Exception as e:
            logger.error(f"Exception getting current port: {e}")
    
    # API Methods
    @Slot(str, str)
    def executePattern(self, fileName, preExecution="adaptive"):
        logger.info(f"ExecutePattern called: fileName='{fileName}', preExecution='{preExecution}'")
        asyncio.create_task(self._execute_pattern(fileName, preExecution))
    
    async def _execute_pattern(self, fileName, preExecution):
        if not self.session:
            logger.error("Backend session not ready")
            self.errorOccurred.emit("Backend not ready, please try again")
            return
        
        try:
            request_data = {"file_name": fileName, "pre_execution": preExecution}
            logger.debug(f"Making HTTP POST to: {self.base_url}/run_theta_rho")
            logger.debug(f"Request payload: {request_data}")
            
            async with self.session.post(
                f"{self.base_url}/run_theta_rho",
                json=request_data
            ) as resp:
                logger.debug(f"Response status: {resp.status}")
                logger.debug(f"Response headers: {dict(resp.headers)}")
                
                response_text = await resp.text()
                logger.debug(f"Response body: {response_text}")
                
                if resp.status == 200:
                    logger.info("Pattern execution request successful")
                    # Find preview image for the pattern
                    preview_path = self._find_pattern_preview(fileName)
                    logger.debug(f"Pattern preview path: {preview_path}")
                    logger.debug(f"About to emit executionStarted signal with: fileName='{fileName}', preview='{preview_path}'")
                    try:
                        self.executionStarted.emit(fileName, preview_path)
                        logger.info("ExecutionStarted signal emitted successfully")
                    except Exception as e:
                        logger.error(f"Error emitting executionStarted signal: {e}")
                else:
                    logger.error(f"Pattern execution failed with status {resp.status}")
                    self.errorOccurred.emit(f"Failed to execute: {resp.status} - {response_text}")
        except Exception as e:
            logger.error(f"Exception in _execute_pattern: {e}")
            self.errorOccurred.emit(str(e))
    
    def _find_pattern_preview(self, fileName):
        """Find the preview image for a pattern"""
        try:
            # Extract just the filename from the path (remove any directory prefixes)
            clean_filename = fileName.split('/')[-1]  # Get last part of path
            logger.debug(f"Original fileName: {fileName}, clean filename: {clean_filename}")

            # Check multiple possible locations for patterns directory
            # Use relative paths that work across different environments
            possible_dirs = [
                Path("../patterns"),  # One level up (for when running from touch subdirectory)
                Path("patterns"),     # Same level (for when running from main directory)
                Path(__file__).parent.parent / "patterns"  # Dynamic path relative to backend.py
            ]

            for patterns_dir in possible_dirs:
                cache_dir = patterns_dir / "cached_images"
                if cache_dir.exists():
                    logger.debug(f"Searching for preview in cache directory: {cache_dir}")

                    # Extensions to try - PNG first for better kiosk compatibility
                    extensions = [".png", ".webp", ".jpg", ".jpeg"]

                    # Filenames to try - with and without .thr suffix
                    base_name = clean_filename.replace(".thr", "")
                    filenames_to_try = [clean_filename, base_name]

                    # Try direct path in cache_dir first (fastest)
                    for filename in filenames_to_try:
                        for ext in extensions:
                            preview_file = cache_dir / (filename + ext)
                            if preview_file.exists():
                                logger.info(f"Found preview (direct): {preview_file}")
                                return str(preview_file.absolute())

                    # If not found directly, search recursively through subdirectories
                    logger.debug(f"Searching recursively in {cache_dir}...")
                    for filename in filenames_to_try:
                        for ext in extensions:
                            target_name = filename + ext
                            # Use rglob to search recursively
                            matches = list(cache_dir.rglob(target_name))
                            if matches:
                                # Return the first match found
                                preview_file = matches[0]
                                logger.info(f"Found preview (recursive): {preview_file}")
                                return str(preview_file.absolute())

            logger.error("No preview image found")
            return ""
        except Exception as e:
            logger.error(f"Exception finding preview: {e}")
            return ""
    
    @Slot()
    def stopExecution(self):
        asyncio.create_task(self._stop_execution())
    
    async def _stop_execution(self):
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return
        
        try:
            logger.info("Calling stop_execution endpoint...")
            # Backend stop_actions() waits up to 10s for pattern lock + 30s for idle check
            # Use 45s timeout to accommodate worst-case scenario
            timeout = aiohttp.ClientTimeout(total=45)
            async with self.session.post(f"{self.base_url}/stop_execution", timeout=timeout) as resp:
                logger.info(f"Stop execution response status: {resp.status}")
                if resp.status == 200:
                    response_data = await resp.json()
                    logger.info(f"Stop execution response: {response_data}")
                    self.executionStopped.emit()
                else:
                    logger.error(f"Stop execution failed with status: {resp.status}")
                    response_text = await resp.text()
                    self.errorOccurred.emit(f"Stop failed: {resp.status} - {response_text}")
        except asyncio.TimeoutError:
            logger.warning("Stop execution request timed out")
            self.errorOccurred.emit("Stop execution request timed out")
        except Exception as e:
            logger.error(f"Exception in _stop_execution: {e}")
            self.errorOccurred.emit(str(e))
    
    @Slot()
    def pauseExecution(self):
        logger.info("Pausing execution...")
        asyncio.create_task(self._api_call("/pause_execution"))
    
    @Slot()
    def resumeExecution(self):
        logger.info("Resuming execution...")
        asyncio.create_task(self._api_call("/resume_execution"))
    
    @Slot()
    def skipPattern(self):
        logger.info("Skipping pattern...")
        asyncio.create_task(self._api_call("/skip_pattern"))
    
    @Slot(str, float, str, str, bool)
    def executePlaylist(self, playlistName, pauseTime=0.0, clearPattern="adaptive", runMode="single", shuffle=False):
        logger.info(f"ExecutePlaylist called: playlist='{playlistName}', pauseTime={pauseTime}, clearPattern='{clearPattern}', runMode='{runMode}', shuffle={shuffle}")
        asyncio.create_task(self._execute_playlist(playlistName, pauseTime, clearPattern, runMode, shuffle))
    
    async def _execute_playlist(self, playlistName, pauseTime, clearPattern, runMode, shuffle):
        if not self.session:
            logger.error("Backend session not ready")
            self.errorOccurred.emit("Backend not ready, please try again")
            return
        
        try:
            request_data = {
                "playlist_name": playlistName,
                "pause_time": pauseTime,
                "clear_pattern": clearPattern,
                "run_mode": runMode,
                "shuffle": shuffle
            }
            logger.debug(f"Making HTTP POST to: {self.base_url}/run_playlist")
            logger.debug(f"Request payload: {request_data}")
            
            async with self.session.post(
                f"{self.base_url}/run_playlist",
                json=request_data
            ) as resp:
                logger.debug(f"Response status: {resp.status}")
                
                response_text = await resp.text()
                logger.debug(f"Response body: {response_text}")
                
                if resp.status == 200:
                    logger.info(f"Playlist execution request successful: {playlistName}")
                    # The playlist will start executing patterns automatically
                    # Status updates will come through WebSocket
                else:
                    logger.error(f"Playlist execution failed with status {resp.status}")
                    self.errorOccurred.emit(f"Failed to execute playlist: {resp.status} - {response_text}")
        except Exception as e:
            logger.error(f"Exception in _execute_playlist: {e}")
            self.errorOccurred.emit(str(e))
    
    async def _api_call(self, endpoint):
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return
        
        try:
            logger.debug(f"Calling API endpoint: {endpoint}")
            # Add timeout to prevent hanging
            timeout = aiohttp.ClientTimeout(total=10)  # 10 second timeout
            async with self.session.post(f"{self.base_url}{endpoint}", timeout=timeout) as resp:
                logger.debug(f"API response status for {endpoint}: {resp.status}")
                if resp.status == 200:
                    response_data = await resp.json()
                    logger.debug(f"API response for {endpoint}: {response_data}")
                else:
                    logger.error(f"API call {endpoint} failed with status: {resp.status}")
                    response_text = await resp.text()
                    self.errorOccurred.emit(f"API call failed: {endpoint} - {resp.status} - {response_text}")
        except asyncio.TimeoutError:
            logger.warning(f"API call {endpoint} timed out")
            self.errorOccurred.emit(f"API call {endpoint} timed out")
        except Exception as e:
            logger.error(f"Exception in API call {endpoint}: {e}")
            self.errorOccurred.emit(str(e))
    
    # Serial Port Management
    @Slot()
    def refreshSerialPorts(self):
        logger.info("Refreshing serial ports...")
        asyncio.create_task(self._refresh_serial_ports())
    
    async def _refresh_serial_ports(self):
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return
        
        try:
            async with self.session.get(f"{self.base_url}/list_serial_ports") as resp:
                if resp.status == 200:
                    # The endpoint returns a list directly, not a dictionary
                    ports = await resp.json()
                    self._serial_ports = ports if isinstance(ports, list) else []
                    logger.debug(f"Found serial ports: {self._serial_ports}")
                    self.serialPortsUpdated.emit(self._serial_ports)
                else:
                    logger.error(f"Failed to get serial ports: {resp.status}")
        except Exception as e:
            logger.error(f"Exception refreshing serial ports: {e}")
            self.errorOccurred.emit(str(e))
    
    @Slot(str)
    def connectSerial(self, port):
        logger.info(f"Connecting to serial port: {port}")
        asyncio.create_task(self._connect_serial(port))
    
    async def _connect_serial(self, port):
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return
        
        try:
            async with self.session.post(f"{self.base_url}/connect", json={"port": port}) as resp:
                if resp.status == 200:
                    logger.info(f"Connected to {port}")
                    self._serial_connected = True
                    self._current_port = port
                    self.serialConnectionChanged.emit(True)
                    self.currentPortChanged.emit(port)
                else:
                    response_text = await resp.text()
                    logger.error(f"Failed to connect to {port}: {resp.status} - {response_text}")
                    self.errorOccurred.emit(f"Failed to connect: {response_text}")
        except Exception as e:
            logger.error(f"Exception connecting to serial: {e}")
            self.errorOccurred.emit(str(e))
    
    @Slot()
    def disconnectSerial(self):
        logger.info("Disconnecting serial...")
        asyncio.create_task(self._disconnect_serial())
    
    async def _disconnect_serial(self):
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return
        
        try:
            async with self.session.post(f"{self.base_url}/disconnect") as resp:
                if resp.status == 200:
                    logger.info("Disconnected from serial")
                    self._serial_connected = False
                    self._current_port = ""
                    self.serialConnectionChanged.emit(False)
                    self.currentPortChanged.emit("")
                else:
                    response_text = await resp.text()
                    logger.error(f"Failed to disconnect: {resp.status} - {response_text}")
        except Exception as e:
            logger.error(f"Exception disconnecting serial: {e}")
            self.errorOccurred.emit(str(e))
    
    # Hardware Movement Controls
    @Slot()
    def sendHome(self):
        logger.debug("Sending home command...")
        asyncio.create_task(self._send_home())

    async def _send_home(self):
        """Send home command without timeout - homing can take up to 90 seconds."""
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return

        try:
            logger.debug("Calling /send_home (no timeout - homing can take up to 90s)...")
            async with self.session.post(f"{self.base_url}/send_home") as resp:
                logger.debug(f"Home command response status: {resp.status}")
                if resp.status == 200:
                    response_data = await resp.json()
                    logger.info(f"Home command successful: {response_data}")
                else:
                    logger.error(f"Home command failed with status: {resp.status}")
                    response_text = await resp.text()
                    self.errorOccurred.emit(f"Home failed: {resp.status} - {response_text}")
        except Exception as e:
            logger.error(f"Exception in home command: {e}")
            self.errorOccurred.emit(str(e))
    
    @Slot()
    def moveToCenter(self):
        logger.info("Moving to center...")
        asyncio.create_task(self._api_call("/move_to_center"))
    
    @Slot()
    def moveToPerimeter(self):
        logger.info("Moving to perimeter...")
        asyncio.create_task(self._api_call("/move_to_perimeter"))
    
    # Speed Control
    @Slot(int)
    def setSpeed(self, speed):
        logger.debug(f"Setting speed to: {speed}")
        asyncio.create_task(self._set_speed(speed))
    
    async def _set_speed(self, speed):
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return
        
        try:
            async with self.session.post(f"{self.base_url}/set_speed", json={"speed": speed}) as resp:
                if resp.status == 200:
                    logger.info(f"Speed set to {speed}")
                    self._current_speed = speed
                    self.speedChanged.emit(speed)
                else:
                    response_text = await resp.text()
                    logger.error(f"Failed to set speed: {resp.status} - {response_text}")
        except Exception as e:
            logger.error(f"Exception setting speed: {e}")
            self.errorOccurred.emit(str(e))
    
    # Auto Play on Boot Setting
    @Slot(bool)
    def setAutoPlayOnBoot(self, enabled):
        logger.info(f"Setting auto play on boot: {enabled}")
        asyncio.create_task(self._set_auto_play_on_boot(enabled))
    
    async def _set_auto_play_on_boot(self, enabled):
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return
        
        try:
            # Use the kiosk mode API endpoint for auto-play on boot
            async with self.session.post(f"{self.base_url}/api/kiosk-mode", json={"enabled": enabled}) as resp:
                if resp.status == 200:
                    logger.info(f"Auto play on boot set to {enabled}")
                    self._auto_play_on_boot = enabled
                else:
                    response_text = await resp.text()
                    logger.error(f"Failed to set auto play: {resp.status} - {response_text}")
        except Exception as e:
            logger.error(f"Exception setting auto play: {e}")
            self.errorOccurred.emit(str(e))
    
    # Note: Screen timeout is now managed locally in touch_settings.json
    # The main application doesn't have a kiosk-mode endpoint, so we manage this locally
    
    # Load Settings
    def _load_local_settings(self):
        """Load settings from local JSON file"""
        try:
            if os.path.exists(self.SETTINGS_FILE):
                with open(self.SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)

                screen_timeout = settings.get('screen_timeout', self.DEFAULT_SCREEN_TIMEOUT)
                if isinstance(screen_timeout, (int, float)) and screen_timeout >= 0:
                    self._screen_timeout = int(screen_timeout)
                    if screen_timeout == 0:
                        logger.debug(f"Loaded screen timeout from local settings: Never (0s)")
                    else:
                        logger.debug(f"Loaded screen timeout from local settings: {self._screen_timeout}s")
                else:
                    logger.warning(f"Invalid screen timeout in settings, using default: {self.DEFAULT_SCREEN_TIMEOUT}s")

                # Load playlist settings
                self._pause_between_patterns = settings.get('pause_between_patterns', 10800)  # Default 3h
                self._playlist_shuffle = settings.get('playlist_shuffle', True)
                self._playlist_run_mode = settings.get('playlist_run_mode', "loop")
                self._playlist_clear_pattern = settings.get('playlist_clear_pattern', "adaptive")
                logger.info(f"Loaded playlist settings: pause={self._pause_between_patterns}s, shuffle={self._playlist_shuffle}, mode={self._playlist_run_mode}, clear={self._playlist_clear_pattern}")
            else:
                logger.debug(f"No local settings file found, creating with defaults")
                self._save_local_settings()
        except Exception as e:
            logger.error(f"Error loading local settings: {e}, using defaults")
            self._screen_timeout = self.DEFAULT_SCREEN_TIMEOUT

    def _save_local_settings(self):
        """Save settings to local JSON file"""
        try:
            settings = {
                'screen_timeout': self._screen_timeout,
                'pause_between_patterns': self._pause_between_patterns,
                'playlist_shuffle': self._playlist_shuffle,
                'playlist_run_mode': self._playlist_run_mode,
                'playlist_clear_pattern': self._playlist_clear_pattern,
                'version': '1.1'
            }
            with open(self.SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=2)
            logger.debug(f"Saved local settings: screen_timeout={self._screen_timeout}s, playlist settings saved")
        except Exception as e:
            logger.error(f"Error saving local settings: {e}")

    @Slot()
    def loadControlSettings(self):
        logger.debug("Loading control settings...")
        asyncio.create_task(self._load_settings())
    
    async def _load_settings(self):
        if not self.session:
            logger.warning("Session not ready for loading settings")
            return
        
        try:
            # Load auto play setting from the working endpoint
            timeout = aiohttp.ClientTimeout(total=5)  # 5 second timeout
            async with self.session.get(f"{self.base_url}/api/auto_play-mode", timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._auto_play_on_boot = data.get("enabled", False)
                    logger.info(f"Loaded auto play setting: {self._auto_play_on_boot}")
                # Note: Screen timeout is managed locally, not from server
            
            # Serial status will be handled by WebSocket updates automatically
            # But we still load the initial port info if connected
            async with self.session.get(f"{self.base_url}/serial_status", timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    initial_connected = data.get("connected", False)
                    current_port = data.get("port", "")
                    logger.info(f"Initial serial status: connected={initial_connected}, port={current_port}")
                    
                    # Only update if WebSocket hasn't already set this
                    if initial_connected and current_port and not self._current_port:
                        self._current_port = current_port
                        self.currentPortChanged.emit(current_port)
                    
                    # Set initial connection status (WebSocket will take over from here)
                    if self._serial_connected != initial_connected:
                        self._serial_connected = initial_connected
                        self.serialConnectionChanged.emit(initial_connected)
            
            logger.info("Settings loaded - WebSocket will handle real-time updates")
            self.settingsLoaded.emit()
            
        except aiohttp.ClientConnectorError as e:
            logger.warning(f"Cannot connect to backend at {self.base_url}: {e}")
            # Don't emit error - this is expected when backend is down
            # WebSocket will handle reconnection
        except asyncio.TimeoutError:
            logger.warning(f"Timeout loading settings from {self.base_url}")
            # Don't emit error - expected when backend is slow/down
        except Exception as e:
            logger.error(f"Unexpected error loading settings: {e}")
            # Only emit error for unexpected issues
            if "ssl" not in str(e).lower():
                self.errorOccurred.emit(str(e))
    
    # Screen Management Properties
    @Property(bool, notify=screenStateChanged)
    def screenOn(self):
        return self._screen_on
    
    @Property(int, notify=screenTimeoutChanged)
    def screenTimeout(self):
        return self._screen_timeout
    
    @screenTimeout.setter
    def setScreenTimeout(self, timeout):
        if self._screen_timeout != timeout:
            old_timeout = self._screen_timeout
            self._screen_timeout = timeout
            logger.debug(f"Screen timeout changed from {old_timeout}s to {timeout}s")
            
            # Save to local settings
            self._save_local_settings()
            
            # Emit change signal for QML
            self.screenTimeoutChanged.emit(timeout)
    
    @Slot(result='QStringList')
    def getScreenTimeoutOptions(self):
        """Get list of screen timeout options for QML"""
        return list(self.TIMEOUT_OPTIONS.keys())
    
    @Slot(result=str)
    def getCurrentScreenTimeoutOption(self):
        """Get current screen timeout as option string"""
        current_timeout = self._screen_timeout
        for option, value in self.TIMEOUT_OPTIONS.items():
            if value == current_timeout:
                return option
        # If custom value, return closest match or custom description
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
        """Set screen timeout by option string"""
        if option in self.TIMEOUT_OPTIONS:
            timeout_value = self.TIMEOUT_OPTIONS[option]
            # Don't call the setter method, just assign to trigger the property setter
            if self._screen_timeout != timeout_value:
                old_timeout = self._screen_timeout
                self._screen_timeout = timeout_value
                logger.debug(f"Screen timeout changed from {old_timeout}s to {timeout_value}s ({option})")
                
                # Save to local settings
                self._save_local_settings()
                
                # Emit change signal for QML
                self.screenTimeoutChanged.emit(timeout_value)
        else:
            logger.warning(f"Unknown timeout option: {option}")
    
    @Slot(result='QStringList')
    def getSpeedOptions(self):
        """Get list of speed options for QML"""
        return list(self.SPEED_OPTIONS.keys())
    
    @Slot(result=str)
    def getCurrentSpeedOption(self):
        """Get current speed as option string"""
        current_speed = self._current_speed
        for option, value in self.SPEED_OPTIONS.items():
            if value == current_speed:
                return option
        # If custom value, return as string
        return str(current_speed)
    
    @Slot(str)
    def setSpeedByOption(self, option):
        """Set speed by option string"""
        if option in self.SPEED_OPTIONS:
            speed_value = self.SPEED_OPTIONS[option]
            # Don't call setter method, just assign directly  
            if self._current_speed != speed_value:
                old_speed = self._current_speed
                self._current_speed = speed_value
                logger.debug(f"Speed changed from {old_speed} to {speed_value} ({option})")
                
                # Send to main application
                asyncio.create_task(self._set_speed_async(speed_value))
                
                # Emit change signal for QML
                self.speedChanged.emit(speed_value)
        else:
            logger.warning(f"Unknown speed option: {option}")
    
    async def _set_speed_async(self, speed):
        """Send speed to main application asynchronously"""
        if not self.session:
            return
        try:
            async with self.session.post(f"{self.base_url}/set_speed", json={"speed": speed}) as resp:
                if resp.status == 200:
                    logger.info(f"Speed set successfully: {speed}")
                else:
                    logger.error(f"Failed to set speed: {resp.status}")
        except Exception as e:
            logger.error(f"Exception setting speed: {e}")
    
    # Pause Between Patterns Methods
    @Slot(result='QStringList')
    def getPauseOptions(self):
        """Get list of pause between patterns options for QML"""
        return list(self.PAUSE_OPTIONS.keys())
    
    @Slot(result=str)
    def getCurrentPauseOption(self):
        """Get current pause between patterns as option string"""
        current_pause = self._pause_between_patterns
        for option, value in self.PAUSE_OPTIONS.items():
            if value == current_pause:
                return option
        # If custom value, return descriptive string
        if current_pause == 0:
            return "0s"
        elif current_pause < 60:
            return f"{current_pause}s"
        elif current_pause < 3600:
            minutes = current_pause // 60
            return f"{minutes} min"
        else:
            hours = current_pause // 3600
            return f"{hours} hour"
    
    @Slot(str)
    def setPauseByOption(self, option):
        """Set pause between patterns by option string"""
        if option in self.PAUSE_OPTIONS:
            pause_value = self.PAUSE_OPTIONS[option]
            if self._pause_between_patterns != pause_value:
                old_pause = self._pause_between_patterns
                self._pause_between_patterns = pause_value
                logger.info(f"Pause between patterns changed from {old_pause}s to {pause_value}s ({option})")

                # Save to local settings
                self._save_local_settings()

                # Emit change signal for QML
                self.pauseBetweenPatternsChanged.emit(pause_value)
        else:
            logger.warning(f"Unknown pause option: {option}")

    # Property for pause between patterns
    @Property(int, notify=pauseBetweenPatternsChanged)
    def pauseBetweenPatterns(self):
        """Get current pause between patterns in seconds"""
        return self._pause_between_patterns

    # Playlist Settings Properties and Slots
    @Property(bool, notify=playlistSettingsChanged)
    def playlistShuffle(self):
        """Get playlist shuffle setting"""
        return self._playlist_shuffle

    @Slot(bool)
    def setPlaylistShuffle(self, enabled):
        """Set playlist shuffle setting"""
        if self._playlist_shuffle != enabled:
            self._playlist_shuffle = enabled
            logger.info(f"Playlist shuffle changed to: {enabled}")
            self._save_local_settings()
            self.playlistSettingsChanged.emit()

    @Property(str, notify=playlistSettingsChanged)
    def playlistRunMode(self):
        """Get playlist run mode (single/loop)"""
        return self._playlist_run_mode

    @Slot(str)
    def setPlaylistRunMode(self, mode):
        """Set playlist run mode"""
        if mode in ["single", "loop"] and self._playlist_run_mode != mode:
            self._playlist_run_mode = mode
            logger.info(f"Playlist run mode changed to: {mode}")
            self._save_local_settings()
            self.playlistSettingsChanged.emit()

    @Property(str, notify=playlistSettingsChanged)
    def playlistClearPattern(self):
        """Get playlist clear pattern setting"""
        return self._playlist_clear_pattern

    @Slot(str)
    def setPlaylistClearPattern(self, pattern):
        """Set playlist clear pattern"""
        valid_patterns = ["adaptive", "clear_center", "clear_perimeter", "none"]
        if pattern in valid_patterns and self._playlist_clear_pattern != pattern:
            self._playlist_clear_pattern = pattern
            logger.info(f"Playlist clear pattern changed to: {pattern}")
            self._save_local_settings()
            self.playlistSettingsChanged.emit()
    
    # Screen Control Methods
    @Slot()
    def turnScreenOn(self):
        """Turn the screen on and reset activity timer"""
        if not self._screen_on:
            self._turn_screen_on()
        self._reset_activity_timer()
    
    @Slot()
    def turnScreenOff(self):
        """Turn the screen off (QML MouseArea handles wake-on-touch)"""
        self._turn_screen_off()
    
    @Slot()
    def resetActivityTimer(self):
        """Reset the activity timer (call on user interaction)"""
        self._reset_activity_timer()
        if not self._screen_on:
            self._turn_screen_on()
    
    def _turn_screen_on(self):
        """Internal method to turn screen on"""
        with self._screen_transition_lock:
            # Debounce: Don't turn on if we just changed state
            time_since_change = time.time() - self._last_screen_change
            if time_since_change < 2.0:  # 2 second debounce
                logger.debug(f"Screen state change blocked (debounce: {time_since_change:.1f}s < 2s)")
                return
            
            if self._screen_on:
                logger.debug("Screen already ON, skipping")
                return
            
            try:
                # Use the working screen-on script if available
                screen_on_script = Path('/usr/local/bin/screen-on')
                if screen_on_script.exists():
                    result = subprocess.run(['sudo', '/usr/local/bin/screen-on'], 
                                          capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        logger.debug("Screen turned ON (screen-on script)")
                    else:
                        logger.warning(f"screen-on script failed: {result.stderr}")
                else:
                    # Fallback: Manual control matching the script
                    # Unblank framebuffer and restore backlight
                    max_brightness = 255
                    try:
                        result = subprocess.run(['cat', '/sys/class/backlight/*/max_brightness'], 
                                              shell=True, capture_output=True, text=True, timeout=2)
                        if result.returncode == 0 and result.stdout.strip():
                            max_brightness = int(result.stdout.strip())
                    except:
                        pass
                    
                    subprocess.run(['sudo', 'sh', '-c', 
                                  f'echo 0 > /sys/class/graphics/fb0/blank && echo {max_brightness} > /sys/class/backlight/*/brightness'], 
                                 check=False, timeout=5)
                    logger.debug(f"Screen turned ON (manual, brightness: {max_brightness})")
                
                self._screen_on = True
                self._last_screen_change = time.time()
                self.screenStateChanged.emit(True)

            except Exception as e:
                logger.error(f"Failed to turn screen on: {e}")
    
    def _turn_screen_off(self):
        """Internal method to turn screen off"""
        logger.debug("_turn_screen_off() called")
        with self._screen_transition_lock:
            # Debounce: Don't turn off if we just changed state
            time_since_change = time.time() - self._last_screen_change
            if time_since_change < 2.0:  # 2 second debounce
                logger.debug(f"Screen state change blocked (debounce: {time_since_change:.1f}s < 2s)")
                return
            
            if not self._screen_on:
                logger.debug("Screen already OFF, skipping")
                return
        
        try:
            # Use the working screen-off script if available
            screen_off_script = Path('/usr/local/bin/screen-off')
            logger.debug(f"Checking for screen-off script at: {screen_off_script}")
            logger.debug(f"Script exists: {screen_off_script.exists()}")
            
            if screen_off_script.exists():
                logger.debug("Executing screen-off script...")
                result = subprocess.run(['sudo', '/usr/local/bin/screen-off'], 
                                      capture_output=True, text=True, timeout=10)
                logger.debug(f"Script return code: {result.returncode}")
                if result.stdout:
                    logger.debug(f"Script stdout: {result.stdout}")
                if result.stderr:
                    logger.debug(f"Script stderr: {result.stderr}")
                    
                if result.returncode == 0:
                    logger.info("Screen turned OFF (screen-off script)")
                else:
                    logger.warning(f"screen-off script failed: return code {result.returncode}")
            else:
                logger.debug("Using manual screen control...")
                # Fallback: Manual control matching the script
                # Blank framebuffer and turn off backlight
                subprocess.run(['sudo', 'sh', '-c', 
                              'echo 0 > /sys/class/backlight/*/brightness && echo 1 > /sys/class/graphics/fb0/blank'], 
                             check=False, timeout=5)
                logger.debug("Screen turned OFF (manual)")
            
            self._screen_on = False
            self._last_screen_change = time.time()
            self.screenStateChanged.emit(False)
            logger.debug("Screen state set to OFF, signal emitted")
            
        except Exception as e:
            logger.error(f"Failed to turn screen off: {e}")
            import traceback
            traceback.print_exc()
    
    def _reset_activity_timer(self):
        """Reset the last activity timestamp"""
        old_time = self._last_activity
        self._last_activity = time.time()
        time_since_last = self._last_activity - old_time
        if time_since_last > 1:  # Only log if it's been more than 1 second
            logger.debug(f"Activity detected - timer reset (was idle for {time_since_last:.1f}s)")
    
    def _check_screen_timeout(self):
        """Check if screen should be turned off due to inactivity.

        Wake-on-touch is handled by QML's global MouseArea which calls
        resetActivityTimer() on any touch event, even when screen is off.
        """
        if self._screen_on and self._screen_timeout > 0:  # Only check if timeout is enabled
            idle_time = time.time() - self._last_activity
            # Log every 10 seconds when getting close to timeout
            if idle_time > self._screen_timeout - 10 and idle_time % 10 < 1:
                logger.debug(f"Screen idle for {idle_time:.0f}s (timeout at {self._screen_timeout}s)")

            if idle_time > self._screen_timeout:
                logger.debug(f"Screen timeout reached! Idle for {idle_time:.0f}s (timeout: {self._screen_timeout}s)")
                self._turn_screen_off()
        # If timeout is 0 (Never), screen stays on indefinitely

    # ==================== LED Control Methods ====================

    # LED Properties
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

    @Slot()
    def loadLedConfig(self):
        """Load LED configuration from the server"""
        logger.debug("Loading LED configuration...")
        asyncio.create_task(self._load_led_config())

    async def _load_led_config(self):
        if not self.session:
            logger.warning("Session not ready for LED config")
            return

        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with self.session.get(f"{self.base_url}/get_led_config", timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._led_provider = data.get("provider", "none")
                    logger.debug(f"LED provider: {self._led_provider}")

                    if self._led_provider == "dw_leds":
                        # Load DW LEDs status
                        await self._load_led_status()
                        await self._load_led_effects()
                        await self._load_led_palettes()

                    self.ledStatusChanged.emit()
                else:
                    logger.error(f"Failed to get LED config: {resp.status}")
        except Exception as e:
            logger.error(f"Exception loading LED config: {e}")

    async def _load_led_status(self):
        """Load current LED status"""
        if not self.session:
            return

        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with self.session.get(f"{self.base_url}/api/dw_leds/status", timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._led_connected = data.get("connected", False)
                    self._led_power_on = data.get("power_on", False)
                    self._led_brightness = data.get("brightness", 100)
                    self._led_current_effect = data.get("current_effect", 0)
                    self._led_current_palette = data.get("current_palette", 0)
                    logger.debug(f"LED status: connected={self._led_connected}, power={self._led_power_on}, brightness={self._led_brightness}")
                    self.ledStatusChanged.emit()
        except Exception as e:
            logger.error(f"Exception loading LED status: {e}")

    async def _load_led_effects(self):
        """Load available LED effects"""
        if not self.session:
            return

        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with self.session.get(f"{self.base_url}/api/dw_leds/effects", timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # API returns effects as [[id, name], ...] arrays
                    raw_effects = data.get("effects", [])
                    # Convert to list of dicts for easier use in QML
                    self._led_effects = [{"id": e[0], "name": e[1]} for e in raw_effects if len(e) >= 2]
                    logger.debug(f"Loaded {len(self._led_effects)} LED effects")
                    self.ledEffectsLoaded.emit(self._led_effects)
        except Exception as e:
            logger.error(f"Exception loading LED effects: {e}")

    async def _load_led_palettes(self):
        """Load available LED palettes"""
        if not self.session:
            return

        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with self.session.get(f"{self.base_url}/api/dw_leds/palettes", timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # API returns palettes as [[id, name], ...] arrays
                    raw_palettes = data.get("palettes", [])
                    # Convert to list of dicts for easier use in QML
                    self._led_palettes = [{"id": p[0], "name": p[1]} for p in raw_palettes if len(p) >= 2]
                    logger.debug(f"Loaded {len(self._led_palettes)} LED palettes")
                    self.ledPalettesLoaded.emit(self._led_palettes)
        except Exception as e:
            logger.error(f"Exception loading LED palettes: {e}")

    @Slot()
    def refreshLedStatus(self):
        """Refresh LED status from server"""
        logger.debug("Refreshing LED status...")
        asyncio.create_task(self._load_led_status())

    @Slot()
    def toggleLedPower(self):
        """Toggle LED power on/off"""
        logger.debug("Toggling LED power...")
        asyncio.create_task(self._toggle_led_power())

    async def _toggle_led_power(self):
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return

        try:
            async with self.session.post(
                f"{self.base_url}/api/dw_leds/power",
                json={"state": 2}  # Toggle
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._led_power_on = data.get("power_on", False)
                    self._led_connected = data.get("connected", False)
                    logger.debug(f"LED power toggled: {self._led_power_on}")
                    self.ledStatusChanged.emit()
                else:
                    self.errorOccurred.emit(f"Failed to toggle LED power: {resp.status}")
        except Exception as e:
            logger.error(f"Exception toggling LED power: {e}")
            self.errorOccurred.emit(str(e))

    @Slot(bool)
    def setLedPower(self, on):
        """Set LED power state (True=on, False=off)"""
        logger.debug(f"Setting LED power: {on}")
        asyncio.create_task(self._set_led_power(on))

    async def _set_led_power(self, on):
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return

        try:
            async with self.session.post(
                f"{self.base_url}/api/dw_leds/power",
                json={"state": 1 if on else 0}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._led_power_on = data.get("power_on", False)
                    self._led_connected = data.get("connected", False)
                    logger.debug(f"LED power set: {self._led_power_on}")
                    self.ledStatusChanged.emit()
                else:
                    self.errorOccurred.emit(f"Failed to set LED power: {resp.status}")
        except Exception as e:
            logger.error(f"Exception setting LED power: {e}")
            self.errorOccurred.emit(str(e))

    @Slot(int)
    def setLedBrightness(self, value):
        """Set LED brightness (0-100)"""
        logger.debug(f"Setting LED brightness: {value}")
        asyncio.create_task(self._set_led_brightness(value))

    async def _set_led_brightness(self, value):
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return

        try:
            async with self.session.post(
                f"{self.base_url}/api/dw_leds/brightness",
                json={"value": value}
            ) as resp:
                if resp.status == 200:
                    self._led_brightness = value
                    logger.debug(f"LED brightness set: {value}")
                    self.ledStatusChanged.emit()
                else:
                    self.errorOccurred.emit(f"Failed to set brightness: {resp.status}")
        except Exception as e:
            logger.error(f"Exception setting LED brightness: {e}")
            self.errorOccurred.emit(str(e))

    @Slot(int, int, int)
    def setLedColor(self, r, g, b):
        """Set LED color using RGB values"""
        logger.debug(f"Setting LED color: RGB({r}, {g}, {b})")
        asyncio.create_task(self._set_led_color(r, g, b))

    async def _set_led_color(self, r, g, b):
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return

        try:
            async with self.session.post(
                f"{self.base_url}/api/dw_leds/color",
                json={"color": [r, g, b]}
            ) as resp:
                if resp.status == 200:
                    self._led_color = f"#{r:02x}{g:02x}{b:02x}"
                    logger.debug(f"LED color set: {self._led_color}")
                    self.ledStatusChanged.emit()
                else:
                    self.errorOccurred.emit(f"Failed to set color: {resp.status}")
        except Exception as e:
            logger.error(f"Exception setting LED color: {e}")
            self.errorOccurred.emit(str(e))

    @Slot(str)
    def setLedColorHex(self, hexColor):
        """Set LED color using hex string (e.g., '#ff0000')"""
        # Parse hex color
        hexColor = hexColor.lstrip('#')
        if len(hexColor) == 6:
            r = int(hexColor[0:2], 16)
            g = int(hexColor[2:4], 16)
            b = int(hexColor[4:6], 16)
            self.setLedColor(r, g, b)
        else:
            logger.warning(f"Invalid hex color: {hexColor}")

    @Slot(int)
    def setLedEffect(self, effectId):
        """Set LED effect by ID"""
        logger.debug(f"Setting LED effect: {effectId}")
        asyncio.create_task(self._set_led_effect(effectId))

    async def _set_led_effect(self, effectId):
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return

        try:
            async with self.session.post(
                f"{self.base_url}/api/dw_leds/effect",
                json={"effect_id": effectId}
            ) as resp:
                if resp.status == 200:
                    self._led_current_effect = effectId
                    logger.debug(f"LED effect set: {effectId}")
                    self.ledStatusChanged.emit()
                else:
                    self.errorOccurred.emit(f"Failed to set effect: {resp.status}")
        except Exception as e:
            logger.error(f"Exception setting LED effect: {e}")
            self.errorOccurred.emit(str(e))

    @Slot(int)
    def setLedPalette(self, paletteId):
        """Set LED palette by ID"""
        logger.debug(f"Setting LED palette: {paletteId}")
        asyncio.create_task(self._set_led_palette(paletteId))

    async def _set_led_palette(self, paletteId):
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return

        try:
            async with self.session.post(
                f"{self.base_url}/api/dw_leds/palette",
                json={"palette_id": paletteId}
            ) as resp:
                if resp.status == 200:
                    self._led_current_palette = paletteId
                    logger.debug(f"LED palette set: {paletteId}")
                    self.ledStatusChanged.emit()
                else:
                    self.errorOccurred.emit(f"Failed to set palette: {resp.status}")
        except Exception as e:
            logger.error(f"Exception setting LED palette: {e}")
            self.errorOccurred.emit(str(e))

    # ==================== Pattern Refresh Methods ====================

    @Slot()
    def refreshPatterns(self):
        """Refresh pattern cache - converts new WebPs to PNG and rescans patterns"""
        logger.debug("Refreshing patterns...")
        asyncio.create_task(self._refresh_patterns())

    async def _refresh_patterns(self):
        """Async implementation of pattern refresh"""
        try:
            from png_cache_manager import PngCacheManager
            cache_manager = PngCacheManager()
            success = await cache_manager.ensure_png_cache_available()

            message = "Patterns refreshed" if success else "Refreshed with warnings"
            logger.info(f"Pattern refresh completed: {message}")
            self.patternsRefreshCompleted.emit(True, message)
        except Exception as e:
            logger.error(f"Pattern refresh failed: {e}")
            self.patternsRefreshCompleted.emit(False, str(e))

    # ==================== System Control Methods ====================

    @Slot()
    def restartBackend(self):
        """Restart the dune-weaver backend via API"""
        logger.debug("Requesting backend restart via API...")
        asyncio.create_task(self._restart_backend())

    async def _restart_backend(self):
        """Async implementation of backend restart"""
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return

        try:
            async with self.session.post(f"{self.base_url}/api/system/restart") as resp:
                if resp.status == 200:
                    logger.info("Backend restart initiated via API")
                else:
                    response_text = await resp.text()
                    logger.error(f"Failed to restart backend: {resp.status} - {response_text}")
                    self.errorOccurred.emit(f"Failed to restart: {response_text}")
        except Exception as e:
            logger.error(f"Exception restarting backend: {e}")
            self.errorOccurred.emit(str(e))

    @Slot()
    def shutdownPi(self):
        """Shutdown the Raspberry Pi via API"""
        logger.info("Requesting Pi shutdown via API...")
        asyncio.create_task(self._shutdown_pi())

    async def _shutdown_pi(self):
        """Async implementation of Pi shutdown"""
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return

        try:
            async with self.session.post(f"{self.base_url}/api/system/shutdown") as resp:
                if resp.status == 200:
                    logger.info("Shutdown initiated via API")
                else:
                    response_text = await resp.text()
                    logger.error(f"Failed to shutdown: {resp.status} - {response_text}")
                    self.errorOccurred.emit(f"Failed to shutdown: {response_text}")
        except Exception as e:
            logger.error(f"Exception during shutdown: {e}")
            self.errorOccurred.emit(str(e))

    # ==================== Playlist Management Methods ====================

    @Slot(str)
    def createPlaylist(self, playlistName):
        """Create a new empty playlist"""
        logger.debug(f"Creating playlist: {playlistName}")
        asyncio.create_task(self._create_playlist(playlistName))

    async def _create_playlist(self, playlistName):
        """Async implementation of playlist creation"""
        if not self.session:
            self.playlistCreated.emit(False, "Backend not ready")
            return

        try:
            async with self.session.post(
                f"{self.base_url}/create_playlist",
                json={"playlist_name": playlistName, "files": []}
            ) as resp:
                if resp.status == 200:
                    logger.info(f"Playlist created: {playlistName}")
                    self.playlistCreated.emit(True, f"Created: {playlistName}")
                else:
                    response_text = await resp.text()
                    logger.error(f"Failed to create playlist: {resp.status} - {response_text}")
                    self.playlistCreated.emit(False, f"Failed: {response_text}")
        except Exception as e:
            logger.error(f"Exception creating playlist: {e}")
            self.playlistCreated.emit(False, str(e))

    @Slot(str)
    def deletePlaylist(self, playlistName):
        """Delete a playlist"""
        logger.info(f"Deleting playlist: {playlistName}")
        asyncio.create_task(self._delete_playlist(playlistName))

    async def _delete_playlist(self, playlistName):
        """Async implementation of playlist deletion"""
        if not self.session:
            self.playlistDeleted.emit(False, "Backend not ready")
            return

        try:
            async with self.session.request(
                "DELETE",
                f"{self.base_url}/delete_playlist",
                json={"playlist_name": playlistName}
            ) as resp:
                if resp.status == 200:
                    logger.info(f"Playlist deleted: {playlistName}")
                    self.playlistDeleted.emit(True, f"Deleted: {playlistName}")
                else:
                    response_text = await resp.text()
                    logger.error(f"Failed to delete playlist: {resp.status} - {response_text}")
                    self.playlistDeleted.emit(False, f"Failed: {response_text}")
        except Exception as e:
            logger.error(f"Exception deleting playlist: {e}")
            self.playlistDeleted.emit(False, str(e))

    @Slot(str, str)
    def addPatternToPlaylist(self, playlistName, patternPath):
        """Add a pattern to an existing playlist"""
        logger.info(f"Adding pattern to playlist: {patternPath} -> {playlistName}")
        asyncio.create_task(self._add_pattern_to_playlist(playlistName, patternPath))

    async def _add_pattern_to_playlist(self, playlistName, patternPath):
        """Async implementation of adding pattern to playlist"""
        if not self.session:
            self.patternAddedToPlaylist.emit(False, "Backend not ready")
            return

        try:
            async with self.session.post(
                f"{self.base_url}/add_to_playlist",
                json={"playlist_name": playlistName, "pattern": patternPath}
            ) as resp:
                if resp.status == 200:
                    logger.info(f"Pattern added to {playlistName}")
                    self.patternAddedToPlaylist.emit(True, f"Added to {playlistName}")
                else:
                    response_text = await resp.text()
                    logger.error(f"Failed to add pattern: {resp.status} - {response_text}")
                    self.patternAddedToPlaylist.emit(False, f"Failed: {response_text}")
        except Exception as e:
            logger.error(f"Exception adding pattern: {e}")
            self.patternAddedToPlaylist.emit(False, str(e))

    @Slot(str, list)
    def updatePlaylistPatterns(self, playlistName, patterns):
        """Update a playlist with a new list of patterns (used for removing patterns)"""
        logger.debug(f"Updating playlist patterns: {playlistName} -> {len(patterns)} patterns")
        asyncio.create_task(self._update_playlist_patterns(playlistName, patterns))

    async def _update_playlist_patterns(self, playlistName, patterns):
        """Async implementation of playlist pattern update"""
        if not self.session:
            self.playlistModified.emit(False, "Backend not ready")
            return

        try:
            async with self.session.post(
                f"{self.base_url}/modify_playlist",
                json={"playlist_name": playlistName, "files": patterns}
            ) as resp:
                if resp.status == 200:
                    logger.info(f"Playlist updated: {playlistName}")
                    self.playlistModified.emit(True, f"Updated: {playlistName}")
                else:
                    response_text = await resp.text()
                    logger.error(f"Failed to update playlist: {resp.status} - {response_text}")
                    self.playlistModified.emit(False, f"Failed: {response_text}")
        except Exception as e:
            logger.error(f"Exception updating playlist: {e}")
            self.playlistModified.emit(False, str(e))

    @Slot(result=list)
    def getPlaylistNames(self):
        """Get list of all playlist names (synchronous, reads from local file)"""
        try:
            playlists_file = Path("../playlists.json")
            if playlists_file.exists():
                with open(playlists_file, 'r') as f:
                    data = json.load(f)
                    return sorted(list(data.keys()))
        except Exception as e:
            logger.error(f"Error reading playlists: {e}")
        return []