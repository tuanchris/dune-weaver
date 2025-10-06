from PySide6.QtCore import QObject, Signal, Property, Slot, QTimer
from PySide6.QtQml import QmlElement
from PySide6.QtWebSockets import QWebSocket
from PySide6.QtNetwork import QAbstractSocket
import aiohttp
import asyncio
import json
import subprocess
import threading
import time
from pathlib import Path
import os

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
        "1 hour": 3600  # 1 hour
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
    
    # Backend connection status signals
    backendConnectionChanged = Signal(bool)  # True = backend reachable, False = unreachable
    reconnectStatusChanged = Signal(str)  # Current reconnection status message

    # Cache generation signals
    cacheProgressChanged = Signal(dict)  # Emits cache progress data

    def __init__(self):
        super().__init__()
        self.base_url = "http://localhost:8080"

        # Cache progress tracking
        self._cache_in_progress = False
        self._cache_progress = {
            'in_progress': False,
            'current': 0,
            'total': 0,
            'current_file': '',
            'percentage': 0
        }
        
        # Initialize all status properties first
        self._current_file = ""
        self._progress = 0
        self._is_running = False
        self._is_connected = False
        self._serial_ports = []
        self._serial_connected = False
        self._current_port = ""
        self._current_speed = 130
        self._auto_play_on_boot = False
        self._pause_between_patterns = 0  # Default: no pause (0 seconds)
        
        # Backend connection status
        self._backend_connected = False
        self._reconnect_status = "Connecting to backend..."
        
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
        self._touch_monitor_thread = None
        self._screen_transition_lock = threading.Lock()  # Prevent rapid state changes
        self._last_screen_change = 0  # Track last state change time
        self._use_touch_script = False  # Disable external touch-monitor script (too sensitive)
        self._screen_timer = QTimer()
        self._screen_timer.timeout.connect(self._check_screen_timeout)
        self._screen_timer.start(1000)  # Check every second
        # Load local settings first
        self._load_local_settings()
        print(f"🖥️ Screen management initialized: timeout={self._screen_timeout}s, timer started")
        
        # HTTP session - initialize lazily
        self.session = None
        self._session_initialized = False
        
        # Use QTimer to defer session initialization until event loop is running
        QTimer.singleShot(100, self._delayed_init)
        
        # Start initial WebSocket connection (after all attributes are initialized)
        # Use QTimer to ensure it happens after constructor completes
        QTimer.singleShot(200, self._attempt_ws_reconnect)

        # Start cache progress monitoring
        self._cache_progress_timer = QTimer()
        self._cache_progress_timer.timeout.connect(self._check_cache_progress)
        QTimer.singleShot(1000, lambda: self._cache_progress_timer.start(2000))  # Check every 2 seconds
    
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

    @Property(bool, notify=cacheProgressChanged)
    def cacheInProgress(self):
        return self._cache_in_progress

    @Property(dict, notify=cacheProgressChanged)
    def cacheProgress(self):
        return self._cache_progress

    # Cache progress checking
    @Slot()
    def _check_cache_progress(self):
        """Poll the backend for cache generation progress"""
        if self.session and self._backend_connected:
            asyncio.create_task(self._fetch_cache_progress())

    async def _fetch_cache_progress(self):
        """Fetch cache progress from backend API"""
        try:
            async with self.session.get(f"{self.base_url}/cache-progress") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    was_in_progress = self._cache_in_progress
                    self._cache_in_progress = data.get('in_progress', False)
                    self._cache_progress = {
                        'in_progress': data.get('in_progress', False),
                        'current': data.get('current', 0),
                        'total': data.get('total', 0),
                        'current_file': data.get('current_file', ''),
                        'percentage': data.get('percentage', 0)
                    }

                    # Only emit if status changed or progress updated
                    if was_in_progress != self._cache_in_progress or self._cache_in_progress:
                        self.cacheProgressChanged.emit(self._cache_progress)

                        # Log when cache generation starts/stops
                        if self._cache_in_progress and not was_in_progress:
                            print(f"🎨 Cache generation started: {self._cache_progress['total']} patterns")
                        elif not self._cache_in_progress and was_in_progress:
                            print(f"✅ Cache generation completed!")

        except Exception as e:
            # Silently fail - cache progress is non-critical
            pass

    # WebSocket handlers
    @Slot()
    def _on_ws_connected(self):
        print("✅ WebSocket connected successfully")
        self._is_connected = True
        self._backend_connected = True
        self._reconnect_attempts = 0  # Reset reconnection counter
        self._reconnect_status = "Connected to backend"
        self.connectionChanged.emit()
        self.backendConnectionChanged.emit(True)
        self.reconnectStatusChanged.emit("Connected to backend")
        
        # Load initial settings when we connect
        self.loadControlSettings()
    
    @Slot()
    def _on_ws_disconnected(self):
        print("❌ WebSocket disconnected")
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
        print(f"❌ WebSocket error: {error}")
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
        print(f"🔄 {status_msg}")
        self._reconnect_status = status_msg
        self.reconnectStatusChanged.emit(status_msg)
        self._reconnect_timer.start(self._reconnect_delay)  # Always 1 second
    
    @Slot()
    def _attempt_ws_reconnect(self):
        """Attempt to reconnect WebSocket."""
        if self.ws.state() == QAbstractSocket.SocketState.ConnectedState:
            print("✅ WebSocket already connected")
            return
            
        self._reconnect_attempts += 1
        status_msg = f"Connecting to backend... (attempt {self._reconnect_attempts})"
        print(f"🔄 {status_msg}")
        self._reconnect_status = status_msg
        self.reconnectStatusChanged.emit(status_msg)
        
        # Close existing connection if any
        if self.ws.state() != QAbstractSocket.SocketState.UnconnectedState:
            self.ws.close()
        
        # Attempt new connection
        self.ws.open("ws://localhost:8080/ws/status")
    
    @Slot()
    def retryConnection(self):
        """Manually retry connection (reset attempts and try again)."""
        print("🔄 Manual connection retry requested")
        self._reconnect_attempts = 0
        self._reconnect_timer.stop()  # Stop any scheduled reconnect
        self._attempt_ws_reconnect()
    
    @Slot(str)
    def _on_ws_message(self, message):
        try:
            data = json.loads(message)
            if data.get("type") == "status_update":
                status = data.get("data", {})
                self._current_file = status.get("current_file", "")
                self._is_running = status.get("is_running", False)
                
                # Handle serial connection status from WebSocket
                ws_connection_status = status.get("connection_status", False)
                if ws_connection_status != self._serial_connected:
                    print(f"🔌 WebSocket serial connection status changed: {ws_connection_status}")
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
                    print(f"⚡ WebSocket speed changed: {ws_speed}")
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
                        print(f"🔌 Updated current port from WebSocket trigger: {current_port}")
        except Exception as e:
            print(f"💥 Exception getting current port: {e}")
    
    # API Methods
    @Slot(str, str)
    def executePattern(self, fileName, preExecution="adaptive"):
        print(f"🎯 ExecutePattern called: fileName='{fileName}', preExecution='{preExecution}'")
        asyncio.create_task(self._execute_pattern(fileName, preExecution))
    
    async def _execute_pattern(self, fileName, preExecution):
        if not self.session:
            print("❌ Backend session not ready")
            self.errorOccurred.emit("Backend not ready, please try again")
            return
        
        try:
            request_data = {"file_name": fileName, "pre_execution": preExecution}
            print(f"🔄 Making HTTP POST to: {self.base_url}/run_theta_rho")
            print(f"📝 Request payload: {request_data}")
            
            async with self.session.post(
                f"{self.base_url}/run_theta_rho",
                json=request_data
            ) as resp:
                print(f"📡 Response status: {resp.status}")
                print(f"📋 Response headers: {dict(resp.headers)}")
                
                response_text = await resp.text()
                print(f"📄 Response body: {response_text}")
                
                if resp.status == 200:
                    print("✅ Pattern execution request successful")
                    # Find preview image for the pattern
                    preview_path = self._find_pattern_preview(fileName)
                    print(f"🖼️ Pattern preview path: {preview_path}")
                    print(f"📡 About to emit executionStarted signal with: fileName='{fileName}', preview='{preview_path}'")
                    try:
                        self.executionStarted.emit(fileName, preview_path)
                        print("✅ ExecutionStarted signal emitted successfully")
                    except Exception as e:
                        print(f"❌ Error emitting executionStarted signal: {e}")
                else:
                    print(f"❌ Pattern execution failed with status {resp.status}")
                    self.errorOccurred.emit(f"Failed to execute: {resp.status} - {response_text}")
        except Exception as e:
            print(f"💥 Exception in _execute_pattern: {e}")
            self.errorOccurred.emit(str(e))
    
    def _find_pattern_preview(self, fileName):
        """Find the preview image for a pattern"""
        try:
            # Extract just the filename from the path (remove any directory prefixes)
            clean_filename = fileName.split('/')[-1]  # Get last part of path
            print(f"🔍 Original fileName: {fileName}, clean filename: {clean_filename}")
            
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
                    print(f"🔍 Checking preview cache directory: {cache_dir}")
                    # Use PNG format only for kiosk compatibility
                    # First try with .thr suffix (e.g., pattern.thr.png)
                    preview_file = cache_dir / (clean_filename + ".png")
                    print(f"🔍 Looking for preview: {preview_file}")
                    if preview_file.exists():
                        print(f"✅ Found preview: {preview_file}")
                        return str(preview_file.absolute())

                    # Then try without .thr suffix (e.g., pattern.png)
                    base_name = clean_filename.replace(".thr", "")
                    preview_file = cache_dir / (base_name + ".png")
                    print(f"🔍 Looking for preview (no .thr): {preview_file}")
                    if preview_file.exists():
                        print(f"✅ Found preview: {preview_file}")
                        return str(preview_file.absolute())
            
            print("❌ No preview image found")
            return ""
        except Exception as e:
            print(f"💥 Exception finding preview: {e}")
            return ""
    
    @Slot()
    def stopExecution(self):
        asyncio.create_task(self._stop_execution())
    
    async def _stop_execution(self):
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return
        
        try:
            print("🛑 Calling stop_execution endpoint...")
            # Add timeout to prevent hanging
            timeout = aiohttp.ClientTimeout(total=10)  # 10 second timeout
            async with self.session.post(f"{self.base_url}/stop_execution", timeout=timeout) as resp:
                print(f"🛑 Stop execution response status: {resp.status}")
                if resp.status == 200:
                    response_data = await resp.json()
                    print(f"🛑 Stop execution response: {response_data}")
                    self.executionStopped.emit()
                else:
                    print(f"❌ Stop execution failed with status: {resp.status}")
                    response_text = await resp.text()
                    self.errorOccurred.emit(f"Stop failed: {resp.status} - {response_text}")
        except asyncio.TimeoutError:
            print("⏰ Stop execution request timed out")
            self.errorOccurred.emit("Stop execution request timed out")
        except Exception as e:
            print(f"💥 Exception in _stop_execution: {e}")
            self.errorOccurred.emit(str(e))
    
    @Slot()
    def pauseExecution(self):
        print("⏸️ Pausing execution...")
        asyncio.create_task(self._api_call("/pause_execution"))
    
    @Slot()
    def resumeExecution(self):
        print("▶️ Resuming execution...")
        asyncio.create_task(self._api_call("/resume_execution"))
    
    @Slot()
    def skipPattern(self):
        print("⏭️ Skipping pattern...")
        asyncio.create_task(self._api_call("/skip_pattern"))
    
    @Slot(str, float, str, str, bool)
    def executePlaylist(self, playlistName, pauseTime=0.0, clearPattern="adaptive", runMode="single", shuffle=False):
        print(f"🎵 ExecutePlaylist called: playlist='{playlistName}', pauseTime={pauseTime}, clearPattern='{clearPattern}', runMode='{runMode}', shuffle={shuffle}")
        asyncio.create_task(self._execute_playlist(playlistName, pauseTime, clearPattern, runMode, shuffle))
    
    async def _execute_playlist(self, playlistName, pauseTime, clearPattern, runMode, shuffle):
        if not self.session:
            print("❌ Backend session not ready")
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
            print(f"🔄 Making HTTP POST to: {self.base_url}/run_playlist")
            print(f"📝 Request payload: {request_data}")
            
            async with self.session.post(
                f"{self.base_url}/run_playlist",
                json=request_data
            ) as resp:
                print(f"📡 Response status: {resp.status}")
                
                response_text = await resp.text()
                print(f"📄 Response body: {response_text}")
                
                if resp.status == 200:
                    print(f"✅ Playlist execution request successful: {playlistName}")
                    # The playlist will start executing patterns automatically
                    # Status updates will come through WebSocket
                else:
                    print(f"❌ Playlist execution failed with status {resp.status}")
                    self.errorOccurred.emit(f"Failed to execute playlist: {resp.status} - {response_text}")
        except Exception as e:
            print(f"💥 Exception in _execute_playlist: {e}")
            self.errorOccurred.emit(str(e))
    
    async def _api_call(self, endpoint):
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return
        
        try:
            print(f"📡 Calling API endpoint: {endpoint}")
            # Add timeout to prevent hanging
            timeout = aiohttp.ClientTimeout(total=10)  # 10 second timeout
            async with self.session.post(f"{self.base_url}{endpoint}", timeout=timeout) as resp:
                print(f"📡 API response status for {endpoint}: {resp.status}")
                if resp.status == 200:
                    response_data = await resp.json()
                    print(f"📡 API response for {endpoint}: {response_data}")
                else:
                    print(f"❌ API call {endpoint} failed with status: {resp.status}")
                    response_text = await resp.text()
                    self.errorOccurred.emit(f"API call failed: {endpoint} - {resp.status} - {response_text}")
        except asyncio.TimeoutError:
            print(f"⏰ API call {endpoint} timed out")
            self.errorOccurred.emit(f"API call {endpoint} timed out")
        except Exception as e:
            print(f"💥 Exception in API call {endpoint}: {e}")
            self.errorOccurred.emit(str(e))
    
    # Serial Port Management
    @Slot()
    def refreshSerialPorts(self):
        print("🔌 Refreshing serial ports...")
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
                    print(f"📡 Found serial ports: {self._serial_ports}")
                    self.serialPortsUpdated.emit(self._serial_ports)
                else:
                    print(f"❌ Failed to get serial ports: {resp.status}")
        except Exception as e:
            print(f"💥 Exception refreshing serial ports: {e}")
            self.errorOccurred.emit(str(e))
    
    @Slot(str)
    def connectSerial(self, port):
        print(f"🔗 Connecting to serial port: {port}")
        asyncio.create_task(self._connect_serial(port))
    
    async def _connect_serial(self, port):
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return
        
        try:
            async with self.session.post(f"{self.base_url}/connect", json={"port": port}) as resp:
                if resp.status == 200:
                    print(f"✅ Connected to {port}")
                    self._serial_connected = True
                    self._current_port = port
                    self.serialConnectionChanged.emit(True)
                    self.currentPortChanged.emit(port)
                else:
                    response_text = await resp.text()
                    print(f"❌ Failed to connect to {port}: {resp.status} - {response_text}")
                    self.errorOccurred.emit(f"Failed to connect: {response_text}")
        except Exception as e:
            print(f"💥 Exception connecting to serial: {e}")
            self.errorOccurred.emit(str(e))
    
    @Slot()
    def disconnectSerial(self):
        print("🔌 Disconnecting serial...")
        asyncio.create_task(self._disconnect_serial())
    
    async def _disconnect_serial(self):
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return
        
        try:
            async with self.session.post(f"{self.base_url}/disconnect") as resp:
                if resp.status == 200:
                    print("✅ Disconnected from serial")
                    self._serial_connected = False
                    self._current_port = ""
                    self.serialConnectionChanged.emit(False)
                    self.currentPortChanged.emit("")
                else:
                    response_text = await resp.text()
                    print(f"❌ Failed to disconnect: {resp.status} - {response_text}")
        except Exception as e:
            print(f"💥 Exception disconnecting serial: {e}")
            self.errorOccurred.emit(str(e))
    
    # Hardware Movement Controls
    @Slot()
    def sendHome(self):
        print("🏠 Sending home command...")
        asyncio.create_task(self._api_call("/send_home"))
    
    @Slot()
    def moveToCenter(self):
        print("🎯 Moving to center...")
        asyncio.create_task(self._api_call("/move_to_center"))
    
    @Slot()
    def moveToPerimeter(self):
        print("⭕ Moving to perimeter...")
        asyncio.create_task(self._api_call("/move_to_perimeter"))
    
    # Speed Control
    @Slot(int)
    def setSpeed(self, speed):
        print(f"⚡ Setting speed to: {speed}")
        asyncio.create_task(self._set_speed(speed))
    
    async def _set_speed(self, speed):
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return
        
        try:
            async with self.session.post(f"{self.base_url}/set_speed", json={"speed": speed}) as resp:
                if resp.status == 200:
                    print(f"✅ Speed set to {speed}")
                    self._current_speed = speed
                    self.speedChanged.emit(speed)
                else:
                    response_text = await resp.text()
                    print(f"❌ Failed to set speed: {resp.status} - {response_text}")
        except Exception as e:
            print(f"💥 Exception setting speed: {e}")
            self.errorOccurred.emit(str(e))
    
    # Auto Play on Boot Setting
    @Slot(bool)
    def setAutoPlayOnBoot(self, enabled):
        print(f"🚀 Setting auto play on boot: {enabled}")
        asyncio.create_task(self._set_auto_play_on_boot(enabled))
    
    async def _set_auto_play_on_boot(self, enabled):
        if not self.session:
            self.errorOccurred.emit("Backend not ready")
            return
        
        try:
            # Use the kiosk mode API endpoint for auto-play on boot
            async with self.session.post(f"{self.base_url}/api/kiosk-mode", json={"enabled": enabled}) as resp:
                if resp.status == 200:
                    print(f"✅ Auto play on boot set to {enabled}")
                    self._auto_play_on_boot = enabled
                else:
                    response_text = await resp.text()
                    print(f"❌ Failed to set auto play: {resp.status} - {response_text}")
        except Exception as e:
            print(f"💥 Exception setting auto play: {e}")
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
                        print(f"🖥️ Loaded screen timeout from local settings: Never (0s)")
                    else:
                        print(f"🖥️ Loaded screen timeout from local settings: {self._screen_timeout}s")
                else:
                    print(f"⚠️ Invalid screen timeout in settings, using default: {self.DEFAULT_SCREEN_TIMEOUT}s")
            else:
                print(f"📄 No local settings file found, creating with defaults")
                self._save_local_settings()
        except Exception as e:
            print(f"❌ Error loading local settings: {e}, using defaults")
            self._screen_timeout = self.DEFAULT_SCREEN_TIMEOUT
    
    def _save_local_settings(self):
        """Save settings to local JSON file"""
        try:
            settings = {
                'screen_timeout': self._screen_timeout,
                'version': '1.0'
            }
            with open(self.SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=2)
            print(f"💾 Saved local settings: screen_timeout={self._screen_timeout}s")
        except Exception as e:
            print(f"❌ Error saving local settings: {e}")

    @Slot()
    def loadControlSettings(self):
        print("📋 Loading control settings...")
        asyncio.create_task(self._load_settings())
    
    async def _load_settings(self):
        if not self.session:
            print("⚠️ Session not ready for loading settings")
            return
        
        try:
            # Load auto play setting from the working endpoint
            timeout = aiohttp.ClientTimeout(total=5)  # 5 second timeout
            async with self.session.get(f"{self.base_url}/api/auto_play-mode", timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._auto_play_on_boot = data.get("enabled", False)
                    print(f"🚀 Loaded auto play setting: {self._auto_play_on_boot}")
                # Note: Screen timeout is managed locally, not from server
            
            # Serial status will be handled by WebSocket updates automatically
            # But we still load the initial port info if connected
            async with self.session.get(f"{self.base_url}/serial_status", timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    initial_connected = data.get("connected", False)
                    current_port = data.get("port", "")
                    print(f"🔌 Initial serial status: connected={initial_connected}, port={current_port}")
                    
                    # Only update if WebSocket hasn't already set this
                    if initial_connected and current_port and not self._current_port:
                        self._current_port = current_port
                        self.currentPortChanged.emit(current_port)
                    
                    # Set initial connection status (WebSocket will take over from here)
                    if self._serial_connected != initial_connected:
                        self._serial_connected = initial_connected
                        self.serialConnectionChanged.emit(initial_connected)
            
            print("✅ Settings loaded - WebSocket will handle real-time updates")
            self.settingsLoaded.emit()
            
        except aiohttp.ClientConnectorError as e:
            print(f"⚠️ Cannot connect to backend at {self.base_url}: {e}")
            # Don't emit error - this is expected when backend is down
            # WebSocket will handle reconnection
        except asyncio.TimeoutError:
            print(f"⏰ Timeout loading settings from {self.base_url}")
            # Don't emit error - expected when backend is slow/down
        except Exception as e:
            print(f"💥 Unexpected error loading settings: {e}")
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
            print(f"🖥️ Screen timeout changed from {old_timeout}s to {timeout}s")
            
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
                print(f"🖥️ Screen timeout changed from {old_timeout}s to {timeout_value}s ({option})")
                
                # Save to local settings
                self._save_local_settings()
                
                # Emit change signal for QML
                self.screenTimeoutChanged.emit(timeout_value)
        else:
            print(f"⚠️ Unknown timeout option: {option}")
    
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
                print(f"⚡ Speed changed from {old_speed} to {speed_value} ({option})")
                
                # Send to main application
                asyncio.create_task(self._set_speed_async(speed_value))
                
                # Emit change signal for QML
                self.speedChanged.emit(speed_value)
        else:
            print(f"⚠️ Unknown speed option: {option}")
    
    async def _set_speed_async(self, speed):
        """Send speed to main application asynchronously"""
        if not self.session:
            return
        try:
            async with self.session.post(f"{self.base_url}/set_speed", json={"speed": speed}) as resp:
                if resp.status == 200:
                    print(f"✅ Speed set successfully: {speed}")
                else:
                    print(f"❌ Failed to set speed: {resp.status}")
        except Exception as e:
            print(f"💥 Exception setting speed: {e}")
    
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
                print(f"⏸️ Pause between patterns changed from {old_pause}s to {pause_value}s ({option})")
                
                # Emit change signal for QML
                self.pauseBetweenPatternsChanged.emit(pause_value)
        else:
            print(f"⚠️ Unknown pause option: {option}")
    
    # Property for pause between patterns
    @Property(int, notify=pauseBetweenPatternsChanged)
    def pauseBetweenPatterns(self):
        """Get current pause between patterns in seconds"""
        return self._pause_between_patterns
    
    # Screen Control Methods
    @Slot()
    def turnScreenOn(self):
        """Turn the screen on and reset activity timer"""
        if not self._screen_on:
            self._turn_screen_on()
        self._reset_activity_timer()
    
    @Slot()
    def turnScreenOff(self):
        """Turn the screen off"""
        self._turn_screen_off()
        # Start touch monitoring after manual screen off
        QTimer.singleShot(1000, self._start_touch_monitoring)  # 1 second delay
    
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
                print(f"🖥️ Screen state change blocked (debounce: {time_since_change:.1f}s < 2s)")
                return
            
            if self._screen_on:
                print("🖥️ Screen already ON, skipping")
                return
            
            try:
                # Use the working screen-on script if available
                screen_on_script = Path('/usr/local/bin/screen-on')
                if screen_on_script.exists():
                    result = subprocess.run(['sudo', '/usr/local/bin/screen-on'], 
                                          capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        print("🖥️ Screen turned ON (screen-on script)")
                    else:
                        print(f"⚠️ screen-on script failed: {result.stderr}")
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
                    print(f"🖥️ Screen turned ON (manual, brightness: {max_brightness})")
                
                self._screen_on = True
                self._last_screen_change = time.time()
                self.screenStateChanged.emit(True)
            
            except Exception as e:
                print(f"❌ Failed to turn screen on: {e}")
    
    def _turn_screen_off(self):
        """Internal method to turn screen off"""
        print("🖥️ _turn_screen_off() called")
        with self._screen_transition_lock:
            # Debounce: Don't turn off if we just changed state
            time_since_change = time.time() - self._last_screen_change
            if time_since_change < 2.0:  # 2 second debounce
                print(f"🖥️ Screen state change blocked (debounce: {time_since_change:.1f}s < 2s)")
                return
            
            if not self._screen_on:
                print("🖥️ Screen already OFF, skipping")
                return
        
        try:
            # Use the working screen-off script if available
            screen_off_script = Path('/usr/local/bin/screen-off')
            print(f"🖥️ Checking for screen-off script at: {screen_off_script}")
            print(f"🖥️ Script exists: {screen_off_script.exists()}")
            
            if screen_off_script.exists():
                print("🖥️ Executing screen-off script...")
                result = subprocess.run(['sudo', '/usr/local/bin/screen-off'], 
                                      capture_output=True, text=True, timeout=10)
                print(f"🖥️ Script return code: {result.returncode}")
                if result.stdout:
                    print(f"🖥️ Script stdout: {result.stdout}")
                if result.stderr:
                    print(f"🖥️ Script stderr: {result.stderr}")
                    
                if result.returncode == 0:
                    print("✅ Screen turned OFF (screen-off script)")
                else:
                    print(f"⚠️ screen-off script failed: return code {result.returncode}")
            else:
                print("🖥️ Using manual screen control...")
                # Fallback: Manual control matching the script
                # Blank framebuffer and turn off backlight
                subprocess.run(['sudo', 'sh', '-c', 
                              'echo 0 > /sys/class/backlight/*/brightness && echo 1 > /sys/class/graphics/fb0/blank'], 
                             check=False, timeout=5)
                print("🖥️ Screen turned OFF (manual)")
            
            self._screen_on = False
            self._last_screen_change = time.time()
            self.screenStateChanged.emit(False)
            print("🖥️ Screen state set to OFF, signal emitted")
            
        except Exception as e:
            print(f"❌ Failed to turn screen off: {e}")
            import traceback
            traceback.print_exc()
    
    def _reset_activity_timer(self):
        """Reset the last activity timestamp"""
        old_time = self._last_activity
        self._last_activity = time.time()
        time_since_last = self._last_activity - old_time
        if time_since_last > 1:  # Only log if it's been more than 1 second
            print(f"🖥️ Activity detected - timer reset (was idle for {time_since_last:.1f}s)")
    
    def _check_screen_timeout(self):
        """Check if screen should be turned off due to inactivity"""
        if self._screen_on and self._screen_timeout > 0:  # Only check if timeout is enabled
            idle_time = time.time() - self._last_activity
            # Log every 10 seconds when getting close to timeout
            if idle_time > self._screen_timeout - 10 and idle_time % 10 < 1:
                print(f"🖥️ Screen idle for {idle_time:.0f}s (timeout at {self._screen_timeout}s)")
            
            if idle_time > self._screen_timeout:
                print(f"🖥️ Screen timeout reached! Idle for {idle_time:.0f}s (timeout: {self._screen_timeout}s)")
                self._turn_screen_off()
                # Add delay before starting touch monitoring to avoid catching residual events
                QTimer.singleShot(1000, self._start_touch_monitoring)  # 1 second delay
        # If timeout is 0 (Never), screen stays on indefinitely
    
    def _start_touch_monitoring(self):
        """Start monitoring touch input for wake-up"""
        if self._touch_monitor_thread is None or not self._touch_monitor_thread.is_alive():
            self._touch_monitor_thread = threading.Thread(target=self._monitor_touch_input, daemon=True)
            self._touch_monitor_thread.start()
    
    def _monitor_touch_input(self):
        """Monitor touch input to wake up the screen"""
        print("👆 Starting touch monitoring for wake-up")
        # Add delay to let any residual touch events clear
        time.sleep(2)
        
        # Flush touch device to clear any buffered events
        try:
            # Find and flush touch device
            for i in range(5):
                device = f'/dev/input/event{i}'
                if Path(device).exists():
                    try:
                        # Read and discard any pending events
                        with open(device, 'rb') as f:
                            import fcntl
                            import os
                            fcntl.fcntl(f.fileno(), fcntl.F_SETFL, os.O_NONBLOCK)
                            while True:
                                try:
                                    f.read(24)  # Standard input_event size
                                except:
                                    break
                        print(f"👆 Flushed touch device: {device}")
                        break
                    except:
                        continue
        except Exception as e:
            print(f"👆 Could not flush touch device: {e}")
        
        print("👆 Touch monitoring active")
        try:
            # Use external touch monitor script if available - but only if not too sensitive
            touch_monitor_script = Path('/usr/local/bin/touch-monitor')
            use_script = touch_monitor_script.exists() and hasattr(self, '_use_touch_script') and self._use_touch_script
            
            if use_script:
                print("👆 Using touch-monitor script")
                # Add extra delay for script-based monitoring since it's more sensitive
                time.sleep(3)
                print("👆 Starting touch-monitor script after flush delay")
                process = subprocess.Popen(['sudo', '/usr/local/bin/touch-monitor'], 
                                         stdout=subprocess.PIPE, 
                                         stderr=subprocess.PIPE)
                
                # Wait for script to detect touch and wake screen
                while not self._screen_on:
                    if process.poll() is not None:  # Script exited (touch detected)
                        print("👆 Touch detected by monitor script")
                        self._turn_screen_on()
                        self._reset_activity_timer()
                        break
                    time.sleep(0.1)
                
                if process.poll() is None:
                    process.terminate()
            else:
                # Fallback: Direct monitoring
                # Find touch input device
                touch_device = None
                for i in range(5):  # Check event0 through event4
                    device = f'/dev/input/event{i}'
                    if Path(device).exists():
                        # Check if it's a touch device
                        try:
                            info = subprocess.run(['udevadm', 'info', '--query=all', f'--name={device}'], 
                                                capture_output=True, text=True, timeout=2)
                            if 'touch' in info.stdout.lower() or 'ft5406' in info.stdout.lower():
                                touch_device = device
                                break
                        except:
                            pass
                
                if not touch_device:
                    touch_device = '/dev/input/event0'  # Default fallback
                
                print(f"👆 Monitoring touch device: {touch_device}")
                
                # Try evtest first (more responsive to single taps)
                evtest_available = subprocess.run(['which', 'evtest'], 
                                                 capture_output=True).returncode == 0
                
                if evtest_available:
                    # Use evtest which is more sensitive to single touches
                    print("👆 Using evtest for touch detection")
                    process = subprocess.Popen(['sudo', 'evtest', touch_device], 
                                             stdout=subprocess.PIPE, 
                                             stderr=subprocess.DEVNULL,
                                             text=True)
                    
                    # Wait for any event line
                    while not self._screen_on:
                        try:
                            line = process.stdout.readline()
                            if line and 'Event:' in line:
                                print("👆 Touch detected via evtest - waking screen")
                                process.terminate()
                                self._turn_screen_on()
                                self._reset_activity_timer()
                                break
                        except:
                            pass
                        
                        if process.poll() is not None:
                            break
                        time.sleep(0.01)  # Small sleep to prevent CPU spinning
                else:
                    # Fallback: Use cat with single byte read (more responsive)
                    print("👆 Using cat for touch detection")
                    process = subprocess.Popen(['sudo', 'cat', touch_device], 
                                             stdout=subprocess.PIPE, 
                                             stderr=subprocess.DEVNULL)
                    
                    # Wait for any data (even 1 byte indicates touch)
                    while not self._screen_on:
                        try:
                            # Non-blocking check for data
                            import select
                            ready, _, _ = select.select([process.stdout], [], [], 0.1)
                            if ready:
                                data = process.stdout.read(1)  # Read just 1 byte
                                if data:
                                    print("👆 Touch detected - waking screen")
                                    process.terminate()
                                    self._turn_screen_on()
                                    self._reset_activity_timer()
                                    break
                        except:
                            pass
                        
                        # Check if screen was turned on by other means
                        if self._screen_on:
                            process.terminate()
                            break
                        
                        time.sleep(0.1)
                
        except Exception as e:
            print(f"❌ Error monitoring touch input: {e}")
        
        print("👆 Touch monitoring stopped")