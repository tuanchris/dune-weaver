from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional
import os
import logging
from datetime import datetime
from modules.connection import connection_manager
from modules.core import pattern_manager
from modules.core.pattern_manager import parse_theta_rho_file, THETA_RHO_DIR
from modules.core import playlist_manager
from modules.core import board_settings
from modules.core import execution
from modules.update import update_manager
from modules.core.state import state
from modules import mqtt
import signal
import asyncio
from contextlib import asynccontextmanager
from modules.led.led_interface import LEDInterface
from modules.screen.screen_controller import ScreenController
from modules.led.idle_timeout_manager import idle_timeout_manager
from modules.core.cache_manager import get_cache_path, generate_image_preview, get_pattern_metadata
from modules.core.version_manager import version_manager
from modules.core.mdns_discovery import discovery as mdns_discovery
from modules.core.log_handler import init_memory_handler, get_memory_handler
from modules.wifi.router import router as wifi_router, captive_portal_router
import json
import base64
import hashlib
import time
import subprocess
import requests

# Get log level from environment variable, default to INFO
log_level_str = os.getenv('LOG_LEVEL', 'INFO').upper()
log_level = getattr(logging, log_level_str, logging.INFO)

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
    ]
)

# Initialize memory log handler for web UI log viewer
# Increased to 5000 entries to support lazy loading in the UI
init_memory_handler(max_entries=5000)

logger = logging.getLogger(__name__)


async def _check_table_is_idle() -> bool:
    """Helper function to check if table is idle."""
    return not state.current_playing_file or state.pause_requested


def _start_idle_led_timeout():
    """Start idle LED timeout if enabled."""
    if not state.dw_led_idle_timeout_enabled or state.dw_led_idle_timeout_minutes <= 0:
        return

    logger.debug(f"Starting idle LED timeout: {state.dw_led_idle_timeout_minutes} minutes")
    idle_timeout_manager.start_idle_timeout(
        timeout_minutes=state.dw_led_idle_timeout_minutes,
        state=state,
        check_idle_callback=_check_table_is_idle
    )


def check_homing_in_progress():
    """Check if homing is in progress and raise exception if so."""
    if state.is_homing:
        raise HTTPException(status_code=409, detail="Cannot perform this action while homing is in progress")


def normalize_file_path(file_path: str) -> str:
    """Normalize file path separators for consistent cross-platform handling."""
    if not file_path:
        return ''
    
    # First normalize path separators
    normalized = file_path.replace('\\', '/')
    
    # Remove only the patterns directory prefix from the beginning, not patterns within the path
    if normalized.startswith('./patterns/'):
        normalized = normalized[11:]
    elif normalized.startswith('patterns/'):
        normalized = normalized[9:]
    
    return normalized

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Dune Weaver application...")

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Connect device in background so the web server starts immediately
    async def connect_and_home():
        """Connect to device and perform homing in background."""
        try:
            # Connect without homing first (fast)
            await asyncio.to_thread(connection_manager.connect_device, False)

            # If connected, perform homing in background (unless disabled)
            if state.conn and state.conn.is_connected():
                if not state.home_on_connect:
                    logger.info("Device connected. Home-on-connect is disabled — skipping automatic homing.")
                else:
                    logger.info("Device connected, starting homing in background...")
                    state.is_homing = True
                    try:
                        success = await asyncio.to_thread(connection_manager.home)
                        if not success:
                            logger.warning("Background homing failed or was skipped")
                            # If sensor homing failed, close connection and wait for user action
                            if state.sensor_homing_failed:
                                logger.error("Sensor homing failed - closing connection. User must check sensor or switch to crash homing.")
                                if state.conn:
                                    await asyncio.to_thread(state.conn.close)
                                    state.conn = None
                                return  # Don't proceed with auto-play
                    finally:
                        state.is_homing = False
                        logger.info("Background homing completed")

                # Auto-play on boot lives on the board ($Playlist/Autostart,
                # set via Settings) — nothing to do host-side.
        except Exception as e:
            logger.warning(f"Failed to auto-connect to board: {str(e)}")

    # Start connection/homing in background - doesn't block server startup
    asyncio.create_task(connect_and_home())

    # The board observer is the single status loop: it polls /sand_status,
    # translates it into the /ws/status contract, logs play history on file
    # transitions, runs the clear-speed and WLED quiet-hours shims, adopts
    # board-side Still Sands edits, and broadcasts to all clients.
    execution.observer.on_status = broadcast_status_update
    execution.observer.start()

    # Initialize LED controller based on saved configuration
    try:
        # Auto-detect provider for backward compatibility with existing installations
        if not state.led_provider or state.led_provider == "none":
            if state.wled_ip:
                state.led_provider = "wled"
                logger.info("Auto-detected WLED provider from existing configuration")

        # Initialize the appropriate controller
        if state.led_provider == "wled" and state.wled_ip:
            state.led_controller = LEDInterface("wled", state.wled_ip)
            logger.info(f"LED controller initialized: WLED at {state.wled_ip}")
        elif state.led_provider == "board":
            state.led_controller = LEDInterface("board")
            logger.info("LED controller initialized: table's built-in LEDs (firmware-controlled)")
        else:
            state.led_controller = None
            logger.info("LED controller not configured")

        # Save if provider was auto-detected
        if state.led_provider and state.wled_ip:
            state.save()
    except Exception as e:
        logger.warning(f"Failed to initialize LED controller: {str(e)}")
        state.led_controller = None

    # Initialize screen controller for LCD backlight control
    try:
        state.screen_controller = ScreenController()
        if state.screen_controller.available:
            logger.info("Screen controller initialized (backlight control available)")
        else:
            logger.info("Screen controller initialized (no backlight device found)")
    except Exception as e:
        logger.warning(f"Failed to initialize screen controller: {e}")
        state.screen_controller = None

    # Note: auto_play is now handled in connect_and_home() after homing completes

    try:
        mqtt.init_mqtt()
    except Exception as e:
        logger.warning(f"Failed to initialize MQTT: {str(e)}")
    
    # Schedule cache generation check for later (non-blocking startup)
    async def delayed_cache_check():
        """Check and generate cache in background."""
        try:
            logger.info("Starting cache check...")

            from modules.core.cache_manager import is_cache_generation_needed_async, generate_cache_background

            if await is_cache_generation_needed_async():
                logger.info("Cache generation needed, starting background task...")
                asyncio.create_task(generate_cache_background())  # Don't await - run in background
            else:
                logger.info("Cache is up to date, skipping generation")
        except Exception as e:
            logger.warning(f"Failed during cache generation: {str(e)}")

    # Start cache check in background immediately
    asyncio.create_task(delayed_cache_check())


    # Advertise this table via mDNS and browse for peer tables (best-effort)
    try:
        await mdns_discovery.start(
            table_id=state.table_id,
            table_name=state.table_name,
            port=8080,
            version=await version_manager.get_current_version(),
        )
    except Exception as e:
        logger.warning(f"mDNS table discovery unavailable: {e}")

    yield  # This separates startup from shutdown code

    # Shutdown
    logger.info("Shutting down Dune Weaver application...")
    await mdns_discovery.stop()

app = FastAPI(lifespan=lifespan)

# Add CORS middleware to allow cross-origin requests from other Dune Weaver frontends
# This enables multi-table control from a single frontend
# Note: allow_credentials must be False when allow_origins=["*"] (browser security requirement)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local network access
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include WiFi management router
app.include_router(wifi_router)
app.include_router(captive_portal_router)

# Global semaphore to limit concurrent preview processing
# Prevents resource exhaustion when loading many previews simultaneously
# Lazily initialized to avoid "attached to a different loop" errors
_preview_semaphore: Optional[asyncio.Semaphore] = None

def get_preview_semaphore() -> asyncio.Semaphore:
    """Get or create the preview semaphore in the current event loop."""
    global _preview_semaphore
    if _preview_semaphore is None:
        _preview_semaphore = asyncio.Semaphore(5)
    return _preview_semaphore

# Pydantic models for request/response validation
class ConnectRequest(BaseModel):
    port: Optional[str] = None
    # Board API password ($Sand/Password); stored and sent as X-Sand-Key.
    password: Optional[str] = None

class auto_playModeRequest(BaseModel):
    enabled: bool
    playlist: Optional[str] = None
    run_mode: Optional[str] = "loop"
    pause_time: Optional[float] = 5.0
    clear_pattern: Optional[str] = "adaptive"
    shuffle: Optional[bool] = False

class TimeSlot(BaseModel):
    start_time: str  # HH:MM format
    end_time: str    # HH:MM format
    days: str        # "daily", "weekdays", "weekends", or "custom"
    custom_days: Optional[List[str]] = []  # ["monday", "tuesday", etc.]

class ScheduledPauseRequest(BaseModel):
    enabled: bool
    control_wled: Optional[bool] = False
    finish_pattern: Optional[bool] = False  # Finish current pattern before pausing
    timezone: Optional[str] = None  # IANA timezone or None for system default
    time_slots: List[TimeSlot] = []

class CoordinateRequest(BaseModel):
    theta: float
    rho: float

class PlaylistRequest(BaseModel):
    playlist_name: str
    files: List[str] = []
    pause_time: float = 0
    clear_pattern: Optional[str] = None
    run_mode: str = "single"
    shuffle: bool = False

class PlaylistRunRequest(BaseModel):
    playlist_name: str
    pause_time: Optional[float] = 0
    clear_pattern: Optional[str] = None
    run_mode: Optional[str] = "single"
    shuffle: Optional[bool] = False
    start_time: Optional[str] = None
    end_time: Optional[str] = None

class SpeedRequest(BaseModel):
    speed: float

class WLEDRequest(BaseModel):
    wled_ip: Optional[str] = None

class LEDConfigRequest(BaseModel):
    provider: str  # "wled", "board", or "none"
    ip_address: Optional[str] = None  # For WLED only
    # DW LED specific fields
    num_leds: Optional[int] = None
    gpio_pin: Optional[int] = None
    pixel_order: Optional[str] = None
    brightness: Optional[int] = None

class DeletePlaylistRequest(BaseModel):
    playlist_name: str

class RenamePlaylistRequest(BaseModel):
    old_name: str
    new_name: str

class ThetaRhoRequest(BaseModel):
    file_name: str
    pre_execution: Optional[str] = "none"

class GetCoordinatesRequest(BaseModel):
    file_name: str

# ============================================================================
# Unified Settings Models
# ============================================================================

class AppSettingsUpdate(BaseModel):
    name: Optional[str] = None
    custom_logo: Optional[str] = None  # Filename or empty string to clear (favicon auto-generated)

class PatternSettingsUpdate(BaseModel):
    clear_pattern_speed: Optional[int] = None
    custom_clear_from_in: Optional[str] = None
    custom_clear_from_out: Optional[str] = None

class ScheduledPauseSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    control_wled: Optional[bool] = None
    finish_pattern: Optional[bool] = None
    timezone: Optional[str] = None  # IANA timezone (e.g., "America/New_York") or None for system default
    time_slots: Optional[List[TimeSlot]] = None

class HomingSettingsUpdate(BaseModel):
    mode: Optional[int] = None
    angular_offset_degrees: Optional[float] = None
    home_on_connect: Optional[bool] = None  # Auto-home after connecting on startup
    auto_home_enabled: Optional[bool] = None
    auto_home_after_patterns: Optional[int] = None
    hard_reset_theta: Optional[bool] = None  # Enable hard reset ($Bye) when resetting theta

class LedSettingsUpdate(BaseModel):
    provider: Optional[str] = None  # "none", "wled", "board"
    wled_ip: Optional[str] = None
    control_mode: Optional[str] = None  # "manual" or "automated"
    idle_timeout_enabled: Optional[bool] = None
    idle_timeout_minutes: Optional[int] = None

class MqttSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    broker: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None  # Write-only, never returned in GET
    client_id: Optional[str] = None
    discovery_prefix: Optional[str] = None
    device_id: Optional[str] = None
    device_name: Optional[str] = None

class MachineSettingsUpdate(BaseModel):
    timezone: Optional[str] = None  # IANA timezone (e.g., "America/New_York", "UTC")

class SecuritySettingsUpdate(BaseModel):
    mode: Optional[str] = None  # "off", "lockdown", "play_only"
    password: Optional[str] = None  # Write-only, stored as SHA-256 hash

class SecurityVerifyRequest(BaseModel):
    password: str

class SettingsUpdate(BaseModel):
    """Request model for PATCH /api/settings - all fields optional for partial updates"""
    app: Optional[AppSettingsUpdate] = None
    patterns: Optional[PatternSettingsUpdate] = None
    scheduled_pause: Optional[ScheduledPauseSettingsUpdate] = None
    homing: Optional[HomingSettingsUpdate] = None
    led: Optional[LedSettingsUpdate] = None
    mqtt: Optional[MqttSettingsUpdate] = None
    machine: Optional[MachineSettingsUpdate] = None
    security: Optional[SecuritySettingsUpdate] = None

# Store active WebSocket connections
active_status_connections = set()
active_cache_progress_connections = set()

@app.websocket("/ws/status")
async def websocket_status_endpoint(websocket: WebSocket):
    """Status stream. The board observer pushes every update via
    broadcast_status_update; this handler only sends the cached snapshot on
    connect and then holds the socket open."""
    await websocket.accept()
    active_status_connections.add(websocket)
    try:
        await websocket.send_json({
            "type": "status_update",
            "data": execution.get_cached_status()
        })
        while True:
            # Drain any client messages (none are expected) until disconnect.
            await websocket.receive_text()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        active_status_connections.discard(websocket)
        try:
            await websocket.close()
        except RuntimeError:
            pass

async def broadcast_status_update(status: dict):
    """Broadcast status update to all connected clients."""
    disconnected = set()
    for websocket in active_status_connections:
        try:
            await websocket.send_json({
                "type": "status_update",
                "data": status
            })
        except WebSocketDisconnect:
            disconnected.add(websocket)
        except RuntimeError:
            disconnected.add(websocket)
    
    active_status_connections.difference_update(disconnected)

@app.websocket("/ws/cache-progress")
async def websocket_cache_progress_endpoint(websocket: WebSocket):
    from modules.core.cache_manager import get_cache_progress

    await websocket.accept()
    active_cache_progress_connections.add(websocket)
    try:
        while True:
            progress = get_cache_progress()
            try:
                await websocket.send_json({
                    "type": "cache_progress",
                    "data": progress
                })
            except RuntimeError as e:
                if "close message has been sent" in str(e):
                    break
                raise
            await asyncio.sleep(1.0)  # Update every 1 second (reduced frequency for better performance)
    except WebSocketDisconnect:
        pass
    finally:
        active_cache_progress_connections.discard(websocket)
        try:
            await websocket.close()
        except RuntimeError:
            pass


# WebSocket endpoint for real-time log streaming
@app.websocket("/ws/logs")
async def websocket_logs_endpoint(websocket: WebSocket):
    """Stream application logs in real-time via WebSocket."""
    await websocket.accept()

    handler = get_memory_handler()
    if not handler:
        await websocket.close()
        return

    # Subscribe to log updates
    log_queue = handler.subscribe()

    try:
        while True:
            try:
                # Wait for new log entry with timeout
                log_entry = await asyncio.wait_for(log_queue.get(), timeout=30.0)
                await websocket.send_json({
                    "type": "log_entry",
                    "data": log_entry
                })
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                await websocket.send_json({"type": "heartbeat"})
            except RuntimeError as e:
                if "close message has been sent" in str(e):
                    break
                raise
    except WebSocketDisconnect:
        pass
    finally:
        handler.unsubscribe(log_queue)
        try:
            await websocket.close()
        except RuntimeError:
            pass


# API endpoint to retrieve logs
@app.get("/api/logs", tags=["logs"])
async def get_logs(limit: int = 100, level: str = None, offset: int = 0):
    """
    Retrieve application logs from memory buffer with pagination.

    Args:
        limit: Maximum number of log entries to return (default: 100)
        level: Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        offset: Number of entries to skip from newest (for lazy loading older logs)

    Returns:
        List of log entries with timestamp, level, logger, and message.
        Also returns total count and whether there are more logs available.
    """
    handler = get_memory_handler()
    if not handler:
        return {"logs": [], "count": 0, "total": 0, "has_more": False, "error": "Log handler not initialized"}

    # Clamp limit to reasonable range (no max limit for lazy loading)
    limit = max(1, limit)
    offset = max(0, offset)

    logs = handler.get_logs(limit=limit, level=level, offset=offset)
    total = handler.get_total_count(level=level)
    has_more = offset + len(logs) < total

    return {"logs": logs, "count": len(logs), "total": total, "has_more": has_more}


@app.delete("/api/logs", tags=["logs"])
async def clear_logs():
    """Clear all logs from the memory buffer."""
    handler = get_memory_handler()
    if handler:
        handler.clear()
    return {"status": "ok", "message": "Logs cleared"}


# FastAPI routes - Redirect old frontend routes to new React frontend on port 80
def get_redirect_response(request: Request):
    """Return redirect page pointing users to the new frontend."""
    host = request.headers.get("host", "localhost").split(":")[0]  # Remove port if present
    return templates.TemplateResponse("redirect.html", {"request": request, "host": host})

@app.get("/")
async def index(request: Request):
    return get_redirect_response(request)

@app.get("/settings")
async def settings_page(request: Request):
    return get_redirect_response(request)

# ============================================================================
# Unified Settings API
# ============================================================================

@app.get("/api/settings", tags=["settings"])
async def get_all_settings():
    """
    Get all application settings in a unified structure.

    This endpoint consolidates multiple settings endpoints into a single response.
    Individual settings endpoints are deprecated but still functional.
    """
    return {
        "app": {
            "name": state.app_name,
            "custom_logo": state.custom_logo
        },
        "patterns": {
            "clear_pattern_speed": state.clear_pattern_speed,
            "custom_clear_from_in": state.custom_clear_from_in,
            "custom_clear_from_out": state.custom_clear_from_out
        },
        "scheduled_pause": {
            "enabled": state.scheduled_pause_enabled,
            "control_wled": state.scheduled_pause_control_wled,
            "finish_pattern": state.scheduled_pause_finish_pattern,
            "timezone": state.scheduled_pause_timezone,
            "time_slots": state.scheduled_pause_time_slots
        },
        "homing": {
            "mode": state.homing,
            "user_override": state.homing_user_override,  # True if user explicitly set, False if auto-detected
            "angular_offset_degrees": state.angular_homing_offset_degrees,
            "home_on_connect": state.home_on_connect,
            "auto_home_enabled": state.auto_home_enabled,
            "auto_home_after_patterns": state.auto_home_after_patterns,
            "hard_reset_theta": state.hard_reset_theta  # Enable hard reset when resetting theta
        },
        "led": {
            "provider": state.led_provider,
            "wled_ip": state.wled_ip,
            "control_mode": state.dw_led_control_mode,
            "idle_timeout_enabled": state.dw_led_idle_timeout_enabled,
            "idle_timeout_minutes": state.dw_led_idle_timeout_minutes
        },
        "mqtt": {
            "enabled": state.mqtt_enabled,
            "broker": state.mqtt_broker,
            "port": state.mqtt_port,
            "username": state.mqtt_username,
            "has_password": bool(state.mqtt_password),
            "client_id": state.mqtt_client_id,
            "discovery_prefix": state.mqtt_discovery_prefix,
            "device_id": state.mqtt_device_id,
            "device_name": state.mqtt_device_name
        },
        "machine": {
            # Kinematics live in the board's config.yaml; the host only keeps a timezone.
            "timezone": state.timezone,
        },
        "security": {
            "mode": state.security_mode,
            "has_password": bool(state.security_password_hash)
        }
    }

@app.get("/api/manifest.webmanifest", tags=["settings"])
async def get_dynamic_manifest():
    """
    Get a dynamically generated web manifest.

    Returns manifest with custom icons and app name if custom branding is configured,
    otherwise returns defaults.
    """
    # Determine icon paths based on whether custom logo exists
    if state.custom_logo:
        icon_base = "/static/custom"
    else:
        icon_base = "/static"

    # Use custom app name or default
    app_name = state.app_name or "Dune Weaver"

    return {
        "name": app_name,
        "short_name": app_name,
        "description": "Control your kinetic sand table",
        "icons": [
            {
                "src": f"{icon_base}/android-chrome-192x192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": f"{icon_base}/android-chrome-512x512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": f"{icon_base}/android-chrome-192x192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "maskable"
            },
            {
                "src": f"{icon_base}/android-chrome-512x512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable"
            }
        ],
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "theme_color": "#0a0a0a",
        "background_color": "#0a0a0a",
        "categories": ["utilities", "entertainment"]
    }

@app.patch("/api/settings", tags=["settings"])
async def update_settings(settings_update: SettingsUpdate):
    """
    Partially update application settings.

    Only include the categories and fields you want to update.
    All fields are optional - only provided values will be updated.

    Example: {"app": {"name": "Dune Weaver"}, "auto_play": {"enabled": true}}
    """
    updated_categories = []
    requires_restart = False
    led_reinit_needed = False
    old_led_provider = state.led_provider

    # App settings
    if settings_update.app:
        if settings_update.app.name is not None:
            state.app_name = settings_update.app.name or "Dune Weaver"
        if settings_update.app.custom_logo is not None:
            state.custom_logo = settings_update.app.custom_logo or None
        updated_categories.append("app")

    # Pattern settings
    if settings_update.patterns:
        p = settings_update.patterns
        if p.clear_pattern_speed is not None:
            state.clear_pattern_speed = p.clear_pattern_speed if p.clear_pattern_speed > 0 else None
        if p.custom_clear_from_in is not None:
            state.custom_clear_from_in = p.custom_clear_from_in or None
        if p.custom_clear_from_out is not None:
            state.custom_clear_from_out = p.custom_clear_from_out or None
        # The firmware runs its own clear files; mirror custom choices onto them.
        if p.custom_clear_from_in is not None or p.custom_clear_from_out is not None:
            board_settings.push_custom_clears_async()
        updated_categories.append("patterns")

    # Scheduled pause (Still Sands) settings
    if settings_update.scheduled_pause:
        sp = settings_update.scheduled_pause
        if sp.enabled is not None:
            state.scheduled_pause_enabled = sp.enabled
        if sp.control_wled is not None:
            state.scheduled_pause_control_wled = sp.control_wled
        if sp.finish_pattern is not None:
            state.scheduled_pause_finish_pattern = sp.finish_pattern
        if sp.timezone is not None:
            # Empty string means use system default (store as None)
            state.scheduled_pause_timezone = sp.timezone if sp.timezone else None
            # Clear cached timezone in pattern_manager so it picks up the new setting
            from modules.core import pattern_manager
            pattern_manager._cached_timezone = None
            pattern_manager._cached_zoneinfo = None
        if sp.time_slots is not None:
            state.scheduled_pause_time_slots = [slot.model_dump() for slot in sp.time_slots]
        updated_categories.append("scheduled_pause")
        # Board NVS is canonical for Still Sands (the mobile apps edit it there);
        # push the new values, plus the timezone so board-local schedules match.
        if state.conn:
            def _push_sands():
                try:
                    board_settings.push_still_sands()
                    if sp.timezone is not None:
                        board_settings.sync_board_time()
                except Exception as e:
                    logger.warning(f"Could not push Still Sands settings to board: {e}")
            asyncio.create_task(asyncio.to_thread(_push_sands))

    # Homing settings
    if settings_update.homing:
        h = settings_update.homing
        if h.mode is not None:
            state.homing = h.mode
            state.homing_user_override = True  # User explicitly set preference
        if h.angular_offset_degrees is not None:
            state.angular_homing_offset_degrees = h.angular_offset_degrees
        if h.home_on_connect is not None:
            state.home_on_connect = h.home_on_connect
        if h.auto_home_enabled is not None:
            state.auto_home_enabled = h.auto_home_enabled
        if h.auto_home_after_patterns is not None:
            state.auto_home_after_patterns = h.auto_home_after_patterns
        if h.hard_reset_theta is not None:
            state.hard_reset_theta = h.hard_reset_theta
        updated_categories.append("homing")
        # Mirror to the board: mode/offset now (idle-gated NVS; also re-pushed on
        # every home), and the auto-home cadence for firmware-sequenced playlists.
        if state.conn:
            def _push_homing():
                try:
                    if h.mode is not None:
                        state.conn.set_homing_mode("crash" if state.homing == 0 else "sensor")
                    if h.angular_offset_degrees is not None:
                        state.conn.set_theta_offset(state.angular_homing_offset_degrees)
                    if h.auto_home_enabled is not None or h.auto_home_after_patterns is not None:
                        board_settings.push_auto_home()
                except Exception as e:
                    logger.warning(f"Could not push homing settings to board: {e}")
            asyncio.create_task(asyncio.to_thread(_push_homing))

    # LED settings
    if settings_update.led:
        led = settings_update.led
        if led.provider is not None:
            state.led_provider = led.provider
            if led.provider != old_led_provider:
                led_reinit_needed = True
        if led.wled_ip is not None:
            state.wled_ip = led.wled_ip or None
        if led.control_mode is not None:
            state.dw_led_control_mode = led.control_mode
        if led.idle_timeout_enabled is not None:
            state.dw_led_idle_timeout_enabled = led.idle_timeout_enabled
        if led.idle_timeout_minutes is not None:
            state.dw_led_idle_timeout_minutes = led.idle_timeout_minutes
        updated_categories.append("led")

    # MQTT settings
    if settings_update.mqtt:
        m = settings_update.mqtt
        if m.enabled is not None:
            state.mqtt_enabled = m.enabled
        if m.broker is not None:
            state.mqtt_broker = m.broker
        if m.port is not None:
            state.mqtt_port = m.port
        if m.username is not None:
            state.mqtt_username = m.username
        if m.password is not None:
            state.mqtt_password = m.password
        if m.client_id is not None:
            state.mqtt_client_id = m.client_id
        if m.discovery_prefix is not None:
            state.mqtt_discovery_prefix = m.discovery_prefix
        if m.device_id is not None:
            state.mqtt_device_id = m.device_id
        if m.device_name is not None:
            state.mqtt_device_name = m.device_name
        updated_categories.append("mqtt")
        requires_restart = True

    # Machine settings (kinematics live in the board's config.yaml; only the
    # host timezone remains)
    if settings_update.machine:
        m = settings_update.machine
        if m.timezone is not None:
            # Validate timezone by trying to create a ZoneInfo object
            try:
                from zoneinfo import ZoneInfo
            except ImportError:
                from backports.zoneinfo import ZoneInfo
            try:
                ZoneInfo(m.timezone)  # Validate
                state.timezone = m.timezone
                # Also update scheduled_pause_timezone to keep in sync
                state.scheduled_pause_timezone = m.timezone
                # Clear cached timezone in pattern_manager so it picks up the new setting
                from modules.core import pattern_manager
                pattern_manager._cached_timezone = None
                pattern_manager._cached_zoneinfo = None
                logger.info(f"Timezone updated to: {m.timezone}")
            except Exception as e:
                logger.warning(f"Invalid timezone '{m.timezone}': {e}")
        updated_categories.append("machine")

    # Security settings
    if settings_update.security:
        sec = settings_update.security
        if sec.mode is not None:
            if sec.mode not in ("off", "lockdown", "play_only"):
                raise HTTPException(status_code=400, detail="Invalid security mode. Must be 'off', 'lockdown', or 'play_only'.")
            state.security_mode = sec.mode
            # When turning off, clear the password hash
            if sec.mode == "off":
                state.security_password_hash = ""
        if sec.password is not None and sec.password != "":
            state.security_password_hash = hashlib.sha256(sec.password.encode('utf-8')).hexdigest()
        updated_categories.append("security")

    # Save state
    state.save()

    # Handle LED reinitialization if provider changed
    if led_reinit_needed:
        logger.info(f"LED provider changed from {old_led_provider} to {state.led_provider}, reinitialization may be needed")

    logger.info(f"Settings updated: {', '.join(updated_categories)}")

    return {
        "success": True,
        "updated_categories": updated_categories,
        "requires_restart": requires_restart,
        "led_reinit_needed": led_reinit_needed
    }

@app.post("/api/security/verify", tags=["settings"])
async def verify_security_password(request: SecurityVerifyRequest):
    """Verify a security password against the stored hash."""
    if not state.security_password_hash:
        return {"valid": False}
    input_hash = hashlib.sha256(request.password.encode('utf-8')).hexdigest()
    return {"valid": input_hash == state.security_password_hash}

# ============================================================================
# Board-owned settings (FluidNC NVS) — proxied for the web UI
# ============================================================================

class AutostartSettingsUpdate(BaseModel):
    playlist: Optional[str] = None  # empty string disables auto-play on boot
    run_mode: Optional[str] = None  # "single" | "loop"
    shuffle: Optional[bool] = None
    pause_seconds: Optional[int] = None
    pause_from_start: Optional[bool] = None
    clear_pattern: Optional[str] = None  # none|adaptive|in|out|sideway|random

class BoardSettingsUpdate(BaseModel):
    autostart: Optional[AutostartSettingsUpdate] = None

@app.get("/api/board/settings", tags=["settings"])
async def get_board_settings():
    """
    Read the board-owned settings (auto-play on boot, homing, clock) straight
    from the FluidNC board's NVS. These fire on table power-on, independent of
    this backend, and are shared with the native mobile apps.
    """
    if not state.conn:
        return {"reachable": False}
    try:
        return await asyncio.to_thread(board_settings.get_board_settings)
    except Exception as e:
        logger.warning(f"Could not read board settings: {e}")
        return {"reachable": False}

@app.patch("/api/board/settings", tags=["settings"])
async def update_board_settings(update: BoardSettingsUpdate):
    """Write board-owned settings ($Playlist/Autostart* family) to the board."""
    if not state.conn:
        raise HTTPException(status_code=409, detail="Not connected to the board")
    try:
        if update.autostart:
            autostart = update.autostart.model_dump(exclude_none=True)
            await asyncio.to_thread(board_settings.apply_autostart, autostart)
            # A newly selected boot playlist must exist on the board SD, with
            # all of its patterns, before the next power-on.
            playlist_name = autostart.get("playlist")
            if playlist_name:
                playlist = playlist_manager.get_playlist(playlist_name)
                if playlist:
                    asyncio.create_task(asyncio.to_thread(
                        board_settings.mirror_playlist,
                        playlist_name, playlist["files"], None, True,
                    ))
        return {"success": True}
    except Exception as e:
        logger.warning(f"Could not write board settings: {e}")
        raise HTTPException(status_code=502, detail=f"Board rejected the update: {e}")

class BoardCommandRequest(BaseModel):
    command: str

@app.get("/api/firmware/version", tags=["settings"])
async def firmware_version():
    """Board firmware version + latest published release (GitHub, cached)."""
    from modules.update import firmware_updater
    release = await asyncio.to_thread(firmware_updater.get_latest_release)
    current = state.firmware_version
    latest = release["version"] if release else None
    return {
        "current": current,
        "latest": latest,
        "update_available": bool(release and firmware_updater.is_newer(latest, current)),
        "release_url": release["release_url"] if release else None,
    }

@app.post("/api/firmware/update", tags=["settings"])
async def firmware_update():
    """Flash the latest firmware release onto the board over OTA and wait for
    it to reboot. A failed/interrupted upload leaves the old image running."""
    from modules.update import firmware_updater
    if not state.conn or not state.conn.is_connected():
        raise HTTPException(status_code=409, detail="Not connected to the board")
    if execution.get_cached_status().get("is_running"):
        raise HTTPException(status_code=409, detail="Stop the current pattern first")

    probe = await asyncio.to_thread(state.conn.update_probe)
    if probe.get("status") == "busy":
        raise HTTPException(status_code=409, detail="The table is busy - stop the current pattern first")
    if probe.get("status") != "ready":
        raise HTTPException(
            status_code=400,
            detail="This firmware is too old for OTA updates - update it once via the web installer")

    release = await asyncio.to_thread(firmware_updater.get_latest_release, True)
    if not release:
        raise HTTPException(status_code=502, detail="Could not fetch the latest firmware release")
    try:
        image = await asyncio.to_thread(firmware_updater.download_image, release["download_url"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Firmware download failed: {e}")

    # The board's web server is single-threaded: suspend the status poller for
    # the whole flash + reboot window.
    execution.observer.suspended = True
    try:
        logger.info(f"Flashing firmware {release['version']} ({len(image)} bytes) to the board")
        result = await asyncio.to_thread(state.conn.upload_firmware, image)
        if result.get("status") != "ok":
            detail = ("The table is busy - stop the current pattern first"
                      if result.get("status") == "busy" else "The table rejected the update")
            raise HTTPException(status_code=502, detail=detail)

        # Board reboots ~1s after "ok"; give it a head start, then poll.
        await asyncio.sleep(8)
        deadline = time.time() + 120
        while True:
            try:
                st = await asyncio.to_thread(state.conn.get_status)
                state.firmware_version = st.get("fw") or state.firmware_version
                logger.info(f"Firmware update complete - board reports {state.firmware_version}")
                return {"success": True, "version": state.firmware_version}
            except Exception:
                if time.time() > deadline:
                    raise HTTPException(
                        status_code=504,
                        detail="Update sent, but the table has not come back online - check it in a minute")
                await asyncio.sleep(3)
    finally:
        execution.observer.suspended = False

# --- Table (board) Wi-Fi management — fw >= v0.1.8 --------------------------
# Distinct from /api/wifi/* (the host Pi's Wi-Fi): these reconfigure the
# FluidNC board's own network. Writes can reboot the board; the observer's
# reconnect/relocate watchdog re-finds it afterwards (by MAC via mDNS).

def _require_board():
    if not state.conn or not state.conn.is_connected():
        raise HTTPException(status_code=409, detail="Not connected to the board")

@app.get("/api/board/wifi/status", tags=["settings"])
async def board_wifi_status():
    _require_board()
    try:
        status = await asyncio.to_thread(state.conn.wifi_status)
        return {"supported": True, **status}
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return {"supported": False}
        raise HTTPException(status_code=502, detail=f"Wi-Fi status failed: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Wi-Fi status failed: {e}")

@app.get("/api/board/wifi/scan", tags=["settings"])
async def board_wifi_scan(rescan: bool = False):
    """Async scan: returns {status:'scanning'} until results are ready - poll."""
    _require_board()
    try:
        return await asyncio.to_thread(state.conn.wifi_scan, rescan)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Wi-Fi scan failed: {e}")

class BoardWifiSaveRequest(BaseModel):
    ssid: str
    password: str

@app.post("/api/board/wifi/save", tags=["settings"])
async def board_wifi_save(request: BoardWifiSaveRequest):
    """Point the table at a home Wi-Fi network. The table reboots; a lost
    reply means the reboot raced the response and is treated as success
    (same as the mobile app / captive portal)."""
    _require_board()
    if not request.ssid.strip():
        raise HTTPException(status_code=400, detail="SSID is required")
    if not (8 <= len(request.password) <= 64):
        raise HTTPException(status_code=400, detail="Password must be 8-64 characters")
    try:
        result = await asyncio.to_thread(
            state.conn.wifi_save, request.ssid.strip(), request.password)
    except Exception:
        # Reboot raced the reply - the write almost certainly landed.
        return {"success": True, "rebooting": True}
    if result.get("status") == "busy":
        raise HTTPException(status_code=409, detail="The table is busy - stop the current pattern first")
    if result.get("status") == "error":
        raise HTTPException(status_code=502, detail=result.get("message") or "The table rejected those credentials")
    return {"success": True, "rebooting": bool(result.get("reboot"))}

@app.post("/api/board/wifi/standalone", tags=["settings"])
async def board_wifi_standalone():
    """Switch the table to standalone hotspot mode ($WiFi/Mode=AP). From home
    Wi-Fi the table reboots and leaves this network."""
    _require_board()
    try:
        result = await asyncio.to_thread(state.conn.wifi_standalone)
    except Exception:
        return {"success": True, "rebooting": True}
    if result.get("status") == "busy":
        raise HTTPException(status_code=409, detail="The table is busy - stop the current pattern first")
    if result.get("status") == "error":
        raise HTTPException(status_code=502, detail=result.get("message") or "Could not switch to standalone mode")
    return {"success": True, "rebooting": bool(result.get("reboot"))}

class RotateRequest(BaseModel):
    theta: float  # absolute target, radians

@app.post("/api/board/rotate", tags=["settings"])
async def board_rotate(request: RotateRequest):
    """Jog the arm to an absolute theta at the perimeter (crash-homing
    orientation alignment). The firmware answers 409 while a previous jog is
    still finishing — the client retries."""
    if not state.conn or not state.conn.is_connected():
        raise HTTPException(status_code=409, detail="Not connected to the board")
    try:
        await asyncio.to_thread(state.conn.goto, request.theta, 1.0)
        return {"success": True}
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else 502
        raise HTTPException(status_code=code if code in (401, 409) else 502,
                            detail=f"Rotate rejected: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Rotate failed: {e}")

@app.get("/api/board/logs", tags=["settings"])
async def board_logs(limit: int = 500):
    """Persistent table log history harvested from the board's /sand_log ring
    buffer by the observer (outlives board reboots, unlike the ring itself)."""
    try:
        with open(execution.BOARD_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        lines = []
    return {"lines": lines[-max(1, min(limit, execution.BOARD_LOG_MAX_LINES)):]}

@app.get("/api/board/bootlog", tags=["settings"])
async def board_bootlog():
    """The board's boot log ($SS startup log). After a panic it preserves the
    *previous* boot's log — the on-device crash breadcrumb. Read live."""
    if not state.conn or not state.conn.is_connected():
        raise HTTPException(status_code=409, detail="Not connected to the board")
    try:
        text = await asyncio.to_thread(state.conn.get_bootlog)
        return {"text": text}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not read boot log: {e}")

@app.get("/api/board/coredump", tags=["settings"])
async def board_coredump():
    """JSON crash report from the coredump partition, written on any panic
    (incl. task-WDT hang). {present, task, pc, backtrace, ...}. Read live."""
    if not state.conn or not state.conn.is_connected():
        raise HTTPException(status_code=409, detail="Not connected to the board")
    try:
        return await asyncio.to_thread(state.conn.get_coredump)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not read coredump: {e}")

@app.post("/api/board/coredump/erase", tags=["settings"])
async def board_coredump_erase():
    """Clear the stored coredump so a fresh crash is unambiguous."""
    if not state.conn or not state.conn.is_connected():
        raise HTTPException(status_code=409, detail="Not connected to the board")
    try:
        await asyncio.to_thread(state.conn.erase_coredump)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not erase coredump: {e}")

@app.post("/api/board/unlock", tags=["settings"])
async def board_unlock():
    """Clear a GRBL Alarm state ($X) so the table accepts commands again."""
    if not state.conn or not state.conn.is_connected():
        raise HTTPException(status_code=409, detail="Not connected to the board")
    try:
        await asyncio.to_thread(state.conn.run_command, "$X")
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Unlock failed: {e}")

@app.post("/api/board/restart", tags=["settings"])
async def board_restart():
    """Reboot the DLC32 controller (FluidNC) via $Bye. Position is lost, so the
    table re-homes on the way back up. The observer's reconnect watchdog picks
    the board back up once it's finished rebooting."""
    if not state.conn or not state.conn.is_connected():
        raise HTTPException(status_code=409, detail="Not connected to the board")
    # A lost reply just means the reboot raced the "ok" response — the board is
    # restarting either way, so (like the Wi-Fi endpoints) we treat it as success.
    await connection_manager.perform_soft_reset()
    return {"success": True, "rebooting": True}

class BoardPasswordRequest(BaseModel):
    # 'set' writes $Sand/Password on the board and stores it locally;
    # 'remove' clears it on the board and locally;
    # 'save_local' only verifies + stores an existing password on this backend.
    action: str
    password: Optional[str] = None

@app.post("/api/board/password", tags=["settings"])
async def board_password(request: BoardPasswordRequest):
    """Manage the table's API password ($Sand/Password, fw >= v0.1.11)."""
    action = request.action
    password = (request.password or "").strip()
    if action not in ("set", "remove", "save_local"):
        raise HTTPException(status_code=400, detail="Unknown action")
    if action in ("set", "save_local") and not (4 <= len(password) <= 64):
        raise HTTPException(status_code=400, detail="Password must be 4-64 characters")

    if action == "save_local":
        # Verify against the board (which may currently be rejecting us).
        from modules.connection.fluidnc_client import FluidNCClient
        probe = state.conn or FluidNCClient(connection_manager.board_url())
        try:
            ok = await asyncio.to_thread(probe.test_key, password)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Could not reach the table: {e}")
        if not ok:
            raise HTTPException(status_code=401, detail="Wrong password")
        state.board_api_key = password
        state.board_locked = False
        if state.conn:
            state.conn.api_key = password
        state.save()
        return {"success": True}

    if not state.conn or not state.conn.is_connected():
        raise HTTPException(status_code=409, detail="Not connected to the board")
    try:
        resp = await asyncio.to_thread(state.conn.set_password,
                                       password if action == "set" else "")
        if "error" in (resp or "").lower():
            raise HTTPException(status_code=502, detail=f"Board rejected the change: {resp.strip()}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to update the table password: {e}")
    state.board_api_key = password if action == "set" else None
    state.conn.api_key = state.board_api_key
    state.board_locked = False
    state.save()
    return {"success": True}

@app.post("/api/board/command", tags=["settings"])
async def board_command(request: BoardCommandRequest):
    """Advanced console: send a $-command to the board and return the recent
    session log (the board streams command output to its log, not HTTP)."""
    if not state.conn:
        raise HTTPException(status_code=409, detail="Not connected to the board")
    command = request.command.strip()
    if not command:
        raise HTTPException(status_code=400, detail="Empty command")
    try:
        response = await asyncio.to_thread(state.conn.run_command, command)
        log_tail = ""
        try:
            log_text = await asyncio.to_thread(
                lambda: state.conn._get("/sand_log").text)
            log_tail = "\n".join(log_text.strip().splitlines()[-15:])
        except Exception:
            pass
        responses = [line for line in (response or "").strip().splitlines() if line]
        return {"success": True, "responses": responses, "log": log_tail}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Board command failed: {e}")

@app.post("/api/board/sync_time", tags=["settings"])
async def sync_board_time():
    """Push the host's clock and timezone to the board (quiet hours need it)."""
    if not state.conn:
        raise HTTPException(status_code=409, detail="Not connected to the board")
    try:
        result = await asyncio.to_thread(board_settings.sync_board_time)
        return {"success": True, "time": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Clock sync failed: {e}")

# ============================================================================
# Multi-Table Identity Endpoints
# ============================================================================

class TableInfoUpdate(BaseModel):
    name: Optional[str] = None

class KnownTableAdd(BaseModel):
    id: str
    name: str
    url: str
    host: Optional[str] = None
    port: Optional[int] = None
    version: Optional[str] = None

class KnownTableUpdate(BaseModel):
    name: Optional[str] = None

@app.get("/api/table-info", tags=["multi-table"])
async def get_table_info():
    """
    Get table identity information for multi-table discovery.

    Returns the table's unique ID, name, and version.
    """
    return {
        "id": state.table_id,
        "name": state.table_name,
        "version": await version_manager.get_current_version()
    }

@app.patch("/api/table-info", tags=["multi-table"])
async def update_table_info(update: TableInfoUpdate):
    """
    Update table identity information.

    Currently only the table name can be updated.
    The table ID is immutable after generation.
    """
    if update.name is not None:
        state.table_name = update.name.strip() or "Dune Weaver"
        state.save()
        logger.info(f"Table name updated to: {state.table_name}")
        await mdns_discovery.update_name(state.table_name)

    return {
        "success": True,
        "id": state.table_id,
        "name": state.table_name
    }

@app.get("/api/discovered-tables", tags=["multi-table"])
async def get_discovered_tables():
    """
    Get Dune Weaver tables auto-discovered via mDNS on the local network.

    Unlike known-tables these are not persisted - the list reflects which
    peer backends are currently advertising themselves. Returns an empty
    list when mDNS is unavailable (e.g. zeroconf not installed).
    """
    return {"tables": mdns_discovery.get_tables()}

@app.get("/api/discovered-boards", tags=["multi-table"])
async def get_discovered_boards():
    """
    Get FluidNC controller boards auto-discovered via mDNS (_http._tcp with
    the firmware's sandtable TXT records) - candidates for /connect. Unlike
    /api/discovered-tables (peer backends), these are the boards themselves.
    Returns an empty list when mDNS is unavailable.
    """
    return {"boards": mdns_discovery.get_boards()}

@app.get("/api/known-tables", tags=["multi-table"])
async def get_known_tables():
    """
    Get list of known remote tables.

    These are tables that have been manually added and are persisted
    for multi-table management.
    """
    return {"tables": state.known_tables}

@app.post("/api/known-tables", tags=["multi-table"])
async def add_known_table(table: KnownTableAdd):
    """
    Add a known remote table.

    This persists the table information so it's available across
    browser sessions and devices.
    """
    # Check if table with same ID already exists
    existing_ids = [t.get("id") for t in state.known_tables]
    if table.id in existing_ids:
        raise HTTPException(status_code=400, detail="Table with this ID already exists")

    # Check if table with same URL already exists
    existing_urls = [t.get("url") for t in state.known_tables]
    if table.url in existing_urls:
        raise HTTPException(status_code=400, detail="Table with this URL already exists")

    new_table = {
        "id": table.id,
        "name": table.name,
        "url": table.url,
    }
    if table.host:
        new_table["host"] = table.host
    if table.port:
        new_table["port"] = table.port
    if table.version:
        new_table["version"] = table.version

    state.known_tables.append(new_table)
    state.save()
    logger.info(f"Added known table: {table.name} ({table.url})")

    return {"success": True, "table": new_table}

@app.delete("/api/known-tables/{table_id}", tags=["multi-table"])
async def remove_known_table(table_id: str):
    """
    Remove a known remote table by ID.
    """
    original_count = len(state.known_tables)
    state.known_tables = [t for t in state.known_tables if t.get("id") != table_id]

    if len(state.known_tables) == original_count:
        raise HTTPException(status_code=404, detail="Table not found")

    state.save()
    logger.info(f"Removed known table: {table_id}")

    return {"success": True}

@app.patch("/api/known-tables/{table_id}", tags=["multi-table"])
async def update_known_table(table_id: str, update: KnownTableUpdate):
    """
    Update a known remote table's name.
    """
    for table in state.known_tables:
        if table.get("id") == table_id:
            if update.name is not None:
                table["name"] = update.name.strip()
            state.save()
            logger.info(f"Updated known table {table_id}: name={update.name}")
            return {"success": True, "table": table}

    raise HTTPException(status_code=404, detail="Table not found")

# ============================================================================
# Individual Settings Endpoints (Deprecated - use /api/settings instead)
# ============================================================================

@app.get("/api/scheduled-pause", deprecated=True, tags=["settings-deprecated"])
async def get_scheduled_pause():
    """DEPRECATED: Use GET /api/settings instead. Get current Still Sands settings."""
    return {
        "enabled": state.scheduled_pause_enabled,
        "control_wled": state.scheduled_pause_control_wled,
        "finish_pattern": state.scheduled_pause_finish_pattern,
        "timezone": state.scheduled_pause_timezone,
        "time_slots": state.scheduled_pause_time_slots
    }

@app.post("/api/scheduled-pause", deprecated=True, tags=["settings-deprecated"])
async def set_scheduled_pause(request: ScheduledPauseRequest):
    """Update Still Sands settings."""
    try:
        # Validate time slots
        for i, slot in enumerate(request.time_slots):
            # Validate time format (HH:MM)
            try:
                datetime.strptime(slot.start_time, "%H:%M")
                datetime.strptime(slot.end_time, "%H:%M")
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid time format in slot {i+1}. Use HH:MM format."
                )

            # Validate days setting
            if slot.days not in ["daily", "weekdays", "weekends", "custom"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid days setting in slot {i+1}. Must be 'daily', 'weekdays', 'weekends', or 'custom'."
                )

            # Validate custom days if applicable
            if slot.days == "custom":
                if not slot.custom_days or len(slot.custom_days) == 0:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Custom days must be specified for slot {i+1} when days is set to 'custom'."
                    )

                valid_days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                for day in slot.custom_days:
                    if day not in valid_days:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Invalid day '{day}' in slot {i+1}. Valid days are: {', '.join(valid_days)}"
                        )

        # Update state
        state.scheduled_pause_enabled = request.enabled
        state.scheduled_pause_control_wled = request.control_wled
        state.scheduled_pause_finish_pattern = request.finish_pattern
        state.scheduled_pause_timezone = request.timezone if request.timezone else None
        state.scheduled_pause_time_slots = [slot.model_dump() for slot in request.time_slots]
        state.save()

        # Clear cached timezone so it picks up the new setting
        from modules.core import pattern_manager
        pattern_manager._cached_timezone = None
        pattern_manager._cached_zoneinfo = None

        wled_msg = " (with WLED control)" if request.control_wled else ""
        finish_msg = " (finish pattern first)" if request.finish_pattern else ""
        tz_msg = f" (timezone: {request.timezone})" if request.timezone else ""
        logger.info(f"Still Sands {'enabled' if request.enabled else 'disabled'} with {len(request.time_slots)} time slots{wled_msg}{finish_msg}{tz_msg}")
        return {"success": True, "message": "Still Sands settings updated"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating Still Sands settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update Still Sands settings: {str(e)}")

@app.get("/api/homing-config", deprecated=True, tags=["settings-deprecated"])
async def get_homing_config():
    """Get homing configuration (mode, compass offset, and auto-home settings)."""
    return {
        "homing_mode": state.homing,
        "angular_homing_offset_degrees": state.angular_homing_offset_degrees,
        "auto_home_enabled": state.auto_home_enabled,
        "auto_home_after_patterns": state.auto_home_after_patterns
    }

class HomingConfigRequest(BaseModel):
    homing_mode: int = 0  # 0 = crash, 1 = sensor
    angular_homing_offset_degrees: float = 0.0
    auto_home_enabled: Optional[bool] = None
    auto_home_after_patterns: Optional[int] = None

@app.post("/api/homing-config", deprecated=True, tags=["settings-deprecated"])
async def set_homing_config(request: HomingConfigRequest):
    """Set homing configuration (mode, compass offset, and auto-home settings)."""
    try:
        # Validate homing mode
        if request.homing_mode not in [0, 1]:
            raise HTTPException(status_code=400, detail="Homing mode must be 0 (crash) or 1 (sensor)")

        state.homing = request.homing_mode
        state.homing_user_override = True  # User explicitly set preference
        state.angular_homing_offset_degrees = request.angular_homing_offset_degrees

        # Update auto-home settings if provided
        if request.auto_home_enabled is not None:
            state.auto_home_enabled = request.auto_home_enabled
        if request.auto_home_after_patterns is not None:
            if request.auto_home_after_patterns < 1:
                raise HTTPException(status_code=400, detail="Auto-home after patterns must be at least 1")
            state.auto_home_after_patterns = request.auto_home_after_patterns

        state.save()

        mode_name = "crash" if request.homing_mode == 0 else "sensor"
        logger.info(f"Homing mode set to {mode_name}, compass offset set to {request.angular_homing_offset_degrees}°")
        if request.auto_home_enabled is not None:
            logger.info(f"Auto-home enabled: {state.auto_home_enabled}, after {state.auto_home_after_patterns} patterns")
        return {"success": True, "message": "Homing configuration updated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating homing configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update homing configuration: {str(e)}")

@app.get("/list_serial_ports")
async def list_ports():
    # Legacy route name kept for the frontend/touch-app contract; there are no
    # serial ports — it returns the board's HTTP URL as the single "port".
    logger.debug("Listing board URLs")
    return await asyncio.to_thread(connection_manager.list_board_urls)

@app.post("/connect")
async def connect(request: ConnectRequest):
    # `request.port` carries the board address now (a URL or bare IP). Blank =>
    # use the configured/default board URL.
    from modules.connection.fluidnc_client import FluidNCClient
    try:
        url = connection_manager._normalize_board_url(request.port or "") or connection_manager.board_url()
        state.board_url = url
        state.port = url
        state.user_disconnected = False
        if request.password is not None:
            state.board_api_key = request.password.strip() or None
        state.save()
        state.conn = FluidNCClient(url, api_key=state.board_api_key)
        if not state.conn.reachable():
            state.board_locked = state.conn.locked
            state.conn = None
            if state.board_locked:
                raise HTTPException(
                    status_code=401,
                    detail="The table is password-protected - enter its password to connect")
            raise HTTPException(status_code=500, detail=f"Board not reachable at {url}")
        state.board_locked = False
        if not await asyncio.to_thread(connection_manager.device_init, False):
            raise HTTPException(status_code=500, detail="Failed to initialize board")
        logger.info(f"Successfully connected to board at {url}")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to connect to board: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/disconnect")
async def disconnect():
    try:
        state.user_disconnected = True  # suppress the observer's auto-reconnect
        state.conn.close()
        logger.info('Successfully disconnected from board')
        return {"success": True}
    except Exception as e:
        logger.error(f'Failed to disconnect from board: {str(e)}')
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/restart_connection")
async def restart(request: ConnectRequest):
    if not request.port:
        logger.warning("Restart connection request received without a board address")
        raise HTTPException(status_code=400, detail="No port provided")

    try:
        logger.info(f"Restarting connection to board {request.port}")
        connection_manager.restart_connection()
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to restart connection to board {request.port}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/list_theta_rho_files")
async def list_theta_rho_files():
    logger.debug("Listing theta-rho files")
    # Run the blocking file system operation in a thread pool
    files = await asyncio.to_thread(pattern_manager.list_theta_rho_files)
    return sorted(files)

@app.get("/list_theta_rho_files_with_metadata")
async def list_theta_rho_files_with_metadata():
    """Get list of theta-rho files with metadata for sorting and filtering.
    
    Optimized to process files asynchronously and support request cancellation.
    """
    from modules.core.cache_manager import get_pattern_metadata
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    
    # Run the blocking file listing in a thread
    files = await asyncio.to_thread(pattern_manager.list_theta_rho_files)
    files_with_metadata = []

    # Use ThreadPoolExecutor for I/O-bound operations
    executor = ThreadPoolExecutor(max_workers=4)
    
    def process_file(file_path):
        """Process a single file and return its metadata."""
        try:
            full_path = os.path.join(pattern_manager.THETA_RHO_DIR, file_path)
            
            # Get file stats
            file_stat = os.stat(full_path)
            
            # Get cached metadata (this should be fast if cached)
            metadata = get_pattern_metadata(file_path)
            
            # Extract full folder path from file path
            path_parts = file_path.split('/')
            if len(path_parts) > 1:
                # Get everything except the filename (join all folder parts)
                category = '/'.join(path_parts[:-1])
            else:
                category = 'root'
            
            # Get file name without extension
            file_name = os.path.splitext(os.path.basename(file_path))[0]
            
            # Use modification time (mtime) for "date modified"
            date_modified = file_stat.st_mtime
            
            return {
                'path': file_path,
                'name': file_name,
                'category': category,
                'date_modified': date_modified,
                'coordinates_count': metadata.get('total_coordinates', 0) if metadata else 0
            }
            
        except Exception as e:
            logger.warning(f"Error getting metadata for {file_path}: {str(e)}")
            # Include file with minimal info if metadata fails
            path_parts = file_path.split('/')
            if len(path_parts) > 1:
                category = '/'.join(path_parts[:-1])
            else:
                category = 'root'
            return {
                'path': file_path,
                'name': os.path.splitext(os.path.basename(file_path))[0],
                'category': category,
                'date_modified': 0,
                'coordinates_count': 0
            }
    
    # Load the entire metadata cache at once (async)
    # This is much faster than 1000+ individual metadata lookups
    try:
        import json
        metadata_cache_path = "metadata_cache.json"
        # Use async file reading to avoid blocking the event loop
        cache_data = await asyncio.to_thread(lambda: json.load(open(metadata_cache_path, 'r')))
        cache_dict = cache_data.get('data', {})
        logger.debug(f"Loaded metadata cache with {len(cache_dict)} entries")

        # Process all files using cached data only
        for file_path in files:
            try:
                # Extract category from path
                path_parts = file_path.split('/')
                category = '/'.join(path_parts[:-1]) if len(path_parts) > 1 else 'root'

                # Get file name without extension
                file_name = os.path.splitext(os.path.basename(file_path))[0]

                # Get metadata from cache
                cached_entry = cache_dict.get(file_path, {})
                if isinstance(cached_entry, dict) and 'metadata' in cached_entry:
                    metadata = cached_entry['metadata']
                    coords_count = metadata.get('total_coordinates', 0)
                    date_modified = cached_entry.get('mtime', 0)
                else:
                    coords_count = 0
                    date_modified = 0

                files_with_metadata.append({
                    'path': file_path,
                    'name': file_name,
                    'category': category,
                    'date_modified': date_modified,
                    'coordinates_count': coords_count
                })

            except Exception as e:
                logger.warning(f"Error processing {file_path}: {e}")
                # Include file with minimal info if processing fails
                path_parts = file_path.split('/')
                category = '/'.join(path_parts[:-1]) if len(path_parts) > 1 else 'root'
                files_with_metadata.append({
                    'path': file_path,
                    'name': os.path.splitext(os.path.basename(file_path))[0],
                    'category': category,
                    'date_modified': 0,
                    'coordinates_count': 0
                })

    except Exception as e:
        logger.error(f"Failed to load metadata cache, falling back to slow method: {e}")
        # Fallback to original method if cache loading fails
        # Create tasks only when needed
        loop = asyncio.get_running_loop()
        tasks = [loop.run_in_executor(executor, process_file, file_path) for file_path in files]

        for task in asyncio.as_completed(tasks):
            try:
                result = await task
                files_with_metadata.append(result)
            except Exception as task_error:
                logger.error(f"Error processing file: {str(task_error)}")

    # Clean up executor
    executor.shutdown(wait=False)

    return files_with_metadata

@app.post("/upload_theta_rho")
async def upload_theta_rho(file: UploadFile = File(...)):
    """Upload a theta-rho file."""
    try:
        # Save the file
        # Ensure custom_patterns directory exists
        custom_patterns_dir = os.path.join(pattern_manager.THETA_RHO_DIR, "custom_patterns")
        os.makedirs(custom_patterns_dir, exist_ok=True)
        
        # Use forward slashes for internal path representation to maintain consistency
        file_path_in_patterns_dir = f"custom_patterns/{file.filename}"
        full_file_path = os.path.join(pattern_manager.THETA_RHO_DIR, file_path_in_patterns_dir)
        
        # Save the uploaded file with proper encoding for Windows compatibility
        file_content = await file.read()
        try:
            # First try to decode as UTF-8 and re-encode to ensure proper encoding
            text_content = file_content.decode('utf-8')
            with open(full_file_path, "w", encoding='utf-8') as f:
                f.write(text_content)
        except UnicodeDecodeError:
            # If UTF-8 decoding fails, save as binary (fallback)
            with open(full_file_path, "wb") as f:
                f.write(file_content)
        
        logger.info(f"File {file.filename} saved successfully")
        
        # Generate image preview for the new file with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"Generating preview for {file_path_in_patterns_dir} (attempt {attempt + 1}/{max_retries})")
                success = await generate_image_preview(file_path_in_patterns_dir)
                if success:
                    logger.info(f"Preview generated successfully for {file_path_in_patterns_dir}")
                    break
                else:
                    logger.warning(f"Preview generation failed for {file_path_in_patterns_dir} (attempt {attempt + 1})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.5)  # Small delay before retry
            except Exception as e:
                logger.error(f"Error generating preview for {file_path_in_patterns_dir} (attempt {attempt + 1}): {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5)  # Small delay before retry
        
        return {"success": True, "message": f"File {file.filename} uploaded successfully"}
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/get_theta_rho_coordinates")
async def get_theta_rho_coordinates(request: GetCoordinatesRequest):
    """Get theta-rho coordinates for animated preview."""
    try:
        # Normalize file path for cross-platform compatibility and remove prefixes
        file_name = normalize_file_path(request.file_name)
        file_path = os.path.join(THETA_RHO_DIR, file_name)

        # Check if we can use cached coordinates (already loaded for current playback)
        # This avoids re-parsing large files (2MB+) which can cause issues on Pi Zero 2W
        current_file = state.current_playing_file
        if current_file and state._current_coordinates:
            # Normalize current file path for comparison
            current_normalized = normalize_file_path(current_file)
            if current_normalized == file_name:
                logger.debug(f"Using cached coordinates for {file_name}")
                return {
                    "success": True,
                    "coordinates": state._current_coordinates,
                    "total_points": len(state._current_coordinates)
                }

        # Check file existence asynchronously
        exists = await asyncio.to_thread(os.path.exists, file_path)
        if not exists:
            raise HTTPException(status_code=404, detail=f"File {file_name} not found")

        # Parse the theta-rho file in a thread (not process) to avoid memory pressure
        # on resource-constrained devices like Pi Zero 2W
        coordinates = await asyncio.to_thread(parse_theta_rho_file, file_path)

        if not coordinates:
            raise HTTPException(status_code=400, detail="No valid coordinates found in file")

        return {
            "success": True,
            "coordinates": coordinates,
            "total_points": len(coordinates)
        }

    except Exception as e:
        logger.error(f"Error getting coordinates for {request.file_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/run_theta_rho")
async def run_theta_rho(request: ThetaRhoRequest):
    """Run one pattern. The firmware sequences the pre-execution clear
    ($Sand/Run clear=<mode>) and aborts any current job first."""
    if not request.file_name:
        logger.warning('Run theta-rho request received without file name')
        raise HTTPException(status_code=400, detail="No file name provided")

    normalized_file_name = normalize_file_path(request.file_name)
    file_path = os.path.join(pattern_manager.THETA_RHO_DIR, normalized_file_name)
    if not os.path.exists(file_path):
        logger.error(f'Theta-rho file not found: {file_path}')
        raise HTTPException(status_code=404, detail="File not found")

    if not (state.conn.is_connected() if state.conn else False):
        logger.warning("Attempted to run a pattern without a connection")
        raise HTTPException(status_code=400, detail="Connection not established")
    check_homing_in_progress()

    try:
        await execution.run_pattern(file_path, request.pre_execution)
        return {"success": True}
    except execution.ExecutionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f'Failed to run theta-rho file {request.file_name}: {str(e)}')
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/stop_execution")
async def stop_execution():
    if not (state.conn.is_connected() if state.conn else False):
        logger.warning("Attempted to stop without a connection")
        raise HTTPException(status_code=400, detail="Connection not established")
    try:
        success = await execution.stop()
    except execution.ExecutionError as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not success:
        raise HTTPException(status_code=500, detail="Stop timed out - use force_stop")
    return {"success": True}

@app.post("/force_stop")
async def force_stop():
    """Best-effort board stop + unconditional host-state reset. Use when the
    normal stop doesn't come back."""
    logger.info("Force stop requested - clearing all run state")
    await execution.stop(force=True)
    state.is_homing = False
    return {"success": True, "message": "Force stop completed"}

@app.post("/soft_reset")
async def soft_reset():
    """Send $Bye soft reset to FluidNC controller. Resets position counters to 0."""
    if not (state.conn and state.conn.is_connected()):
        logger.warning("Attempted to soft reset without a connection")
        raise HTTPException(status_code=400, detail="Connection not established")

    try:
        # Stop any running patterns first
        await execution.stop(force=True)

        # Use the shared soft reset function
        await connection_manager.perform_soft_reset()

        return {"success": True, "message": "Soft reset sent. Position reset to 0."}
    except Exception as e:
        logger.error(f"Error sending soft reset: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/send_home")
async def send_home():
    try:
        if not (state.conn.is_connected() if state.conn else False):
            logger.warning("Attempted to move to home without a connection")
            raise HTTPException(status_code=400, detail="Connection not established")

        if state.is_homing:
            raise HTTPException(status_code=409, detail="Homing already in progress")

        # Set homing flag to block other movement operations
        state.is_homing = True
        logger.info("Homing started - blocking other movement operations")

        try:
            # Run homing with 15 second timeout
            success = await asyncio.to_thread(connection_manager.home)
            if not success:
                logger.error("Homing failed or timed out")
                raise HTTPException(status_code=500, detail="Homing failed or timed out after 15 seconds")

            return {"success": True}
        finally:
            # Always clear homing flag when done (success or failure)
            state.is_homing = False
            logger.info("Homing completed - movement operations unblocked")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send home command: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

class SensorHomingRecoveryRequest(BaseModel):
    switch_to_crash_homing: bool = False

@app.post("/recover_sensor_homing")
async def recover_sensor_homing(request: SensorHomingRecoveryRequest):
    """
    Recover from sensor homing failure.

    If switch_to_crash_homing is True, changes homing mode to crash homing (mode 0)
    and saves the setting. Then attempts to reconnect and home the device.

    If switch_to_crash_homing is False, just clears the failure flag and retries
    with sensor homing.
    """
    try:
        # Clear the sensor homing failure flag first
        state.sensor_homing_failed = False

        if request.switch_to_crash_homing:
            # Switch to crash homing mode
            logger.info("Switching to crash homing mode per user request")
            state.homing = 0
            state.homing_user_override = True
            state.save()

        # If already connected, just perform homing
        if state.conn and state.conn.is_connected():
            logger.info("Device already connected, performing homing...")
            state.is_homing = True
            try:
                success = await asyncio.to_thread(connection_manager.home)
                if not success:
                    # Check if sensor homing failed again
                    if state.sensor_homing_failed:
                        return {
                            "success": False,
                            "sensor_homing_failed": True,
                            "message": "Sensor homing failed again. Please check sensor position or switch to crash homing."
                        }
                    return {"success": False, "message": "Homing failed"}
                return {"success": True, "message": "Homing completed successfully"}
            finally:
                state.is_homing = False
        else:
            # Need to reconnect
            logger.info("Reconnecting device and performing homing...")
            state.is_homing = True
            try:
                # connect_device includes homing
                await asyncio.to_thread(connection_manager.connect_device, True)

                # Check if sensor homing failed during connection
                if state.sensor_homing_failed:
                    return {
                        "success": False,
                        "sensor_homing_failed": True,
                        "message": "Sensor homing failed. Please check sensor position or switch to crash homing."
                    }

                if state.conn and state.conn.is_connected():
                    return {"success": True, "message": "Connected and homed successfully"}
                else:
                    return {"success": False, "message": "Failed to establish connection"}
            finally:
                state.is_homing = False

    except Exception as e:
        logger.error(f"Error during sensor homing recovery: {e}")
        state.is_homing = False
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/run_theta_rho_file/{file_name}")
async def run_specific_theta_rho_file(file_name: str):
    file_path = os.path.join(pattern_manager.THETA_RHO_DIR, file_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    if not (state.conn.is_connected() if state.conn else False):
        logger.warning("Attempted to run a pattern without a connection")
        raise HTTPException(status_code=400, detail="Connection not established")

    check_homing_in_progress()

    await execution.run_pattern(file_path)
    return {"success": True}

class DeleteFileRequest(BaseModel):
    file_name: str

@app.post("/delete_theta_rho_file")
async def delete_theta_rho_file(request: DeleteFileRequest):
    if not request.file_name:
        logger.warning("Delete theta-rho file request received without filename")
        raise HTTPException(status_code=400, detail="No file name provided")

    # Normalize file path for cross-platform compatibility
    normalized_file_name = normalize_file_path(request.file_name)
    file_path = os.path.join(pattern_manager.THETA_RHO_DIR, normalized_file_name)

    # Check file existence asynchronously
    exists = await asyncio.to_thread(os.path.exists, file_path)
    if not exists:
        logger.error(f"Attempted to delete non-existent file: {file_path}")
        raise HTTPException(status_code=404, detail="File not found")

    try:
        # Delete the pattern file asynchronously
        await asyncio.to_thread(os.remove, file_path)
        logger.info(f"Successfully deleted theta-rho file: {request.file_name}")
        
        # Clean up cached preview image and metadata asynchronously
        from modules.core.cache_manager import delete_pattern_cache
        cache_cleanup_success = await asyncio.to_thread(delete_pattern_cache, normalized_file_name)
        if cache_cleanup_success:
            logger.info(f"Successfully cleaned up cache for {request.file_name}")
        else:
            logger.warning(f"Cache cleanup failed for {request.file_name}, but pattern was deleted")
        
        return {"success": True, "cache_cleanup": cache_cleanup_success}
    except Exception as e:
        logger.error(f"Failed to delete theta-rho file {request.file_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/move_to_center")
async def move_to_center():
    try:
        if not (state.conn.is_connected() if state.conn else False):
            logger.warning("Attempted to move to center without a connection")
            raise HTTPException(status_code=400, detail="Connection not established")

        check_homing_in_progress()


        logger.info("Moving device to center position")
        await pattern_manager.reset_theta()
        await pattern_manager.move_polar(0, 0)

        # Wait for machine to reach idle before returning
        idle = await connection_manager.check_idle_async(timeout=60)
        if not idle:
            logger.warning("Machine did not reach idle after move to center")

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to move to center: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/move_to_perimeter")
async def move_to_perimeter():
    try:
        if not (state.conn.is_connected() if state.conn else False):
            logger.warning("Attempted to move to perimeter without a connection")
            raise HTTPException(status_code=400, detail="Connection not established")

        check_homing_in_progress()


        logger.info("Moving device to perimeter position")
        await pattern_manager.reset_theta()
        await pattern_manager.move_polar(0, 1)

        # Wait for machine to reach idle before returning
        idle = await connection_manager.check_idle_async(timeout=60)
        if not idle:
            logger.warning("Machine did not reach idle after move to perimeter")

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to move to perimeter: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/preview_thr")
async def preview_thr(request: DeleteFileRequest):
    if not request.file_name:
        logger.warning("Preview theta-rho request received without filename")
        raise HTTPException(status_code=400, detail="No file name provided")

    # Normalize file path for cross-platform compatibility
    normalized_file_name = normalize_file_path(request.file_name)
    # Construct the full path to the pattern file to check existence
    pattern_file_path = os.path.join(pattern_manager.THETA_RHO_DIR, normalized_file_name)

    # Check file existence asynchronously
    exists = await asyncio.to_thread(os.path.exists, pattern_file_path)
    if not exists:
        logger.error(f"Attempted to preview non-existent pattern file: {pattern_file_path}")
        raise HTTPException(status_code=404, detail="Pattern file not found")

    try:
        cache_path = get_cache_path(normalized_file_name)

        # Check cache existence asynchronously
        cache_exists = await asyncio.to_thread(os.path.exists, cache_path)
        if not cache_exists:
            logger.info(f"Cache miss for {request.file_name}. Generating preview...")
            # Attempt to generate the preview if it's missing
            success = await generate_image_preview(normalized_file_name)
            cache_exists_after = await asyncio.to_thread(os.path.exists, cache_path)
            if not success or not cache_exists_after:
                logger.error(f"Failed to generate or find preview for {request.file_name} after attempting generation.")
                raise HTTPException(status_code=500, detail="Failed to generate preview image.")

        # Try to get coordinates from metadata cache first
        metadata = get_pattern_metadata(normalized_file_name)
        if metadata:
            first_coord_obj = metadata.get('first_coordinate')
            last_coord_obj = metadata.get('last_coordinate')
        else:
            # Fallback to parsing file if metadata not cached (shouldn't happen after initial cache)
            logger.debug(f"Metadata cache miss for {request.file_name}, parsing file")
            coordinates = await asyncio.to_thread(parse_theta_rho_file, pattern_file_path)
            first_coord = coordinates[0] if coordinates else None
            last_coord = coordinates[-1] if coordinates else None
            
            # Format coordinates as objects with x and y properties
            first_coord_obj = {"x": first_coord[0], "y": first_coord[1]} if first_coord else None
            last_coord_obj = {"x": last_coord[0], "y": last_coord[1]} if last_coord else None

        # Return JSON with preview URL and coordinates
        # URL encode the file_name for the preview URL
        # Handle both forward slashes and backslashes for cross-platform compatibility
        encoded_filename = normalized_file_name.replace('\\', '--').replace('/', '--')
        return {
            "preview_url": f"/preview/{encoded_filename}",
            "first_coordinate": first_coord_obj,
            "last_coordinate": last_coord_obj
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate or serve preview for {request.file_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to serve preview image: {str(e)}")

@app.get("/api/pattern_history/{pattern_name:path}")
async def get_pattern_history(pattern_name: str):
    """Get the most recent execution history for a pattern.

    Returns the last completed execution time and speed for the given pattern.
    """
    from modules.core.pattern_manager import get_pattern_execution_history

    # Get just the filename if a full path was provided
    filename = os.path.basename(pattern_name)
    if not filename.endswith('.thr'):
        filename = f"{filename}.thr"

    history = get_pattern_execution_history(filename)
    if history:
        return history
    return {"actual_time_seconds": None, "actual_time_formatted": None, "speed": None, "timestamp": None}

@app.get("/api/pattern_history_all")
async def get_all_pattern_history():
    """Get execution history for all patterns in a single request.

    Returns a dict mapping pattern names to their most recent execution history.
    """
    from modules.core.pattern_manager import EXECUTION_LOG_FILE

    if not os.path.exists(EXECUTION_LOG_FILE):
        return {}

    try:
        history_map = {}
        play_counts = {}
        with open(EXECUTION_LOG_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    # Only consider fully completed patterns
                    if entry.get('completed', False):
                        pattern_name = entry.get('pattern_name')
                        if pattern_name:
                            play_counts[pattern_name] = play_counts.get(pattern_name, 0) + 1
                            # Keep the most recent match (last one in file wins)
                            history_map[pattern_name] = {
                                "actual_time_seconds": entry.get('actual_time_seconds'),
                                "actual_time_formatted": entry.get('actual_time_formatted'),
                                "speed": entry.get('speed'),
                                "timestamp": entry.get('timestamp'),
                                "play_count": play_counts[pattern_name],
                                "last_played": entry.get('timestamp')
                            }
                except json.JSONDecodeError:
                    continue
        return history_map
    except Exception as e:
        logger.error(f"Failed to read execution time log: {e}")
        return {}

@app.get("/preview/{encoded_filename}")
async def serve_preview(encoded_filename: str):
    """Serve a preview image for a pattern file."""
    # Decode the filename by replacing -- with the original path separators
    # First try forward slash (most common case), then backslash if needed
    file_name = encoded_filename.replace('--', '/')
    
    # Apply normalization to handle any remaining path prefixes
    file_name = normalize_file_path(file_name)
    
    # Check if the decoded path exists, if not try backslash decoding
    cache_path = get_cache_path(file_name)
    if not os.path.exists(cache_path):
        # Try with backslash for Windows paths
        file_name_backslash = encoded_filename.replace('--', '\\')
        file_name_backslash = normalize_file_path(file_name_backslash)
        cache_path_backslash = get_cache_path(file_name_backslash)
        if os.path.exists(cache_path_backslash):
            file_name = file_name_backslash
            cache_path = cache_path_backslash
    # cache_path is already determined above in the decoding logic
    if not os.path.exists(cache_path):
        logger.error(f"Preview image not found for {file_name}")
        raise HTTPException(status_code=404, detail="Preview image not found")
    
    # Add caching headers
    headers = {
        "Cache-Control": "public, max-age=31536000",  # Cache for 1 year
        "Content-Type": "image/webp",
        "Accept-Ranges": "bytes"
    }
    
    return FileResponse(
        cache_path,
        media_type="image/webp",
        headers=headers
    )

@app.post("/send_coordinate")
async def send_coordinate(request: CoordinateRequest):
    if not (state.conn.is_connected() if state.conn else False):
        logger.warning("Attempted to send coordinate without a connection")
        raise HTTPException(status_code=400, detail="Connection not established")

    check_homing_in_progress()


    try:
        logger.debug(f"Sending coordinate: theta={request.theta}, rho={request.rho}")
        await pattern_manager.move_polar(request.theta, request.rho)

        # Wait for machine to reach idle before returning
        idle = await connection_manager.check_idle_async(timeout=60)
        if not idle:
            logger.warning("Machine did not reach idle after send_coordinate")

        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to send coordinate: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/{filename}")
async def download_file(filename: str):
    return FileResponse(
        os.path.join(pattern_manager.THETA_RHO_DIR, filename),
        filename=filename
    )

@app.get("/serial_status")
async def serial_status():
    """Connection status. `port` is the configured board address (HTTP, not serial)."""
    connected = state.conn.is_connected() if state.conn else False
    port = connection_manager.board_url()
    logger.debug(f"Connection status check - connected: {connected}, board: {port}")
    return {
        "connected": connected,
        "port": port,
        # Board's network hostname (e.g. "DWMP") - the table's display name.
        "hostname": state.board_hostname,
        # True when the board rejects us with 401 (password-protected).
        "locked": (state.conn.locked if state.conn else False) or state.board_locked,
        # Whether a board password is saved on this backend.
        "has_key": bool(state.board_api_key),
    }

@app.post("/pause_execution")
async def pause_execution():
    status = execution.get_cached_status()
    if not (status.get("is_running") or status.get("pause_time_remaining")):
        raise HTTPException(status_code=400, detail="Nothing is currently playing")
    try:
        await execution.pause()
        return {"success": True, "message": "Execution paused"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to pause execution: {e}")

@app.post("/resume_execution")
async def resume_execution():
    if not execution.get_cached_status().get("is_paused"):
        raise HTTPException(status_code=400, detail="Execution is not paused")
    try:
        await execution.resume()
        return {"success": True, "message": "Execution resumed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resume execution: {e}")

# Playlist endpoints
@app.get("/list_all_playlists")
async def list_all_playlists():
    playlist_names = playlist_manager.list_all_playlists()
    return playlist_names

@app.get("/get_playlist")
async def get_playlist(name: str):
    if not name:
        raise HTTPException(status_code=400, detail="Missing playlist name parameter")

    playlist = playlist_manager.get_playlist(name)
    if not playlist:
        # Auto-create empty playlist if not found
        logger.info(f"Playlist '{name}' not found, creating empty playlist")
        playlist_manager.create_playlist(name, [])
        playlist = {"name": name, "files": []}

    return playlist

@app.post("/create_playlist")
async def create_playlist(request: PlaylistRequest):
    success = playlist_manager.create_playlist(request.playlist_name, request.files)
    return {
        "success": success,
        "message": f"Playlist '{request.playlist_name}' created/updated"
    }

@app.post("/modify_playlist")
async def modify_playlist(request: PlaylistRequest):
    success = playlist_manager.modify_playlist(request.playlist_name, request.files)
    return {
        "success": success,
        "message": f"Playlist '{request.playlist_name}' updated"
    }

@app.delete("/delete_playlist")
async def delete_playlist(request: DeletePlaylistRequest):
    success = playlist_manager.delete_playlist(request.playlist_name)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Playlist '{request.playlist_name}' not found"
        )

    return {
        "success": True,
        "message": f"Playlist '{request.playlist_name}' deleted"
    }

@app.post("/rename_playlist")
async def rename_playlist(request: RenamePlaylistRequest):
    """Rename an existing playlist."""
    success, message = playlist_manager.rename_playlist(request.old_name, request.new_name)
    if not success:
        raise HTTPException(
            status_code=400,
            detail=message
        )

    return {
        "success": True,
        "message": message,
        "new_name": request.new_name
    }

class AddToPlaylistRequest(BaseModel):
    playlist_name: str
    pattern: str

@app.post("/add_to_playlist")
async def add_to_playlist(request: AddToPlaylistRequest):
    success = playlist_manager.add_to_playlist(request.playlist_name, request.pattern)
    if not success:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return {"success": True}

@app.post("/run_playlist")
async def run_playlist_endpoint(request: PlaylistRequest):
    """Run a playlist on the board ($Playlist/Run; the firmware sequences it)."""
    if not (state.conn.is_connected() if state.conn else False):
        logger.warning("Attempted to run a playlist without a connection")
        raise HTTPException(status_code=400, detail="Connection not established")
    check_homing_in_progress()

    try:
        await execution.start_playlist(
            request.playlist_name,
            run_mode=request.run_mode,
            pause_time=request.pause_time,
            clear_pattern=request.clear_pattern,
            shuffle=request.shuffle,
        )
        return {"message": f"Started playlist: {request.playlist_name}"}
    except execution.ExecutionError as e:
        detail = str(e)
        status = 404 if "not found" in detail else 409
        raise HTTPException(status_code=status, detail=detail)
    except Exception as e:
        logger.error(f"Error running playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/set_speed")
async def set_speed(request: SpeedRequest):
    try:
        if not (state.conn.is_connected() if state.conn else False):
            logger.warning("Attempted to change speed without a connection")
            raise HTTPException(status_code=400, detail="Connection not established")

        if request.speed <= 0:
            logger.warning(f"Invalid speed value received: {request.speed}")
            raise HTTPException(status_code=400, detail="Invalid speed value")

        state.speed = request.speed
        # Push the feed live to the board (works mid-pattern; persists across the run).
        try:
            await asyncio.to_thread(state.conn.set_feed, int(request.speed))
        except Exception as e:
            logger.warning(f"Could not push feed to board: {e}")
        return {"success": True, "speed": request.speed}
    except HTTPException:
        raise  # Re-raise HTTPException as-is
    except Exception as e:
        logger.error(f"Failed to set speed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/check_software_update")
async def check_updates():
    update_info = update_manager.check_git_updates()
    return update_info

@app.post("/update_software")
async def update_software():
    logger.info("Starting software update process")
    success, error_message, error_log = update_manager.update_software()
    
    if success:
        logger.info("Software update completed successfully")
        return {"success": True}
    else:
        logger.error(f"Software update failed: {error_message}\nDetails: {error_log}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": error_message,
                "details": error_log
            }
        )

@app.post("/set_wled_ip")
async def set_wled_ip(request: WLEDRequest):
    """Legacy endpoint for backward compatibility - sets WLED as LED provider"""
    state.wled_ip = request.wled_ip
    state.led_provider = "wled" if request.wled_ip else "none"
    state.led_controller = LEDInterface("wled", request.wled_ip) if request.wled_ip else None
    if state.led_controller:
        state.led_controller.effect_idle()
        _start_idle_led_timeout()
    state.save()
    logger.info(f"WLED IP updated: {request.wled_ip}")
    return {"success": True, "wled_ip": state.wled_ip}

@app.get("/get_wled_ip")
async def get_wled_ip():
    """Legacy endpoint for backward compatibility"""
    if not state.wled_ip:
        raise HTTPException(status_code=404, detail="No WLED IP set")
    return {"success": True, "wled_ip": state.wled_ip}

@app.post("/set_led_config", deprecated=True, tags=["settings-deprecated"])
async def set_led_config(request: LEDConfigRequest):
    """DEPRECATED: Use PATCH /api/settings instead. Configure LED provider (board, WLED, or none)"""
    if request.provider not in ["wled", "board", "none"]:
        raise HTTPException(status_code=400, detail="Invalid provider. Must be 'board', 'wled', or 'none'")

    state.led_provider = request.provider

    if request.provider == "wled":
        if not request.ip_address:
            raise HTTPException(status_code=400, detail="IP address required for WLED")
        state.wled_ip = request.ip_address
        state.led_controller = LEDInterface("wled", request.ip_address)
        logger.info(f"LED provider set to WLED at {request.ip_address}")

    elif request.provider == "board":
        # The table's own LED ring, driven by the FluidNC firmware.
        state.led_controller = LEDInterface("board")
        logger.info("LED provider set to the table's built-in LEDs (firmware-controlled)")

    else:  # none
        state.wled_ip = None
        state.led_controller = None
        logger.info("LED provider disabled")

    # Show idle effect if controller is configured
    if state.led_controller:
        state.led_controller.effect_idle()
        _start_idle_led_timeout()

    state.save()

    return {
        "success": True,
        "provider": state.led_provider,
        "wled_ip": state.wled_ip,
    }

@app.get("/get_led_config", deprecated=True, tags=["settings-deprecated"])
async def get_led_config():
    """DEPRECATED: Use GET /api/settings instead. Get current LED provider configuration"""
    # Auto-detect provider for backward compatibility with existing installations
    provider = state.led_provider
    if not provider or provider == "none":
        # If no provider set but we have IPs configured, auto-detect
        if state.wled_ip:
            provider = "wled"
            state.led_provider = "wled"
            state.save()
            logger.info("Auto-detected WLED provider from existing configuration")
        else:
            provider = "none"

    return {
        "success": True,
        "provider": provider,
        "wled_ip": state.wled_ip,
    }

@app.post("/skip_pattern")
async def skip_pattern():
    try:
        skipped = await execution.skip()
    except execution.ExecutionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not skipped:
        raise HTTPException(status_code=400, detail="No playlist is currently running")
    return {"success": True}

@app.get("/api/custom_clear_patterns", deprecated=True, tags=["settings-deprecated"])
async def get_custom_clear_patterns():
    """Get the currently configured custom clear patterns."""
    return {
        "success": True,
        "custom_clear_from_in": state.custom_clear_from_in,
        "custom_clear_from_out": state.custom_clear_from_out
    }

@app.post("/api/custom_clear_patterns", deprecated=True, tags=["settings-deprecated"])
async def set_custom_clear_patterns(request: dict):
    """Set custom clear patterns for clear_from_in and clear_from_out."""
    try:
        # Validate that the patterns exist if they're provided
        if "custom_clear_from_in" in request and request["custom_clear_from_in"]:
            pattern_path = os.path.join(pattern_manager.THETA_RHO_DIR, request["custom_clear_from_in"])
            if not os.path.exists(pattern_path):
                raise HTTPException(status_code=400, detail=f"Pattern file not found: {request['custom_clear_from_in']}")
            state.custom_clear_from_in = request["custom_clear_from_in"]
        elif "custom_clear_from_in" in request:
            state.custom_clear_from_in = None
            
        if "custom_clear_from_out" in request and request["custom_clear_from_out"]:
            pattern_path = os.path.join(pattern_manager.THETA_RHO_DIR, request["custom_clear_from_out"])
            if not os.path.exists(pattern_path):
                raise HTTPException(status_code=400, detail=f"Pattern file not found: {request['custom_clear_from_out']}")
            state.custom_clear_from_out = request["custom_clear_from_out"]
        elif "custom_clear_from_out" in request:
            state.custom_clear_from_out = None
        
        state.save()
        # The firmware runs its own clear files; mirror the choice onto them.
        board_settings.push_custom_clears_async()
        logger.info(f"Custom clear patterns updated - in: {state.custom_clear_from_in}, out: {state.custom_clear_from_out}")
        return {
            "success": True,
            "custom_clear_from_in": state.custom_clear_from_in,
            "custom_clear_from_out": state.custom_clear_from_out
        }
    except Exception as e:
        logger.error(f"Failed to set custom clear patterns: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/clear_pattern_speed", deprecated=True, tags=["settings-deprecated"])
async def get_clear_pattern_speed():
    """Get the current clearing pattern speed setting."""
    return {
        "success": True,
        "clear_pattern_speed": state.clear_pattern_speed,
        "effective_speed": state.clear_pattern_speed if state.clear_pattern_speed is not None else state.speed
    }

@app.post("/api/clear_pattern_speed", deprecated=True, tags=["settings-deprecated"])
async def set_clear_pattern_speed(request: dict):
    """DEPRECATED: Use PATCH /api/settings instead. Set the clearing pattern speed."""
    try:
        # If speed is None or "none", use default behavior (state.speed)
        speed_value = request.get("clear_pattern_speed")
        if speed_value is None or speed_value == "none" or speed_value == "":
            speed = None
        else:
            speed = int(speed_value)
        
        # Validate speed range (same as regular speed limits) only if speed is not None
        if speed is not None and not (50 <= speed <= 2000):
            raise HTTPException(status_code=400, detail="Speed must be between 50 and 2000")
        
        state.clear_pattern_speed = speed
        state.save()
        
        logger.info(f"Clear pattern speed set to {speed if speed is not None else 'default (state.speed)'}")
        return {
            "success": True,
            "clear_pattern_speed": state.clear_pattern_speed,
            "effective_speed": state.clear_pattern_speed if state.clear_pattern_speed is not None else state.speed
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid speed value")
    except Exception as e:
        logger.error(f"Failed to set clear pattern speed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/app-name", deprecated=True, tags=["settings-deprecated"])
async def get_app_name():
    """DEPRECATED: Use GET /api/settings instead. Get current application name."""
    return {"app_name": state.app_name}

@app.post("/api/app-name", deprecated=True, tags=["settings-deprecated"])
async def set_app_name(request: dict):
    """DEPRECATED: Use PATCH /api/settings instead. Update application name."""
    app_name = request.get("app_name", "").strip()
    if not app_name:
        app_name = "Dune Weaver"  # Reset to default if empty

    state.app_name = app_name
    state.save()

    logger.info(f"Application name updated to: {app_name}")
    return {"success": True, "app_name": app_name}

# ============================================================================
# Custom Branding Upload Endpoints
# ============================================================================

CUSTOM_BRANDING_DIR = os.path.join("static", "custom")
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
MAX_LOGO_SIZE = 10 * 1024 * 1024  # 10MB
MAX_LOGO_DIMENSION = 512  # Max width/height for optimized logo


def optimize_logo_image(content: bytes, original_ext: str) -> tuple[bytes, str]:
    """Optimize logo image by resizing and converting to WebP.

    Args:
        content: Original image bytes
        original_ext: Original file extension (e.g., '.png', '.jpg')

    Returns:
        Tuple of (optimized_bytes, new_extension)

    For SVG files, returns the original content unchanged.
    For raster images, resizes to MAX_LOGO_DIMENSION and converts to WebP.
    """
    # SVG files are already lightweight vectors - keep as-is
    if original_ext.lower() == ".svg":
        return content, original_ext

    try:
        from PIL import Image
        import io

        with Image.open(io.BytesIO(content)) as img:
            # Convert to RGBA for transparency support
            if img.mode in ('P', 'LA') or (img.mode == 'RGBA' and 'transparency' in img.info):
                img = img.convert('RGBA')
            elif img.mode != 'RGBA':
                img = img.convert('RGB')

            # Resize if larger than max dimension (maintain aspect ratio)
            width, height = img.size
            if width > MAX_LOGO_DIMENSION or height > MAX_LOGO_DIMENSION:
                ratio = min(MAX_LOGO_DIMENSION / width, MAX_LOGO_DIMENSION / height)
                new_size = (int(width * ratio), int(height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                logger.info(f"Logo resized from {width}x{height} to {new_size[0]}x{new_size[1]}")

            # Save as WebP with good quality/size balance
            output = io.BytesIO()
            img.save(output, format='WEBP', quality=85, method=6)
            optimized_bytes = output.getvalue()

            original_size = len(content)
            new_size = len(optimized_bytes)
            reduction = ((original_size - new_size) / original_size) * 100
            logger.info(f"Logo optimized: {original_size:,} bytes -> {new_size:,} bytes ({reduction:.1f}% reduction)")

            return optimized_bytes, ".webp"

    except Exception as e:
        logger.warning(f"Logo optimization failed, using original: {str(e)}")
        return content, original_ext

def generate_favicon_from_logo(logo_path: str, output_dir: str) -> bool:
    """Generate circular favicons with transparent background from the uploaded logo.

    Creates:
    - favicon.ico (multi-size: 256, 128, 64, 48, 32, 16)
    - favicon-16x16.png, favicon-32x32.png, favicon-96x96.png, favicon-128x128.png

    Returns True on success, False on failure.
    """
    try:
        from PIL import Image, ImageDraw

        def create_circular_transparent(img, size):
            """Create circular image with transparent background."""
            resized = img.resize((size, size), Image.Resampling.LANCZOS)

            mask = Image.new('L', (size, size), 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0, size - 1, size - 1), fill=255)

            output = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            output.paste(resized, (0, 0), mask)
            return output

        with Image.open(logo_path) as img:
            # Convert to RGBA if needed
            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            # Crop to square (center crop)
            width, height = img.size
            min_dim = min(width, height)
            left = (width - min_dim) // 2
            top = (height - min_dim) // 2
            img = img.crop((left, top, left + min_dim, top + min_dim))

            # Generate circular favicon PNGs with transparent background
            png_sizes = {
                "favicon-16x16.png": 16,
                "favicon-32x32.png": 32,
                "favicon-96x96.png": 96,
                "favicon-128x128.png": 128,
            }
            for filename, size in png_sizes.items():
                icon = create_circular_transparent(img, size)
                icon.save(os.path.join(output_dir, filename), format='PNG')

            # Generate high-resolution favicon.ico
            ico_sizes = [256, 128, 64, 48, 32, 16]
            ico_images = [create_circular_transparent(img, s) for s in ico_sizes]
            ico_images[0].save(
                os.path.join(output_dir, "favicon.ico"),
                format='ICO',
                append_images=ico_images[1:],
                sizes=[(s, s) for s in ico_sizes]
            )

        return True
    except Exception as e:
        logger.error(f"Failed to generate favicon: {str(e)}")
        return False

def generate_pwa_icons_from_logo(logo_path: str, output_dir: str) -> bool:
    """Generate square PWA app icons from the uploaded logo.

    Creates square icons (no circular crop) - OS will apply its own mask.
    Composites onto a solid background to avoid transparency issues
    (iOS fills transparent areas with white on home screen icons).

    Generates:
    - apple-touch-icon.png (180x180)
    - android-chrome-192x192.png (192x192)
    - android-chrome-512x512.png (512x512)

    Returns True on success, False on failure.
    """
    try:
        from PIL import Image

        with Image.open(logo_path) as img:
            # Convert to RGBA if needed
            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            # Crop to square (center crop)
            width, height = img.size
            min_dim = min(width, height)
            left = (width - min_dim) // 2
            top = (height - min_dim) // 2
            img = img.crop((left, top, left + min_dim, top + min_dim))

            # Generate square icons at each required size
            icon_sizes = {
                "apple-touch-icon.png": 180,
                "android-chrome-192x192.png": 192,
                "android-chrome-512x512.png": 512,
            }

            for filename, size in icon_sizes.items():
                resized = img.resize((size, size), Image.Resampling.LANCZOS)
                # Composite onto solid background to eliminate transparency
                # (iOS shows white behind transparent areas on home screen)
                background = Image.new('RGB', (size, size), (10, 10, 10))  # #0a0a0a theme color
                background.paste(resized, (0, 0), resized)  # Use resized as its own alpha mask
                icon_path = os.path.join(output_dir, filename)
                background.save(icon_path, format='PNG')
                logger.info(f"Generated PWA icon: {filename}")

        return True
    except Exception as e:
        logger.error(f"Failed to generate PWA icons: {str(e)}")
        return False

@app.post("/api/upload-logo", tags=["settings"])
async def upload_logo(file: UploadFile = File(...)):
    """Upload a custom logo image.

    Supported formats: PNG, JPG, JPEG, GIF, WebP, SVG
    Maximum upload size: 10MB

    Images are automatically optimized:
    - Resized to max 512x512 pixels
    - Converted to WebP format for smaller file size
    - SVG files are kept as-is (already lightweight)

    A favicon and PWA icons will be automatically generated from the logo.
    """
    try:
        # Validate file extension
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}"
            )

        # Read and validate file size
        content = await file.read()
        if len(content) > MAX_LOGO_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: {MAX_LOGO_SIZE // (1024*1024)}MB"
            )

        # Ensure custom branding directory exists
        os.makedirs(CUSTOM_BRANDING_DIR, exist_ok=True)

        # Delete old logo and favicon if they exist
        if state.custom_logo:
            old_logo_path = os.path.join(CUSTOM_BRANDING_DIR, state.custom_logo)
            if os.path.exists(old_logo_path):
                os.remove(old_logo_path)
            # Also remove old favicon
            old_favicon_path = os.path.join(CUSTOM_BRANDING_DIR, "favicon.ico")
            if os.path.exists(old_favicon_path):
                os.remove(old_favicon_path)

        # Optimize the image (resize + convert to WebP for smaller file size)
        optimized_content, optimized_ext = optimize_logo_image(content, file_ext)

        # Generate a unique filename to prevent caching issues
        import uuid
        filename = f"logo-{uuid.uuid4().hex[:8]}{optimized_ext}"
        file_path = os.path.join(CUSTOM_BRANDING_DIR, filename)

        # Save the optimized logo file
        with open(file_path, "wb") as f:
            f.write(optimized_content)

        # Generate favicon and PWA icons from logo (for non-SVG files)
        favicon_generated = False
        pwa_icons_generated = False
        if optimized_ext != ".svg":
            favicon_generated = generate_favicon_from_logo(file_path, CUSTOM_BRANDING_DIR)
            pwa_icons_generated = generate_pwa_icons_from_logo(file_path, CUSTOM_BRANDING_DIR)

        # Update state
        state.custom_logo = filename
        state.save()

        logger.info(f"Custom logo uploaded: {filename}, favicon generated: {favicon_generated}, PWA icons generated: {pwa_icons_generated}")
        return {
            "success": True,
            "filename": filename,
            "url": f"/static/custom/{filename}",
            "favicon_generated": favicon_generated,
            "pwa_icons_generated": pwa_icons_generated
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading logo: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/custom-logo", tags=["settings"])
async def delete_custom_logo():
    """Remove custom logo, favicon, and PWA icons, reverting to defaults."""
    try:
        if state.custom_logo:
            # Remove logo
            logo_path = os.path.join(CUSTOM_BRANDING_DIR, state.custom_logo)
            if os.path.exists(logo_path):
                os.remove(logo_path)

            # Remove generated favicons
            favicon_files = [
                "favicon.ico",
                "favicon-16x16.png",
                "favicon-32x32.png",
                "favicon-96x96.png",
                "favicon-128x128.png",
            ]
            for favicon_name in favicon_files:
                favicon_path = os.path.join(CUSTOM_BRANDING_DIR, favicon_name)
                if os.path.exists(favicon_path):
                    os.remove(favicon_path)

            # Remove generated PWA icons
            pwa_icons = [
                "apple-touch-icon.png",
                "android-chrome-192x192.png",
                "android-chrome-512x512.png",
            ]
            for icon_name in pwa_icons:
                icon_path = os.path.join(CUSTOM_BRANDING_DIR, icon_name)
                if os.path.exists(icon_path):
                    os.remove(icon_path)

            state.custom_logo = None
            state.save()
            logger.info("Custom logo, favicon, and PWA icons removed")
        return {"success": True}
    except Exception as e:
        logger.error(f"Error removing logo: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/mqtt-config", deprecated=True, tags=["settings-deprecated"])
async def get_mqtt_config():
    """DEPRECATED: Use GET /api/settings instead. Get current MQTT configuration.

    Note: Password is not returned for security reasons.
    """
    from modules.mqtt import get_mqtt_handler
    handler = get_mqtt_handler()

    return {
        "enabled": state.mqtt_enabled,
        "broker": state.mqtt_broker,
        "port": state.mqtt_port,
        "username": state.mqtt_username,
        # Password is intentionally omitted for security
        "has_password": bool(state.mqtt_password),
        "client_id": state.mqtt_client_id,
        "discovery_prefix": state.mqtt_discovery_prefix,
        "device_id": state.mqtt_device_id,
        "device_name": state.mqtt_device_name,
        "connected": handler.is_connected if hasattr(handler, 'is_connected') else False,
        "is_mock": handler.__class__.__name__ == 'MockMQTTHandler'
    }

@app.post("/api/mqtt-config", deprecated=True, tags=["settings-deprecated"])
async def set_mqtt_config(request: dict):
    """DEPRECATED: Use PATCH /api/settings instead. Update MQTT configuration. Requires restart to take effect."""
    try:
        # Update state with new values
        state.mqtt_enabled = request.get("enabled", False)
        state.mqtt_broker = (request.get("broker") or "").strip()
        state.mqtt_port = int(request.get("port") or 1883)
        state.mqtt_username = (request.get("username") or "").strip()
        state.mqtt_password = (request.get("password") or "").strip()
        state.mqtt_client_id = (request.get("client_id") or "dune_weaver").strip()
        state.mqtt_discovery_prefix = (request.get("discovery_prefix") or "homeassistant").strip()
        state.mqtt_device_id = (request.get("device_id") or "dune_weaver").strip()
        state.mqtt_device_name = (request.get("device_name") or "Dune Weaver").strip()

        # Validate required fields when enabled
        if state.mqtt_enabled and not state.mqtt_broker:
            return JSONResponse(
                content={"success": False, "message": "Broker address is required when MQTT is enabled"},
                status_code=400
            )

        state.save()
        logger.info(f"MQTT configuration updated. Enabled: {state.mqtt_enabled}, Broker: {state.mqtt_broker}")

        return {
            "success": True,
            "message": "MQTT configuration saved. Restart the application for changes to take effect.",
            "requires_restart": True
        }
    except ValueError as e:
        return JSONResponse(
            content={"success": False, "message": f"Invalid value: {str(e)}"},
            status_code=400
        )
    except Exception as e:
        logger.error(f"Failed to update MQTT config: {str(e)}")
        return JSONResponse(
            content={"success": False, "message": str(e)},
            status_code=500
        )

@app.post("/api/mqtt-test")
async def test_mqtt_connection(request: dict):
    """Test MQTT connection with provided settings."""
    import paho.mqtt.client as mqtt_client

    broker = (request.get("broker") or "").strip()
    port = int(request.get("port") or 1883)
    username = (request.get("username") or "").strip()
    password = (request.get("password") or "").strip()
    client_id = (request.get("client_id") or "dune_weaver_test").strip()

    if not broker:
        return JSONResponse(
            content={"success": False, "message": "Broker address is required"},
            status_code=400
        )

    try:
        # Create a test client
        client = mqtt_client.Client(client_id=client_id + "_test")

        if username:
            client.username_pw_set(username, password)

        # Connection result
        connection_result = {"connected": False, "error": None}

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                connection_result["connected"] = True
            else:
                error_messages = {
                    1: "Incorrect protocol version",
                    2: "Invalid client identifier",
                    3: "Server unavailable",
                    4: "Bad username or password",
                    5: "Not authorized"
                }
                connection_result["error"] = error_messages.get(rc, f"Connection failed with code {rc}")

        client.on_connect = on_connect

        # Try to connect with timeout
        client.connect_async(broker, port, keepalive=10)
        client.loop_start()

        # Wait for connection result (max 5 seconds)
        import time
        start_time = time.time()
        while time.time() - start_time < 5:
            if connection_result["connected"] or connection_result["error"]:
                break
            await asyncio.sleep(0.1)

        client.loop_stop()
        client.disconnect()

        if connection_result["connected"]:
            return {"success": True, "message": "Successfully connected to MQTT broker"}
        elif connection_result["error"]:
            return JSONResponse(
                content={"success": False, "message": connection_result["error"]},
                status_code=400
            )
        else:
            return JSONResponse(
                content={"success": False, "message": "Connection timed out. Check broker address and port."},
                status_code=400
            )

    except Exception as e:
        logger.error(f"MQTT test connection failed: {str(e)}")
        return JSONResponse(
            content={"success": False, "message": str(e)},
            status_code=500
        )

def _read_and_encode_preview(cache_path: str) -> str:
    """Read preview image from disk and encode as base64.
    
    Combines file I/O and base64 encoding in a single function
    to be run in executor, reducing context switches.
    """
    with open(cache_path, 'rb') as f:
        image_data = f.read()
    return base64.b64encode(image_data).decode('utf-8')

@app.post("/preview_thr_batch")
async def preview_thr_batch(request: dict):
    start = time.time()
    if not request.get("file_names"):
        logger.warning("Batch preview request received without filenames")
        raise HTTPException(status_code=400, detail="No file names provided")

    file_names = request["file_names"]
    if not isinstance(file_names, list):
        raise HTTPException(status_code=400, detail="file_names must be a list")

    headers = {
        "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
        "Content-Type": "application/json"
    }

    async def process_single_file(file_name):
        """Process a single file and return its preview data."""
        # Check in-memory cache first (for current and next playing patterns)
        normalized_for_cache = normalize_file_path(file_name)
        if state._current_preview and state._current_preview[0] == normalized_for_cache:
            logger.debug(f"Using cached preview for current: {file_name}")
            return file_name, state._current_preview[1]
        if state._next_preview and state._next_preview[0] == normalized_for_cache:
            logger.debug(f"Using cached preview for next: {file_name}")
            return file_name, state._next_preview[1]

        # Acquire semaphore to limit concurrent processing
        async with get_preview_semaphore():
            t1 = time.time()
            try:
                # Normalize file path for cross-platform compatibility
                normalized_file_name = normalize_file_path(file_name)
                pattern_file_path = os.path.join(pattern_manager.THETA_RHO_DIR, normalized_file_name)

                # Check file existence asynchronously
                exists = await asyncio.to_thread(os.path.exists, pattern_file_path)
                if not exists:
                    logger.warning(f"Pattern file not found: {pattern_file_path}")
                    return file_name, {"error": "Pattern file not found"}

                cache_path = get_cache_path(normalized_file_name)

                # Check cache existence asynchronously
                cache_exists = await asyncio.to_thread(os.path.exists, cache_path)
                if not cache_exists:
                    logger.info(f"Cache miss for {file_name}. Generating preview...")
                    success = await generate_image_preview(normalized_file_name)
                    cache_exists_after = await asyncio.to_thread(os.path.exists, cache_path)
                    if not success or not cache_exists_after:
                        logger.error(f"Failed to generate or find preview for {file_name}")
                        return file_name, {"error": "Failed to generate preview"}

                metadata = get_pattern_metadata(normalized_file_name)
                if metadata:
                    first_coord_obj = metadata.get('first_coordinate')
                    last_coord_obj = metadata.get('last_coordinate')
                else:
                    logger.debug(f"Metadata cache miss for {file_name}, parsing file")
                    # Use thread pool to avoid memory pressure on resource-constrained devices
                    coordinates = await asyncio.to_thread(parse_theta_rho_file, pattern_file_path)
                    first_coord = coordinates[0] if coordinates else None
                    last_coord = coordinates[-1] if coordinates else None
                    first_coord_obj = {"x": first_coord[0], "y": first_coord[1]} if first_coord else None
                    last_coord_obj = {"x": last_coord[0], "y": last_coord[1]} if last_coord else None

                # Read image file and encode in executor to avoid blocking event loop
                loop = asyncio.get_running_loop()
                image_b64 = await loop.run_in_executor(None, _read_and_encode_preview, cache_path)
                result = {
                    "image_data": f"data:image/webp;base64,{image_b64}",
                    "first_coordinate": first_coord_obj,
                    "last_coordinate": last_coord_obj
                }

                # Cache preview for current/next pattern to speed up subsequent requests
                current_file = state.current_playing_file
                if current_file:
                    current_normalized = normalize_file_path(current_file)
                    if normalized_file_name == current_normalized:
                        state._current_preview = (normalized_file_name, result)
                        logger.debug(f"Cached preview for current: {file_name}")
                    elif state.current_playlist:
                        # Check if this is the next pattern in playlist
                        playlist = state.current_playlist
                        status_pl = execution.get_cached_status().get("playlist") or {}
                        idx = status_pl.get("current_index")
                        if idx is not None and idx + 1 < len(playlist):
                            next_file = normalize_file_path(playlist[idx + 1])
                            if normalized_file_name == next_file:
                                state._next_preview = (normalized_file_name, result)
                                logger.debug(f"Cached preview for next: {file_name}")

                logger.debug(f"Processed {file_name} in {time.time() - t1:.2f}s")
                return file_name, result
            except Exception as e:
                logger.error(f"Error processing {file_name}: {str(e)}")
                return file_name, {"error": str(e)}

    # Process all files concurrently
    tasks = [process_single_file(file_name) for file_name in file_names]
    file_results = await asyncio.gather(*tasks)

    # Convert results to dictionary
    results = dict(file_results)

    logger.debug(f"Total batch processing time: {time.time() - start:.2f}s for {len(file_names)} files")
    return JSONResponse(content=results, headers=headers)

@app.get("/playlists")
async def playlists_page(request: Request):
    return get_redirect_response(request)

@app.get("/image2sand")
async def image2sand_page(request: Request):
    return get_redirect_response(request)

@app.get("/led")
async def led_control_page(request: Request):
    return get_redirect_response(request)

# DW LED control endpoints
@app.get("/api/dw_leds/status")
async def dw_leds_status():
    """Get DW LED controller status"""
    if not state.led_controller or state.led_provider != "board":
        return {"connected": False, "message": "DW LEDs not configured"}

    try:
        return state.led_controller.check_status()
    except Exception as e:
        logger.error(f"Failed to check DW LED status: {str(e)}")
        return {"connected": False, "message": str(e)}

@app.post("/api/dw_leds/power")
async def dw_leds_power(request: dict):
    """Control DW LED power (0=off, 1=on, 2=toggle)"""
    if not state.led_controller or state.led_provider != "board":
        raise HTTPException(status_code=400, detail="DW LEDs not configured")

    state_value = request.get("state", 1)
    if state_value not in [0, 1, 2]:
        raise HTTPException(status_code=400, detail="State must be 0 (off), 1 (on), or 2 (toggle)")

    try:
        result = state.led_controller.set_power(state_value)

        # Reset idle timeout when LEDs are manually powered on (only if idle timeout is enabled)
        # This prevents idle timeout from immediately turning them back off
        if state_value in [1, 2] and state.dw_led_idle_timeout_enabled:  # Power on or toggle
            state.dw_led_last_activity_time = time.time()
            logger.debug("LED activity time reset due to manual power on")

        return result
    except Exception as e:
        logger.error(f"Failed to set DW LED power: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/dw_leds/brightness")
async def dw_leds_brightness(request: dict):
    """Set DW LED brightness (0-100)"""
    if not state.led_controller or state.led_provider != "board":
        raise HTTPException(status_code=400, detail="DW LEDs not configured")

    value = request.get("value", 50)
    if not 0 <= value <= 100:
        raise HTTPException(status_code=400, detail="Brightness must be between 0 and 100")

    try:
        controller = state.led_controller.get_controller()
        # The value persists where it lives (board NVS / WLED) — no host state.
        return controller.set_brightness(value)
    except Exception as e:
        logger.error(f"Failed to set LED brightness: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/dw_leds/color")
async def dw_leds_color(request: dict):
    """Set solid color (manual UI control - always powers on LEDs)"""
    if not state.led_controller or state.led_provider != "board":
        raise HTTPException(status_code=400, detail="DW LEDs not configured")

    # Accept both formats: {"r": 255, "g": 0, "b": 0} or {"color": [255, 0, 0]}
    if "color" in request:
        color = request["color"]
        if not isinstance(color, list) or len(color) != 3:
            raise HTTPException(status_code=400, detail="Color must be [R, G, B] array")
        r, g, b = color[0], color[1], color[2]
    elif "r" in request and "g" in request and "b" in request:
        r = request["r"]
        g = request["g"]
        b = request["b"]
    else:
        raise HTTPException(status_code=400, detail="Color must include r, g, b fields or color array")

    try:
        controller = state.led_controller.get_controller()
        # Power on LEDs when user manually sets color via UI
        controller.set_power(1)
        # Reset idle timeout for manual interaction (only if idle timeout is enabled)
        if state.dw_led_idle_timeout_enabled:
            state.dw_led_last_activity_time = time.time()
        return controller.set_color(r, g, b)
    except Exception as e:
        logger.error(f"Failed to set DW LED color: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/dw_leds/colors")
async def dw_leds_colors(request: dict):
    """Set effect colors (color1, color2, color3) - manual UI control - always powers on LEDs"""
    if not state.led_controller or state.led_provider != "board":
        raise HTTPException(status_code=400, detail="DW LEDs not configured")

    # Parse colors from request
    color1 = None
    color2 = None
    color3 = None

    if "color1" in request:
        c = request["color1"]
        if isinstance(c, list) and len(c) == 3:
            color1 = tuple(c)
        else:
            raise HTTPException(status_code=400, detail="color1 must be [R, G, B] array")

    if "color2" in request:
        c = request["color2"]
        if isinstance(c, list) and len(c) == 3:
            color2 = tuple(c)
        else:
            raise HTTPException(status_code=400, detail="color2 must be [R, G, B] array")

    if "color3" in request:
        c = request["color3"]
        if isinstance(c, list) and len(c) == 3:
            color3 = tuple(c)
        else:
            raise HTTPException(status_code=400, detail="color3 must be [R, G, B] array")

    if not any([color1, color2, color3]):
        raise HTTPException(status_code=400, detail="Must provide at least one color")

    try:
        controller = state.led_controller.get_controller()
        # Power on LEDs when user manually sets colors via UI
        controller.set_power(1)
        # Reset idle timeout for manual interaction (only if idle timeout is enabled)
        if state.dw_led_idle_timeout_enabled:
            state.dw_led_last_activity_time = time.time()
        return controller.set_colors(color1=color1, color2=color2, color3=color3)
    except Exception as e:
        logger.error(f"Failed to set DW LED colors: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dw_leds/effects")
async def dw_leds_effects():
    """Get list of available effects"""
    if not state.led_controller or state.led_provider != "board":
        raise HTTPException(status_code=400, detail="DW LEDs not configured")

    try:
        controller = state.led_controller.get_controller()
        effects = controller.get_effects()
        # Convert tuples to lists for JSON serialization
        effects_list = [[eid, name] for eid, name in effects]
        result = {"success": True, "effects": effects_list}
        # Board provider: also expose the firmware effect *names* (id -> name),
        # which the ball tracker's background sub-effect picker needs.
        if state.led_provider == "board":
            from modules.led.board_led_controller import BOARD_EFFECTS
            result["names"] = [[i, name] for i, (name, _label) in enumerate(BOARD_EFFECTS)]
        return result
    except Exception as e:
        logger.error(f"Failed to get DW LED effects: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dw_leds/palettes")
async def dw_leds_palettes():
    """Get list of available palettes"""
    if not state.led_controller or state.led_provider != "board":
        raise HTTPException(status_code=400, detail="DW LEDs not configured")

    try:
        controller = state.led_controller.get_controller()
        palettes = controller.get_palettes()
        # Convert tuples to lists for JSON serialization
        palettes_list = [[pid, name] for pid, name in palettes]
        return {
            "success": True,
            "palettes": palettes_list
        }
    except Exception as e:
        logger.error(f"Failed to get DW LED palettes: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/dw_leds/effect")
async def dw_leds_effect(request: dict):
    """Set effect by ID (manual UI control - always powers on LEDs)"""
    if not state.led_controller or state.led_provider != "board":
        raise HTTPException(status_code=400, detail="DW LEDs not configured")

    effect_id = request.get("effect_id", 0)
    speed = request.get("speed")
    intensity = request.get("intensity")

    try:
        controller = state.led_controller.get_controller()
        # Power on LEDs when user manually sets effect via UI
        controller.set_power(1)
        # Reset idle timeout for manual interaction (only if idle timeout is enabled)
        if state.dw_led_idle_timeout_enabled:
            state.dw_led_last_activity_time = time.time()
        return controller.set_effect(effect_id, speed=speed, intensity=intensity)
    except Exception as e:
        logger.error(f"Failed to set DW LED effect: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/dw_leds/palette")
async def dw_leds_palette(request: dict):
    """Set palette by ID (manual UI control - always powers on LEDs)"""
    if not state.led_controller or state.led_provider != "board":
        raise HTTPException(status_code=400, detail="DW LEDs not configured")

    palette_id = request.get("palette_id", 0)

    try:
        controller = state.led_controller.get_controller()
        # Power on LEDs when user manually sets palette via UI
        controller.set_power(1)
        # Reset idle timeout for manual interaction (only if idle timeout is enabled)
        if state.dw_led_idle_timeout_enabled:
            state.dw_led_last_activity_time = time.time()
        return controller.set_palette(palette_id)
    except Exception as e:
        logger.error(f"Failed to set DW LED palette: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/dw_leds/speed")
async def dw_leds_speed(request: dict):
    """Set effect speed (0-255)"""
    if not state.led_controller or state.led_provider != "board":
        raise HTTPException(status_code=400, detail="DW LEDs not configured")

    value = request.get("speed", 128)
    if not 0 <= value <= 255:
        raise HTTPException(status_code=400, detail="Speed must be between 0 and 255")

    try:
        controller = state.led_controller.get_controller()
        return controller.set_speed(value)
    except Exception as e:
        logger.error(f"Failed to set LED speed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/dw_leds/ball")
async def dw_leds_ball(request: dict):
    """Tune the firmware-native 'ball' tracker effect (board provider only).

    Accepts any of: fgbright, bgbright, size, align (ints), direction ('cw'|'ccw'),
    bg (background sub-effect name / 'static' / 'off'), color, color2 (RRGGBB hex).
    Applied live via /sand_led; persisted to the board's NVS at idle.
    """
    if not state.led_controller or state.led_provider != "board":
        raise HTTPException(status_code=400, detail="The ball tracker requires the Table LEDs provider")

    try:
        controller = state.led_controller.get_controller()
        return await asyncio.to_thread(controller.set_ball, **request)
    except Exception as e:
        logger.error(f"Failed to set ball effect: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/dw_leds/intensity")
async def dw_leds_intensity(request: dict):
    """Set effect intensity (0-255)"""
    if not state.led_controller or state.led_provider != "board":
        raise HTTPException(status_code=400, detail="DW LEDs not configured")

    value = request.get("intensity", 128)
    if not 0 <= value <= 255:
        raise HTTPException(status_code=400, detail="Intensity must be between 0 and 255")

    try:
        controller = state.led_controller.get_controller()
        return controller.set_intensity(value)
    except Exception as e:
        logger.error(f"Failed to set LED intensity: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/dw_leds/save_effect_settings")
async def dw_leds_save_effect_settings(request: dict):
    """Save current LED settings as idle or playing effect"""
    effect_type = request.get("type")  # 'idle' or 'playing'

    settings = {
        "effect_id": request.get("effect_id"),
        "palette_id": request.get("palette_id"),
        "speed": request.get("speed"),
        "intensity": request.get("intensity"),
        "color1": request.get("color1"),
        "color2": request.get("color2"),
        "color3": request.get("color3")
    }

    if effect_type not in ("idle", "playing"):
        raise HTTPException(status_code=400, detail="Invalid effect type. Must be 'idle' or 'playing'")

    # Board provider: the firmware switches effects itself — persist the choice
    # as $LED/IdleEffect / $LED/RunEffect on the board instead of host state.
    if state.led_provider == "board":
        from modules.led.board_led_controller import effect_name_for_id
        name = effect_name_for_id(int(settings.get("effect_id") or 0)) or "none"
        controller = state.led_controller.get_controller() if state.led_controller else None
        if not controller:
            raise HTTPException(status_code=409, detail="Table LEDs not configured")
        ok = await asyncio.to_thread(
            controller.set_idle_effect if effect_type == "idle" else controller.set_run_effect, name
        )
        if not ok:
            raise HTTPException(status_code=502, detail="Table rejected the setting (is it idle?)")
        logger.info(f"Board LED {effect_type} effect set to {name}")
        return {"success": True, "type": effect_type, "settings": settings}

    raise HTTPException(status_code=400, detail="Effect automation requires the Table LEDs provider")

@app.post("/api/dw_leds/clear_effect_settings")
async def dw_leds_clear_effect_settings(request: dict):
    """Clear idle or playing effect settings"""
    effect_type = request.get("type")  # 'idle' or 'playing'

    if effect_type not in ("idle", "playing"):
        raise HTTPException(status_code=400, detail="Invalid effect type. Must be 'idle' or 'playing'")

    if state.led_provider == "board":
        controller = state.led_controller.get_controller() if state.led_controller else None
        if not controller:
            raise HTTPException(status_code=409, detail="Table LEDs not configured")
        ok = await asyncio.to_thread(
            controller.set_idle_effect if effect_type == "idle" else controller.set_run_effect, "none"
        )
        if not ok:
            raise HTTPException(status_code=502, detail="Table rejected the setting (is it idle?)")
        logger.info(f"Board LED {effect_type} effect disabled")
        return {"success": True, "type": effect_type}

    raise HTTPException(status_code=400, detail="Effect automation requires the Table LEDs provider")

@app.get("/api/dw_leds/get_effect_settings")
async def dw_leds_get_effect_settings():
    """Get saved idle and playing effect settings"""
    # Board provider: the choices live on the board ($LED/IdleEffect / RunEffect).
    if state.led_provider == "board" and state.led_controller:
        from modules.led.board_led_controller import effect_id_for_name
        status = await asyncio.to_thread(state.led_controller.check_status)
        if status.get("connected"):
            def as_settings(name):
                if not name or name == "none":
                    return None
                return {"effect_id": effect_id_for_name(name), "palette_id": None,
                        "speed": None, "intensity": None,
                        "color1": None, "color2": None, "color3": None}
            return {
                "idle_effect": as_settings(status.get("idle_effect")),
                "playing_effect": as_settings(status.get("run_effect")),
            }
    return {"idle_effect": None, "playing_effect": None}

@app.post("/api/dw_leds/idle_timeout")
async def dw_leds_set_idle_timeout(request: dict):
    """Configure LED idle timeout settings"""
    enabled = request.get("enabled", False)
    minutes = request.get("minutes", 30)

    # Validate minutes (between 1 and 1440 - 24 hours)
    if minutes < 1 or minutes > 1440:
        raise HTTPException(status_code=400, detail="Timeout must be between 1 and 1440 minutes")

    state.dw_led_idle_timeout_enabled = enabled
    state.dw_led_idle_timeout_minutes = minutes

    # Reset activity time when settings change
    import time
    state.dw_led_last_activity_time = time.time()

    state.save()
    logger.info(f"DW LED idle timeout configured: enabled={enabled}, minutes={minutes}")

    return {
        "success": True,
        "enabled": enabled,
        "minutes": minutes
    }

@app.get("/api/dw_leds/idle_timeout")
async def dw_leds_get_idle_timeout():
    """Get LED idle timeout settings"""
    import time

    # Calculate remaining time if timeout is active
    remaining_minutes = None
    if state.dw_led_idle_timeout_enabled and state.dw_led_last_activity_time:
        elapsed_seconds = time.time() - state.dw_led_last_activity_time
        timeout_seconds = state.dw_led_idle_timeout_minutes * 60
        remaining_seconds = max(0, timeout_seconds - elapsed_seconds)
        remaining_minutes = round(remaining_seconds / 60, 1)

    return {
        "enabled": state.dw_led_idle_timeout_enabled,
        "minutes": state.dw_led_idle_timeout_minutes,
        "remaining_minutes": remaining_minutes
    }

# ── Screen (LCD backlight) control endpoints ──────────────────────

@app.get("/api/screen/status")
async def screen_status():
    """Get screen controller status."""
    if not state.screen_controller:
        return {"available": False, "message": "Screen controller not initialized"}
    return state.screen_controller.get_status()

@app.post("/api/screen/power")
async def screen_power(request: dict):
    """Turn screen on/off. Body: {"on": true/false}"""
    if not state.screen_controller or not state.screen_controller.available:
        raise HTTPException(status_code=400, detail="Screen control not available")

    on = request.get("on", True)
    result = state.screen_controller.set_power(on)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

    # Publish updated state to MQTT
    if state.mqtt_handler and state.mqtt_handler.is_enabled:
        state.mqtt_handler._publish_screen_state()

    return result

@app.post("/api/screen/brightness")
async def screen_brightness(request: dict):
    """Set screen brightness. Body: {"value": 0-max_brightness}"""
    if not state.screen_controller or not state.screen_controller.available:
        raise HTTPException(status_code=400, detail="Screen control not available")

    value = request.get("value", 128)
    result = state.screen_controller.set_brightness(value)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("message", "Unknown error"))

    # Publish updated state to MQTT
    if state.mqtt_handler and state.mqtt_handler.is_enabled:
        state.mqtt_handler._publish_screen_state()

    return result

@app.get("/table_control")
async def table_control_page(request: Request):
    return get_redirect_response(request)

@app.get("/cache-progress")
async def get_cache_progress_endpoint():
    """Get the current cache generation progress."""
    from modules.core.cache_manager import get_cache_progress
    return get_cache_progress()

@app.post("/rebuild_cache")
async def rebuild_cache_endpoint():
    """Trigger a rebuild of the pattern cache."""
    try:
        from modules.core.cache_manager import rebuild_cache
        await rebuild_cache()
        return {"success": True, "message": "Cache rebuild completed successfully"}
    except Exception as e:
        logger.error(f"Failed to rebuild cache: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info("Received shutdown signal, cleaning up...")
    try:
        # Turn off all LEDs on shutdown
        if state.led_controller:
            state.led_controller.set_power(0)

        state.save()
        logger.info("Cleanup completed")
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")
    finally:
        logger.info("Exiting application...")
        # Use os._exit after cleanup is complete to avoid async stack tracebacks
        # This is safe because we've already: shut down process pool, stopped motion controller, saved state
        os._exit(0)

@app.get("/api/version")
async def get_version_info(force_refresh: bool = False):
    """Get current and latest version information

    Args:
        force_refresh: If true, bypass cache and fetch fresh data from GitHub
    """
    try:
        version_info = await version_manager.get_version_info(force_refresh=force_refresh)
        return JSONResponse(content=version_info)
    except Exception as e:
        logger.error(f"Error getting version info: {e}")
        return JSONResponse(
            content={
                "current": await version_manager.get_current_version(),
                "latest": await version_manager.get_current_version(),
                "update_available": False,
                "error": "Unable to check for updates"
            },
            status_code=200
        )

@app.post("/api/update")
async def trigger_update():
    """Trigger software update by running `dw update` as a detached process.

    The `dw` CLI handles pulling code and restarting the service.
    We fire-and-forget so the response returns immediately before the
    service goes down for restart.
    """
    try:
        logger.info("Update triggered via API")
        dw_path = '/usr/local/bin/dw'
        log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'update.log')
        logger.info(f"Running: {dw_path} update (log: {log_file})")
        with open(log_file, 'w') as f:
            subprocess.Popen(
                [dw_path, 'update'],
                stdout=f,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
        return JSONResponse(content={
            "success": True,
            "message": "Update started"
        })
    except Exception as e:
        logger.error(f"Error triggering update: {e}")
        return JSONResponse(
            content={"success": False, "message": f"Failed to trigger update: {str(e)}"},
            status_code=500
        )

@app.post("/api/system/shutdown")
async def shutdown_system():
    """Shutdown the system"""
    try:
        logger.warning("Shutdown initiated via API")

        # Schedule shutdown command after a short delay to allow response to be sent
        def delayed_shutdown():
            time.sleep(2)  # Give time for response to be sent
            try:
                subprocess.run(["/usr/bin/sudo", "/usr/bin/systemctl", "poweroff"], check=True)
                logger.info("System shutdown command executed successfully")
            except FileNotFoundError:
                logger.error("sudo or systemctl command not found - ensure systemd is available")
            except Exception as e:
                logger.error(f"Error executing host shutdown command: {e}")

        import threading
        shutdown_thread = threading.Thread(target=delayed_shutdown)
        shutdown_thread.start()

        return {"success": True, "message": "System shutdown initiated"}
    except Exception as e:
        logger.error(f"Error initiating shutdown: {e}")
        return JSONResponse(
            content={"success": False, "message": str(e)},
            status_code=500
        )

@app.post("/api/system/restart")
async def restart_system():
    """Restart the Dune Weaver service via systemctl."""
    try:
        logger.warning("Restart initiated via API")

        # Schedule restart command after a short delay to allow response to be sent
        def delayed_restart():
            time.sleep(2)  # Give time for response to be sent
            try:
                subprocess.run(["/usr/bin/sudo", "/usr/bin/systemctl", "restart", "dune-weaver"], check=True)
                logger.info("Service restart command executed successfully")
            except FileNotFoundError:
                logger.error("sudo or systemctl command not found - ensure systemd is available")
            except Exception as e:
                logger.error(f"Error executing service restart: {e}")

        import threading
        restart_thread = threading.Thread(target=delayed_restart)
        restart_thread.start()

        return {"success": True, "message": "System restart initiated"}
    except Exception as e:
        logger.error(f"Error initiating restart: {e}")
        return JSONResponse(
            content={"success": False, "message": str(e)},
            status_code=500
        )

###############################################################################
# FluidNC Config Endpoints
###############################################################################

def entrypoint():
    import uvicorn
    logger.info("Starting FastAPI server on port 8080...")
    uvicorn.run(app, host="0.0.0.0", port=8080, workers=1)  # Set workers to 1 to avoid multiple signal handlers

if __name__ == "__main__":
    entrypoint()