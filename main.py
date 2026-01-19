from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional, Tuple, Dict, Any, Union
import atexit
import os
import logging
from datetime import datetime, time
from modules.connection import connection_manager
from modules.core import pattern_manager
from modules.core.pattern_manager import parse_theta_rho_file, THETA_RHO_DIR
from modules.core import playlist_manager
from modules.update import update_manager
from modules.core.state import state
from modules import mqtt
import signal
import sys
import asyncio
from contextlib import asynccontextmanager
from modules.led.led_controller import LEDController, effect_idle
from modules.led.led_interface import LEDInterface
from modules.led.idle_timeout_manager import idle_timeout_manager
import math
from modules.core.cache_manager import generate_all_image_previews, get_cache_path, generate_image_preview, get_pattern_metadata
from modules.core.version_manager import version_manager
from modules.core.log_handler import init_memory_handler, get_memory_handler
import json
import base64
import time
import argparse
import subprocess
import platform
from modules.core import process_pool as pool_module

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
init_memory_handler(max_entries=500)

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

    # Initialize shared process pool for CPU-intensive tasks
    pool_module.init_pool()

    # Pin main process to CPUs 1-N to keep CPU 0 dedicated to motion/LED
    from modules.core import scheduling
    background_cpus = scheduling.get_background_cpus()
    if background_cpus:
        scheduling.pin_to_cpus(background_cpus)
        logger.info(f"FastAPI main process pinned to CPUs {sorted(background_cpus)}")
    else:
        logger.info("Single-core system detected, skipping CPU pinning")

    # Connect device in background so the web server starts immediately
    async def connect_and_home():
        """Connect to device and perform homing in background."""
        try:
            # Connect without homing first (fast)
            await asyncio.to_thread(connection_manager.connect_device, False)

            # If connected, perform homing in background
            if state.conn and state.conn.is_connected():
                logger.info("Device connected, starting homing in background...")
                state.is_homing = True
                try:
                    success = await asyncio.to_thread(connection_manager.home)
                    if not success:
                        logger.warning("Background homing failed or was skipped")
                finally:
                    state.is_homing = False
                    logger.info("Background homing completed")

                # After homing, check for auto_play mode
                if state.auto_play_enabled and state.auto_play_playlist:
                    logger.info(f"Homing complete, checking auto_play playlist: {state.auto_play_playlist}")
                    try:
                        playlist_exists = playlist_manager.get_playlist(state.auto_play_playlist) is not None
                        if not playlist_exists:
                            logger.warning(f"Auto-play playlist '{state.auto_play_playlist}' not found. Clearing invalid reference.")
                            state.auto_play_playlist = None
                            state.save()
                        elif state.conn and state.conn.is_connected():
                            logger.info(f"Starting auto-play playlist: {state.auto_play_playlist}")
                            asyncio.create_task(playlist_manager.run_playlist(
                                state.auto_play_playlist,
                                pause_time=state.auto_play_pause_time,
                                clear_pattern=state.auto_play_clear_pattern,
                                run_mode=state.auto_play_run_mode,
                                shuffle=state.auto_play_shuffle
                            ))
                    except Exception as e:
                        logger.error(f"Failed to auto-play playlist: {str(e)}")
        except Exception as e:
            logger.warning(f"Failed to auto-connect to serial port: {str(e)}")

    # Start connection/homing in background - doesn't block server startup
    asyncio.create_task(connect_and_home())

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
        elif state.led_provider == "dw_leds":
            state.led_controller = LEDInterface(
                "dw_leds",
                num_leds=state.dw_led_num_leds,
                gpio_pin=state.dw_led_gpio_pin,
                pixel_order=state.dw_led_pixel_order,
                brightness=state.dw_led_brightness / 100.0,
                speed=state.dw_led_speed,
                intensity=state.dw_led_intensity
            )
            logger.info(f"LED controller initialized: DW LEDs ({state.dw_led_num_leds} LEDs on GPIO{state.dw_led_gpio_pin}, pixel order: {state.dw_led_pixel_order})")

            # Initialize hardware and start idle effect (matches behavior of /set_led_config)
            status = state.led_controller.check_status()
            if status.get("connected", False):
                state.led_controller.effect_idle(state.dw_led_idle_effect)
                _start_idle_led_timeout()
                logger.info("DW LEDs hardware initialized and idle effect started")
            else:
                error_msg = status.get("error", "Unknown error")
                logger.warning(f"DW LED hardware initialization failed: {error_msg}")
        else:
            state.led_controller = None
            logger.info("LED controller not configured")

        # Save if provider was auto-detected
        if state.led_provider and state.wled_ip:
            state.save()
    except Exception as e:
        logger.warning(f"Failed to initialize LED controller: {str(e)}")
        state.led_controller = None

    # Note: auto_play is now handled in connect_and_home() after homing completes

    try:
        mqtt_handler = mqtt.init_mqtt()
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

    # Start idle timeout monitor
    async def idle_timeout_monitor():
        """Monitor LED idle timeout and turn off LEDs when timeout expires."""
        import time
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds

                if not state.dw_led_idle_timeout_enabled:
                    continue

                if not state.led_controller or not state.led_controller.is_configured:
                    continue

                # Check if we're currently playing a pattern
                is_playing = bool(state.current_playing_file or state.current_playlist)
                if is_playing:
                    # Reset activity time when playing
                    state.dw_led_last_activity_time = time.time()
                    continue

                # If no activity time set, initialize it
                if state.dw_led_last_activity_time is None:
                    state.dw_led_last_activity_time = time.time()
                    continue

                # Calculate idle duration
                idle_seconds = time.time() - state.dw_led_last_activity_time
                timeout_seconds = state.dw_led_idle_timeout_minutes * 60

                # Turn off LEDs if timeout expired
                if idle_seconds >= timeout_seconds:
                    status = state.led_controller.check_status()
                    # Check both "power" (WLED) and "power_on" (DW LEDs) keys
                    is_powered_on = status.get("power", False) or status.get("power_on", False)
                    if is_powered_on:  # Only turn off if currently on
                        logger.info(f"Idle timeout ({state.dw_led_idle_timeout_minutes} minutes) expired, turning off LEDs")
                        state.led_controller.set_power(0)
                        # Reset activity time to prevent repeated turn-off attempts
                        state.dw_led_last_activity_time = time.time()

            except Exception as e:
                logger.error(f"Error in idle timeout monitor: {e}")
                await asyncio.sleep(60)  # Wait longer on error

    asyncio.create_task(idle_timeout_monitor())

    yield  # This separates startup from shutdown code

    # Shutdown
    logger.info("Shutting down Dune Weaver application...")

    # Shutdown process pool
    pool_module.shutdown_pool(wait=True)

app = FastAPI(lifespan=lifespan)

# Add CORS middleware to allow cross-origin requests from other Dune Weaver frontends
# This enables multi-table control from a single frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local network access
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

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
    provider: str  # "wled", "dw_leds", or "none"
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

class ConnectionSettingsUpdate(BaseModel):
    preferred_port: Optional[str] = None

class PatternSettingsUpdate(BaseModel):
    clear_pattern_speed: Optional[int] = None
    custom_clear_from_in: Optional[str] = None
    custom_clear_from_out: Optional[str] = None

class AutoPlaySettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    playlist: Optional[str] = None
    run_mode: Optional[str] = None
    pause_time: Optional[float] = None
    clear_pattern: Optional[str] = None
    shuffle: Optional[bool] = None

class ScheduledPauseSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    control_wled: Optional[bool] = None
    finish_pattern: Optional[bool] = None
    timezone: Optional[str] = None  # IANA timezone (e.g., "America/New_York") or None for system default
    time_slots: Optional[List[TimeSlot]] = None

class HomingSettingsUpdate(BaseModel):
    mode: Optional[int] = None
    angular_offset_degrees: Optional[float] = None
    auto_home_enabled: Optional[bool] = None
    auto_home_after_patterns: Optional[int] = None

class DwLedSettingsUpdate(BaseModel):
    num_leds: Optional[int] = None
    gpio_pin: Optional[int] = None
    pixel_order: Optional[str] = None
    brightness: Optional[int] = None
    speed: Optional[int] = None
    intensity: Optional[int] = None
    idle_effect: Optional[dict] = None
    playing_effect: Optional[dict] = None
    idle_timeout_enabled: Optional[bool] = None
    idle_timeout_minutes: Optional[int] = None

class LedSettingsUpdate(BaseModel):
    provider: Optional[str] = None  # "none", "wled", "dw_leds"
    wled_ip: Optional[str] = None
    dw_led: Optional[DwLedSettingsUpdate] = None

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
    table_type_override: Optional[str] = None  # Override detected table type, or empty string/"auto" to clear
    timezone: Optional[str] = None  # IANA timezone (e.g., "America/New_York", "UTC")

class SettingsUpdate(BaseModel):
    """Request model for PATCH /api/settings - all fields optional for partial updates"""
    app: Optional[AppSettingsUpdate] = None
    connection: Optional[ConnectionSettingsUpdate] = None
    patterns: Optional[PatternSettingsUpdate] = None
    auto_play: Optional[AutoPlaySettingsUpdate] = None
    scheduled_pause: Optional[ScheduledPauseSettingsUpdate] = None
    homing: Optional[HomingSettingsUpdate] = None
    led: Optional[LedSettingsUpdate] = None
    mqtt: Optional[MqttSettingsUpdate] = None
    machine: Optional[MachineSettingsUpdate] = None

# Store active WebSocket connections
active_status_connections = set()
active_cache_progress_connections = set()

@app.websocket("/ws/status")
async def websocket_status_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_status_connections.add(websocket)
    try:
        while True:
            status = pattern_manager.get_status()
            try:
                await websocket.send_json({
                    "type": "status_update",
                    "data": status
                })
            except RuntimeError as e:
                if "close message has been sent" in str(e):
                    break
                raise
            await asyncio.sleep(1)
    except WebSocketDisconnect:
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
async def get_logs(limit: int = 100, level: str = None):
    """
    Retrieve application logs from memory buffer.

    Args:
        limit: Maximum number of log entries to return (default: 100, max: 500)
        level: Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        List of log entries with timestamp, level, logger, and message.
    """
    handler = get_memory_handler()
    if not handler:
        return {"logs": [], "error": "Log handler not initialized"}

    # Clamp limit to reasonable range
    limit = max(1, min(limit, 500))

    logs = handler.get_logs(limit=limit, level=level)
    return {"logs": logs, "count": len(logs)}


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
        "connection": {
            "preferred_port": state.preferred_port
        },
        "patterns": {
            "clear_pattern_speed": state.clear_pattern_speed,
            "custom_clear_from_in": state.custom_clear_from_in,
            "custom_clear_from_out": state.custom_clear_from_out
        },
        "auto_play": {
            "enabled": state.auto_play_enabled,
            "playlist": state.auto_play_playlist,
            "run_mode": state.auto_play_run_mode,
            "pause_time": state.auto_play_pause_time,
            "clear_pattern": state.auto_play_clear_pattern,
            "shuffle": state.auto_play_shuffle
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
            "auto_home_enabled": state.auto_home_enabled,
            "auto_home_after_patterns": state.auto_home_after_patterns
        },
        "led": {
            "provider": state.led_provider,
            "wled_ip": state.wled_ip,
            "dw_led": {
                "num_leds": state.dw_led_num_leds,
                "gpio_pin": state.dw_led_gpio_pin,
                "pixel_order": state.dw_led_pixel_order,
                "brightness": state.dw_led_brightness,
                "speed": state.dw_led_speed,
                "intensity": state.dw_led_intensity,
                "idle_effect": state.dw_led_idle_effect,
                "playing_effect": state.dw_led_playing_effect,
                "idle_timeout_enabled": state.dw_led_idle_timeout_enabled,
                "idle_timeout_minutes": state.dw_led_idle_timeout_minutes
            }
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
            "detected_table_type": state.table_type,
            "table_type_override": state.table_type_override,
            "effective_table_type": state.table_type_override or state.table_type,
            "gear_ratio": state.gear_ratio,
            "x_steps_per_mm": state.x_steps_per_mm,
            "y_steps_per_mm": state.y_steps_per_mm,
            "timezone": state.timezone,
            "available_table_types": [
                {"value": "dune_weaver_mini", "label": "Dune Weaver Mini"},
                {"value": "dune_weaver_mini_pro", "label": "Dune Weaver Mini Pro"},
                {"value": "dune_weaver_mini_pro_byj", "label": "Dune Weaver Mini Pro (BYJ)"},
                {"value": "dune_weaver_gold", "label": "Dune Weaver Gold"},
                {"value": "dune_weaver", "label": "Dune Weaver"},
                {"value": "dune_weaver_pro", "label": "Dune Weaver Pro"}
            ]
        }
    }

@app.patch("/api/settings", tags=["settings"])
async def update_settings(settings_update: SettingsUpdate):
    """
    Partially update application settings.

    Only include the categories and fields you want to update.
    All fields are optional - only provided values will be updated.

    Example: {"app": {"name": "My Sand Table"}, "auto_play": {"enabled": true}}
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

    # Connection settings
    if settings_update.connection:
        if settings_update.connection.preferred_port is not None:
            # Store exactly what frontend sends: "__auto__", "__none__", or specific port
            state.preferred_port = settings_update.connection.preferred_port
        updated_categories.append("connection")

    # Pattern settings
    if settings_update.patterns:
        p = settings_update.patterns
        if p.clear_pattern_speed is not None:
            state.clear_pattern_speed = p.clear_pattern_speed if p.clear_pattern_speed > 0 else None
        if p.custom_clear_from_in is not None:
            state.custom_clear_from_in = p.custom_clear_from_in or None
        if p.custom_clear_from_out is not None:
            state.custom_clear_from_out = p.custom_clear_from_out or None
        updated_categories.append("patterns")

    # Auto-play settings
    if settings_update.auto_play:
        ap = settings_update.auto_play
        if ap.enabled is not None:
            state.auto_play_enabled = ap.enabled
        if ap.playlist is not None:
            state.auto_play_playlist = ap.playlist or None
        if ap.run_mode is not None:
            state.auto_play_run_mode = ap.run_mode
        if ap.pause_time is not None:
            state.auto_play_pause_time = ap.pause_time
        if ap.clear_pattern is not None:
            state.auto_play_clear_pattern = ap.clear_pattern
        if ap.shuffle is not None:
            state.auto_play_shuffle = ap.shuffle
        updated_categories.append("auto_play")

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

    # Homing settings
    if settings_update.homing:
        h = settings_update.homing
        if h.mode is not None:
            state.homing = h.mode
            state.homing_user_override = True  # User explicitly set preference
        if h.angular_offset_degrees is not None:
            state.angular_homing_offset_degrees = h.angular_offset_degrees
        if h.auto_home_enabled is not None:
            state.auto_home_enabled = h.auto_home_enabled
        if h.auto_home_after_patterns is not None:
            state.auto_home_after_patterns = h.auto_home_after_patterns
        updated_categories.append("homing")

    # LED settings
    if settings_update.led:
        led = settings_update.led
        if led.provider is not None:
            state.led_provider = led.provider
            if led.provider != old_led_provider:
                led_reinit_needed = True
        if led.wled_ip is not None:
            state.wled_ip = led.wled_ip or None
        if led.dw_led:
            dw = led.dw_led
            if dw.num_leds is not None:
                state.dw_led_num_leds = dw.num_leds
            if dw.gpio_pin is not None:
                state.dw_led_gpio_pin = dw.gpio_pin
            if dw.pixel_order is not None:
                state.dw_led_pixel_order = dw.pixel_order
            if dw.brightness is not None:
                state.dw_led_brightness = dw.brightness
            if dw.speed is not None:
                state.dw_led_speed = dw.speed
            if dw.intensity is not None:
                state.dw_led_intensity = dw.intensity
            if dw.idle_effect is not None:
                state.dw_led_idle_effect = dw.idle_effect
            if dw.playing_effect is not None:
                state.dw_led_playing_effect = dw.playing_effect
            if dw.idle_timeout_enabled is not None:
                state.dw_led_idle_timeout_enabled = dw.idle_timeout_enabled
            if dw.idle_timeout_minutes is not None:
                state.dw_led_idle_timeout_minutes = dw.idle_timeout_minutes
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

    # Machine settings
    if settings_update.machine:
        m = settings_update.machine
        if m.table_type_override is not None:
            # Empty string or "auto" clears the override
            state.table_type_override = None if m.table_type_override in ("", "auto") else m.table_type_override
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

# ============================================================================
# Multi-Table Identity Endpoints
# ============================================================================

class TableInfoUpdate(BaseModel):
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
        state.table_name = update.name.strip() or "My Sand Table"
        state.save()
        logger.info(f"Table name updated to: {state.table_name}")

    return {
        "success": True,
        "id": state.table_id,
        "name": state.table_name
    }

# ============================================================================
# Individual Settings Endpoints (Deprecated - use /api/settings instead)
# ============================================================================

@app.get("/api/auto_play-mode", deprecated=True, tags=["settings-deprecated"])
async def get_auto_play_mode():
    """DEPRECATED: Use GET /api/settings instead. Get current auto_play mode settings."""
    return {
        "enabled": state.auto_play_enabled,
        "playlist": state.auto_play_playlist,
        "run_mode": state.auto_play_run_mode,
        "pause_time": state.auto_play_pause_time,
        "clear_pattern": state.auto_play_clear_pattern,
        "shuffle": state.auto_play_shuffle
    }

@app.post("/api/auto_play-mode", deprecated=True, tags=["settings-deprecated"])
async def set_auto_play_mode(request: auto_playModeRequest):
    """DEPRECATED: Use PATCH /api/settings instead. Update auto_play mode settings."""
    state.auto_play_enabled = request.enabled
    if request.playlist is not None:
        state.auto_play_playlist = request.playlist
    if request.run_mode is not None:
        state.auto_play_run_mode = request.run_mode
    if request.pause_time is not None:
        state.auto_play_pause_time = request.pause_time
    if request.clear_pattern is not None:
        state.auto_play_clear_pattern = request.clear_pattern
    if request.shuffle is not None:
        state.auto_play_shuffle = request.shuffle
    state.save()
    
    logger.info(f"auto_play mode {'enabled' if request.enabled else 'disabled'}, playlist: {request.playlist}")
    return {"success": True, "message": "auto_play mode settings updated"}

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
                start_time = datetime.strptime(slot.start_time, "%H:%M").time()
                end_time = datetime.strptime(slot.end_time, "%H:%M").time()
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
    logger.debug("Listing available serial ports")
    return await asyncio.to_thread(connection_manager.list_serial_ports)

@app.post("/connect")
async def connect(request: ConnectRequest):
    if not request.port:
        state.conn = connection_manager.WebSocketConnection('ws://fluidnc.local:81')
        if not connection_manager.device_init():
            raise HTTPException(status_code=500, detail="Failed to initialize device - could not get machine parameters")
        logger.info('Successfully connected to websocket ws://fluidnc.local:81')
        return {"success": True}

    try:
        state.conn = connection_manager.SerialConnection(request.port)
        if not connection_manager.device_init():
            raise HTTPException(status_code=500, detail="Failed to initialize device - could not get machine parameters")
        logger.info(f'Successfully connected to serial port {request.port}')
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'Failed to connect to serial port {request.port}: {str(e)}')
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/disconnect")
async def disconnect():
    try:
        state.conn.close()
        logger.info('Successfully disconnected from serial port')
        return {"success": True}
    except Exception as e:
        logger.error(f'Failed to disconnect serial: {str(e)}')
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/restart_connection")
async def restart(request: ConnectRequest):
    if not request.port:
        logger.warning("Restart serial request received without port")
        raise HTTPException(status_code=400, detail="No port provided")

    try:
        logger.info(f"Restarting connection on port {request.port}")
        connection_manager.restart_connection()
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to restart serial on port {request.port}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


###############################################################################
# Debug Serial Terminal - Independent raw serial communication
###############################################################################

# Store for debug serial connections (separate from main connection)
_debug_serial_connections: dict = {}
_debug_serial_lock: Optional[asyncio.Lock] = None

def get_debug_serial_lock() -> asyncio.Lock:
    """Get or create the debug serial lock in the current event loop."""
    global _debug_serial_lock
    if _debug_serial_lock is None:
        _debug_serial_lock = asyncio.Lock()
    return _debug_serial_lock

class DebugSerialRequest(BaseModel):
    port: str
    baudrate: int = 115200
    timeout: float = 2.0

class DebugSerialCommand(BaseModel):
    port: str
    command: str
    timeout: float = 2.0

@app.post("/api/debug-serial/open", tags=["debug-serial"])
async def debug_serial_open(request: DebugSerialRequest):
    """Open a debug serial connection (independent of main connection)."""
    import serial

    async with get_debug_serial_lock():
        # Close existing connection on this port if any
        if request.port in _debug_serial_connections:
            try:
                _debug_serial_connections[request.port].close()
            except:
                pass
            del _debug_serial_connections[request.port]

        try:
            ser = serial.Serial(
                request.port,
                baudrate=request.baudrate,
                timeout=request.timeout
            )
            _debug_serial_connections[request.port] = ser
            logger.info(f"Debug serial opened on {request.port}")
            return {"success": True, "port": request.port, "baudrate": request.baudrate}
        except Exception as e:
            logger.error(f"Failed to open debug serial on {request.port}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/debug-serial/close", tags=["debug-serial"])
async def debug_serial_close(request: ConnectRequest):
    """Close a debug serial connection."""
    async with get_debug_serial_lock():
        if request.port not in _debug_serial_connections:
            return {"success": True, "message": "Port not open"}

        try:
            _debug_serial_connections[request.port].close()
            del _debug_serial_connections[request.port]
            logger.info(f"Debug serial closed on {request.port}")
            return {"success": True}
        except Exception as e:
            logger.error(f"Failed to close debug serial on {request.port}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/debug-serial/send", tags=["debug-serial"])
async def debug_serial_send(request: DebugSerialCommand):
    """Send a command and receive response on debug serial connection."""
    import serial

    async with get_debug_serial_lock():
        if request.port not in _debug_serial_connections:
            raise HTTPException(status_code=400, detail="Port not open. Open it first.")

        ser = _debug_serial_connections[request.port]

        try:
            # Clear input buffer
            ser.reset_input_buffer()

            # Send command with newline
            command = request.command.strip()
            if not command.endswith('\n'):
                command += '\n'

            await asyncio.to_thread(ser.write, command.encode())
            await asyncio.to_thread(ser.flush)

            # Read response lines with timeout
            responses = []
            start_time = time.time()
            original_timeout = ser.timeout
            ser.timeout = 0.1  # Short timeout for reading

            while time.time() - start_time < request.timeout:
                try:
                    line = await asyncio.to_thread(ser.readline)
                    if line:
                        decoded = line.decode('utf-8', errors='replace').strip()
                        if decoded:
                            responses.append(decoded)
                            # Check for ok/error to know command completed
                            if decoded.lower() in ['ok', 'error'] or decoded.lower().startswith('error:'):
                                break
                    else:
                        # No data, small delay
                        await asyncio.sleep(0.05)
                except:
                    break

            ser.timeout = original_timeout

            return {
                "success": True,
                "command": request.command.strip(),
                "responses": responses,
                "raw": '\n'.join(responses)
            }
        except Exception as e:
            logger.error(f"Debug serial send error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/debug-serial/status", tags=["debug-serial"])
async def debug_serial_status():
    """Get status of all debug serial connections."""
    async with get_debug_serial_lock():
        status = {}
        for port, ser in _debug_serial_connections.items():
            try:
                status[port] = {
                    "open": ser.is_open,
                    "baudrate": ser.baudrate
                }
            except:
                status[port] = {"open": False}
        return {"connections": status}


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
        
        # Check file existence asynchronously
        exists = await asyncio.to_thread(os.path.exists, file_path)
        if not exists:
            raise HTTPException(status_code=404, detail=f"File {file_name} not found")

        # Parse the theta-rho file in a separate process for CPU-intensive work
        # This prevents blocking the motion control thread
        loop = asyncio.get_running_loop()
        coordinates = await loop.run_in_executor(pool_module.get_pool(), parse_theta_rho_file, file_path)
        
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
async def run_theta_rho(request: ThetaRhoRequest, background_tasks: BackgroundTasks):
    if not request.file_name:
        logger.warning('Run theta-rho request received without file name')
        raise HTTPException(status_code=400, detail="No file name provided")
    
    file_path = None
    if 'clear' in request.file_name:
        logger.info(f'Clear pattern file: {request.file_name.split(".")[0]}')
        file_path = pattern_manager.get_clear_pattern_file(request.file_name.split('.')[0])
        logger.info(f'Clear pattern file: {file_path}')
    if not file_path:
        # Normalize file path for cross-platform compatibility
        normalized_file_name = normalize_file_path(request.file_name)
        file_path = os.path.join(pattern_manager.THETA_RHO_DIR, normalized_file_name)
    if not os.path.exists(file_path):
        logger.error(f'Theta-rho file not found: {file_path}')
        raise HTTPException(status_code=404, detail="File not found")

    try:
        if not (state.conn.is_connected() if state.conn else False):
            logger.warning("Attempted to run a pattern without a connection")
            raise HTTPException(status_code=400, detail="Connection not established")

        check_homing_in_progress()

        if pattern_manager.get_pattern_lock().locked():
            logger.info("Another pattern is running, stopping it first...")
            await pattern_manager.stop_actions()
            
        files_to_run = [file_path]
        logger.info(f'Running theta-rho file: {request.file_name} with pre_execution={request.pre_execution}')
        
        # Only include clear_pattern if it's not "none"
        kwargs = {}
        if request.pre_execution != "none":
            kwargs['clear_pattern'] = request.pre_execution
        
        # Pass arguments properly
        background_tasks.add_task(
            pattern_manager.run_theta_rho_files,
            files_to_run,  # First positional argument
            **kwargs  # Spread keyword arguments
        )
        return {"success": True}
    except HTTPException as http_exc:
        logger.error(f'Failed to run theta-rho file {request.file_name}: {http_exc.detail}')
        raise http_exc
    except Exception as e:
        logger.error(f'Failed to run theta-rho file {request.file_name}: {str(e)}')
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/stop_execution")
async def stop_execution():
    if not (state.conn.is_connected() if state.conn else False):
        logger.warning("Attempted to stop without a connection")
        raise HTTPException(status_code=400, detail="Connection not established")
    await pattern_manager.stop_actions()
    return {"success": True}

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

@app.post("/run_theta_rho_file/{file_name}")
async def run_specific_theta_rho_file(file_name: str):
    file_path = os.path.join(pattern_manager.THETA_RHO_DIR, file_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    if not (state.conn.is_connected() if state.conn else False):
        logger.warning("Attempted to run a pattern without a connection")
        raise HTTPException(status_code=400, detail="Connection not established")

    check_homing_in_progress()

    pattern_manager.run_theta_rho_file(file_path)
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

        await pattern_manager.reset_theta()
        await pattern_manager.move_polar(0, 1)
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
    connected = state.conn.is_connected() if state.conn else False
    port = state.port
    logger.debug(f"Serial status check - connected: {connected}, port: {port}")
    return {
        "connected": connected,
        "port": port,
        "preferred_port": state.preferred_port
    }

@app.get("/api/preferred-port", deprecated=True, tags=["settings-deprecated"])
async def get_preferred_port():
    """Get the currently configured preferred port for auto-connect."""
    return {
        "preferred_port": state.preferred_port
    }

@app.post("/api/preferred-port", deprecated=True, tags=["settings-deprecated"])
async def set_preferred_port(request: Request):
    """Set the preferred port for auto-connect."""
    data = await request.json()
    preferred_port = data.get("preferred_port")

    # Allow setting to None to clear the preference
    if preferred_port == "" or preferred_port == "none":
        preferred_port = None

    state.preferred_port = preferred_port
    state.save()

    logger.info(f"Preferred port set to: {preferred_port}")
    return {
        "success": True,
        "preferred_port": state.preferred_port
    }

@app.post("/pause_execution")
async def pause_execution():
    if pattern_manager.pause_execution():
        return {"success": True, "message": "Execution paused"}
    raise HTTPException(status_code=500, detail="Failed to pause execution")

@app.post("/resume_execution")
async def resume_execution():
    if pattern_manager.resume_execution():
        return {"success": True, "message": "Execution resumed"}
    raise HTTPException(status_code=500, detail="Failed to resume execution")

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
    """Run a playlist with specified parameters."""
    try:
        if not (state.conn.is_connected() if state.conn else False):
            logger.warning("Attempted to run a playlist without a connection")
            raise HTTPException(status_code=400, detail="Connection not established")

        check_homing_in_progress()

        if not os.path.exists(playlist_manager.PLAYLISTS_FILE):
            raise HTTPException(status_code=404, detail=f"Playlist '{request.playlist_name}' not found")

        # Start the playlist execution
        success, message = await playlist_manager.run_playlist(
            request.playlist_name,
            pause_time=request.pause_time,
            clear_pattern=request.clear_pattern,
            run_mode=request.run_mode,
            shuffle=request.shuffle
        )
        if not success:
            raise HTTPException(status_code=409, detail=message)

        return {"message": f"Started playlist: {request.playlist_name}"}
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
        return {"success": True, "speed": request.speed}
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
    """DEPRECATED: Use PATCH /api/settings instead. Configure LED provider (WLED, DW LEDs, or none)"""
    if request.provider not in ["wled", "dw_leds", "none"]:
        raise HTTPException(status_code=400, detail="Invalid provider. Must be 'wled', 'dw_leds', or 'none'")

    state.led_provider = request.provider

    if request.provider == "wled":
        if not request.ip_address:
            raise HTTPException(status_code=400, detail="IP address required for WLED")
        state.wled_ip = request.ip_address
        state.led_controller = LEDInterface("wled", request.ip_address)
        logger.info(f"LED provider set to WLED at {request.ip_address}")

    elif request.provider == "dw_leds":
        # Check if hardware settings changed (requires restart)
        old_gpio_pin = state.dw_led_gpio_pin
        old_pixel_order = state.dw_led_pixel_order
        hardware_changed = (
            old_gpio_pin != (request.gpio_pin or 18) or
            old_pixel_order != (request.pixel_order or "RGB")
        )

        # Stop existing DW LED controller if hardware settings changed
        if hardware_changed and state.led_controller and state.led_provider == "dw_leds":
            logger.info("Hardware settings changed, stopping existing LED controller...")
            controller = state.led_controller.get_controller()
            if controller and hasattr(controller, 'stop'):
                try:
                    controller.stop()
                    logger.info("LED controller stopped successfully")
                except Exception as e:
                    logger.error(f"Error stopping LED controller: {e}")
            # Clear the reference and give hardware time to release
            state.led_controller = None
            await asyncio.sleep(0.5)

        state.dw_led_num_leds = request.num_leds or 60
        state.dw_led_gpio_pin = request.gpio_pin or 18
        state.dw_led_pixel_order = request.pixel_order or "RGB"
        state.dw_led_brightness = request.brightness or 35
        state.wled_ip = None

        # Create new LED controller with updated settings
        state.led_controller = LEDInterface(
            "dw_leds",
            num_leds=state.dw_led_num_leds,
            gpio_pin=state.dw_led_gpio_pin,
            pixel_order=state.dw_led_pixel_order,
            brightness=state.dw_led_brightness / 100.0,
            speed=state.dw_led_speed,
            intensity=state.dw_led_intensity
        )

        restart_msg = " (restarted)" if hardware_changed else ""
        logger.info(f"DW LEDs configured{restart_msg}: {state.dw_led_num_leds} LEDs on GPIO{state.dw_led_gpio_pin}, pixel order: {state.dw_led_pixel_order}")

        # Check if initialization succeeded by checking status
        status = state.led_controller.check_status()
        if not status.get("connected", False) and status.get("error"):
            error_msg = status["error"]
            logger.warning(f"DW LED initialization failed: {error_msg}, but configuration saved for testing")
            state.led_controller = None
            # Keep the provider setting for testing purposes
            # state.led_provider remains "dw_leds" so settings can be saved/tested

            # Save state even with error
            state.save()

            # Return success with warning instead of error
            return {
                "success": True,
                "warning": error_msg,
                "hardware_available": False,
                "provider": state.led_provider,
                "dw_led_num_leds": state.dw_led_num_leds,
                "dw_led_gpio_pin": state.dw_led_gpio_pin,
                "dw_led_pixel_order": state.dw_led_pixel_order,
                "dw_led_brightness": state.dw_led_brightness
            }

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
        "dw_led_num_leds": state.dw_led_num_leds,
        "dw_led_gpio_pin": state.dw_led_gpio_pin,
        "dw_led_brightness": state.dw_led_brightness
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
        "dw_led_num_leds": state.dw_led_num_leds,
        "dw_led_gpio_pin": state.dw_led_gpio_pin,
        "dw_led_pixel_order": state.dw_led_pixel_order,
        "dw_led_brightness": state.dw_led_brightness,
        "dw_led_idle_effect": state.dw_led_idle_effect,
        "dw_led_playing_effect": state.dw_led_playing_effect
    }

@app.post("/skip_pattern")
async def skip_pattern():
    if not state.current_playlist:
        raise HTTPException(status_code=400, detail="No playlist is currently running")
    state.skip_requested = True
    return {"success": True}

@app.post("/reorder_playlist")
async def reorder_playlist(request: dict):
    """Reorder a pattern in the current playlist queue.

    Since the playlist now contains only main patterns (clear patterns are executed
    dynamically at runtime), this simply moves the pattern from one position to another.
    """
    if not state.current_playlist:
        raise HTTPException(status_code=400, detail="No playlist is currently running")

    from_index = request.get("from_index")
    to_index = request.get("to_index")

    if from_index is None or to_index is None:
        raise HTTPException(status_code=400, detail="from_index and to_index are required")

    playlist = list(state.current_playlist)  # Make a copy to work with
    current_index = state.current_playlist_index

    # Validate indices
    if from_index < 0 or from_index >= len(playlist):
        raise HTTPException(status_code=400, detail="from_index out of range")
    if to_index < 0 or to_index >= len(playlist):
        raise HTTPException(status_code=400, detail="to_index out of range")

    # Can't move patterns that have already played (before current_index)
    # But CAN move the current pattern or swap with it (allows live reordering)
    if from_index < current_index:
        raise HTTPException(status_code=400, detail="Cannot move completed pattern")
    if to_index < current_index:
        raise HTTPException(status_code=400, detail="Cannot move to completed position")

    # Perform the reorder
    item = playlist.pop(from_index)
    # Adjust to_index if moving forward (since we removed an item before it)
    adjusted_to_index = to_index if to_index < from_index else to_index - 1
    playlist.insert(adjusted_to_index, item)

    # Update state (this triggers the property setter)
    state.current_playlist = playlist

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
MAX_LOGO_SIZE = 5 * 1024 * 1024  # 5MB

def generate_favicon_from_logo(logo_path: str, favicon_path: str) -> bool:
    """Generate a circular-cropped favicon from the uploaded logo using PIL.

    Creates a multi-size ICO file (16x16, 32x32, 48x48) with circular crop.
    Returns True on success, False on failure.
    """
    try:
        from PIL import Image, ImageDraw

        def create_circular_image(img, size):
            """Create a circular-cropped image at the specified size."""
            # Resize to target size
            resized = img.resize((size, size), Image.Resampling.LANCZOS)

            # Create circular mask
            mask = Image.new('L', (size, size), 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0, size - 1, size - 1), fill=255)

            # Apply circular mask - create transparent background
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

            # Create circular images at each favicon size
            sizes = [48, 32, 16]
            circular_images = [create_circular_image(img, size) for size in sizes]

            # Save as ICO - first image is the main one, rest are appended
            circular_images[0].save(
                favicon_path,
                format='ICO',
                append_images=circular_images[1:],
                sizes=[(s, s) for s in sizes]
            )

        return True
    except Exception as e:
        logger.error(f"Failed to generate favicon: {str(e)}")
        return False

@app.post("/api/upload-logo", tags=["settings"])
async def upload_logo(file: UploadFile = File(...)):
    """Upload a custom logo image.

    Supported formats: PNG, JPG, JPEG, GIF, WebP, SVG
    Maximum size: 5MB

    The uploaded file will be stored and used as the application logo.
    A favicon will be automatically generated from the logo.
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

        # Generate a unique filename to prevent caching issues
        import uuid
        filename = f"logo-{uuid.uuid4().hex[:8]}{file_ext}"
        file_path = os.path.join(CUSTOM_BRANDING_DIR, filename)

        # Save the logo file
        with open(file_path, "wb") as f:
            f.write(content)

        # Generate favicon from logo (for non-SVG files)
        favicon_generated = False
        if file_ext != ".svg":
            favicon_path = os.path.join(CUSTOM_BRANDING_DIR, "favicon.ico")
            favicon_generated = generate_favicon_from_logo(file_path, favicon_path)

        # Update state
        state.custom_logo = filename
        state.save()

        logger.info(f"Custom logo uploaded: {filename}, favicon generated: {favicon_generated}")
        return {
            "success": True,
            "filename": filename,
            "url": f"/static/custom/{filename}",
            "favicon_generated": favicon_generated
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading logo: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/custom-logo", tags=["settings"])
async def delete_custom_logo():
    """Remove custom logo and favicon, reverting to defaults."""
    try:
        if state.custom_logo:
            # Remove logo
            logo_path = os.path.join(CUSTOM_BRANDING_DIR, state.custom_logo)
            if os.path.exists(logo_path):
                os.remove(logo_path)

            # Remove generated favicon
            favicon_path = os.path.join(CUSTOM_BRANDING_DIR, "favicon.ico")
            if os.path.exists(favicon_path):
                os.remove(favicon_path)

            state.custom_logo = None
            state.save()
            logger.info("Custom logo and favicon removed")
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
                    # Use process pool for CPU-intensive parsing
                    loop = asyncio.get_running_loop()
                    coordinates = await loop.run_in_executor(pool_module.get_pool(), parse_theta_rho_file, pattern_file_path)
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

    logger.info(f"Total batch processing time: {time.time() - start:.2f}s for {len(file_names)} files")
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
    if not state.led_controller or state.led_provider != "dw_leds":
        return {"connected": False, "message": "DW LEDs not configured"}

    try:
        return state.led_controller.check_status()
    except Exception as e:
        logger.error(f"Failed to check DW LED status: {str(e)}")
        return {"connected": False, "message": str(e)}

@app.post("/api/dw_leds/power")
async def dw_leds_power(request: dict):
    """Control DW LED power (0=off, 1=on, 2=toggle)"""
    if not state.led_controller or state.led_provider != "dw_leds":
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
            logger.debug(f"LED activity time reset due to manual power on")

        return result
    except Exception as e:
        logger.error(f"Failed to set DW LED power: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/dw_leds/brightness")
async def dw_leds_brightness(request: dict):
    """Set DW LED brightness (0-100)"""
    if not state.led_controller or state.led_provider != "dw_leds":
        raise HTTPException(status_code=400, detail="DW LEDs not configured")

    value = request.get("value", 50)
    if not 0 <= value <= 100:
        raise HTTPException(status_code=400, detail="Brightness must be between 0 and 100")

    try:
        controller = state.led_controller.get_controller()
        result = controller.set_brightness(value)
        # Update state if successful
        if result.get("connected"):
            state.dw_led_brightness = value
            state.save()
        return result
    except Exception as e:
        logger.error(f"Failed to set DW LED brightness: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/dw_leds/color")
async def dw_leds_color(request: dict):
    """Set solid color (manual UI control - always powers on LEDs)"""
    if not state.led_controller or state.led_provider != "dw_leds":
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
    if not state.led_controller or state.led_provider != "dw_leds":
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
    if not state.led_controller or state.led_provider != "dw_leds":
        raise HTTPException(status_code=400, detail="DW LEDs not configured")

    try:
        controller = state.led_controller.get_controller()
        effects = controller.get_effects()
        # Convert tuples to lists for JSON serialization
        effects_list = [[eid, name] for eid, name in effects]
        return {
            "success": True,
            "effects": effects_list
        }
    except Exception as e:
        logger.error(f"Failed to get DW LED effects: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dw_leds/palettes")
async def dw_leds_palettes():
    """Get list of available palettes"""
    if not state.led_controller or state.led_provider != "dw_leds":
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
    if not state.led_controller or state.led_provider != "dw_leds":
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
    if not state.led_controller or state.led_provider != "dw_leds":
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
    if not state.led_controller or state.led_provider != "dw_leds":
        raise HTTPException(status_code=400, detail="DW LEDs not configured")

    value = request.get("speed", 128)
    if not 0 <= value <= 255:
        raise HTTPException(status_code=400, detail="Speed must be between 0 and 255")

    try:
        controller = state.led_controller.get_controller()
        result = controller.set_speed(value)
        # Save speed to state
        state.dw_led_speed = value
        state.save()
        return result
    except Exception as e:
        logger.error(f"Failed to set DW LED speed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/dw_leds/intensity")
async def dw_leds_intensity(request: dict):
    """Set effect intensity (0-255)"""
    if not state.led_controller or state.led_provider != "dw_leds":
        raise HTTPException(status_code=400, detail="DW LEDs not configured")

    value = request.get("intensity", 128)
    if not 0 <= value <= 255:
        raise HTTPException(status_code=400, detail="Intensity must be between 0 and 255")

    try:
        controller = state.led_controller.get_controller()
        result = controller.set_intensity(value)
        # Save intensity to state
        state.dw_led_intensity = value
        state.save()
        return result
    except Exception as e:
        logger.error(f"Failed to set DW LED intensity: {str(e)}")
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

    if effect_type == "idle":
        state.dw_led_idle_effect = settings
    elif effect_type == "playing":
        state.dw_led_playing_effect = settings
    else:
        raise HTTPException(status_code=400, detail="Invalid effect type. Must be 'idle' or 'playing'")

    state.save()
    logger.info(f"DW LED {effect_type} effect settings saved: {settings}")

    return {"success": True, "type": effect_type, "settings": settings}

@app.post("/api/dw_leds/clear_effect_settings")
async def dw_leds_clear_effect_settings(request: dict):
    """Clear idle or playing effect settings"""
    effect_type = request.get("type")  # 'idle' or 'playing'

    if effect_type == "idle":
        state.dw_led_idle_effect = None
    elif effect_type == "playing":
        state.dw_led_playing_effect = None
    else:
        raise HTTPException(status_code=400, detail="Invalid effect type. Must be 'idle' or 'playing'")

    state.save()
    logger.info(f"DW LED {effect_type} effect settings cleared")

    return {"success": True, "type": effect_type}

@app.get("/api/dw_leds/get_effect_settings")
async def dw_leds_get_effect_settings():
    """Get saved idle and playing effect settings"""
    return {
        "idle_effect": state.dw_led_idle_effect,
        "playing_effect": state.dw_led_playing_effect
    }

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

        # Shutdown process pool - wait=True allows workers to release semaphores properly
        pool_module.shutdown_pool(wait=True)

        # Stop pattern manager motion controller
        pattern_manager.motion_controller.stop()

        # Set stop flags to halt any running patterns
        state.stop_requested = True
        state.pause_requested = False

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
    """Trigger software update by pulling latest Docker images and recreating containers."""
    try:
        logger.info("Update triggered via API")
        success, error_message, error_log = update_manager.update_software()

        if success:
            return JSONResponse(content={
                "success": True,
                "message": "Update started. Containers are being recreated with the latest images. The page will reload shortly."
            })
        else:
            return JSONResponse(content={
                "success": False,
                "message": error_message or "Update failed",
                "errors": error_log
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
                # Use systemctl to shutdown the host (via mounted systemd socket)
                subprocess.run(["systemctl", "poweroff"], check=True)
                logger.info("Host shutdown command executed successfully via systemctl")
            except FileNotFoundError:
                logger.error("systemctl command not found - ensure systemd volumes are mounted")
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
    """Restart the Docker containers using docker compose"""
    try:
        logger.warning("Restart initiated via API")

        # Schedule restart command after a short delay to allow response to be sent
        def delayed_restart():
            time.sleep(2)  # Give time for response to be sent
            try:
                # Use docker restart directly with container name
                # This is simpler and doesn't require the compose file path
                subprocess.run(["docker", "restart", "dune-weaver-backend"], check=True)
                logger.info("Docker restart command executed successfully")
            except FileNotFoundError:
                logger.error("docker command not found")
            except Exception as e:
                logger.error(f"Error executing docker restart: {e}")

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

def entrypoint():
    import uvicorn
    logger.info("Starting FastAPI server on port 8080...")
    uvicorn.run(app, host="0.0.0.0", port=8080, workers=1)  # Set workers to 1 to avoid multiple signal handlers

if __name__ == "__main__":
    entrypoint()