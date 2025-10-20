from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
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
import math
from modules.core.cache_manager import generate_all_image_previews, get_cache_path, generate_image_preview, get_pattern_metadata
from modules.core.version_manager import version_manager
import json
import base64
import time
import argparse
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
import subprocess
import platform

# Get log level from environment variable, default to INFO
log_level_str = os.getenv('LOG_LEVEL', 'INFO').upper()
log_level = getattr(logging, log_level_str, logging.INFO)

# Create a process pool for CPU-intensive tasks
# Limit to reasonable number of workers for embedded systems
cpu_count = multiprocessing.cpu_count()
# Maximum 3 workers (leaving 1 for motion), minimum 1
process_pool_size = min(3, max(1, cpu_count - 1))
process_pool = None  # Will be initialized in lifespan

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
    ]
)

logger = logging.getLogger(__name__)

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

    # Initialize process pool for CPU-intensive tasks
    global process_pool
    process_pool = ProcessPoolExecutor(max_workers=process_pool_size)
    logger.info(f"Initialized process pool with {process_pool_size} workers (detected {cpu_count} cores total)")
    
    try:
        connection_manager.connect_device()
    except Exception as e:
        logger.warning(f"Failed to auto-connect to serial port: {str(e)}")

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
                brightness=state.dw_led_brightness / 100.0,
                speed=state.dw_led_speed,
                intensity=state.dw_led_intensity
            )
            logger.info(f"LED controller initialized: DW LEDs ({state.dw_led_num_leds} LEDs on GPIO{state.dw_led_gpio_pin})")
        else:
            state.led_controller = None
            logger.info("LED controller not configured")

        # Save if provider was auto-detected
        if state.led_provider and state.wled_ip:
            state.save()
    except Exception as e:
        logger.warning(f"Failed to initialize LED controller: {str(e)}")
        state.led_controller = None

    # Check if auto_play mode is enabled and auto-play playlist (right after connection attempt)
    if state.auto_play_enabled and state.auto_play_playlist:
        logger.info(f"auto_play mode enabled, checking for connection before auto-playing playlist: {state.auto_play_playlist}")
        try:
            # Check if we have a valid connection before starting playlist
            if state.conn and hasattr(state.conn, 'is_connected') and state.conn.is_connected():
                logger.info(f"Connection available, starting auto-play playlist: {state.auto_play_playlist} with options: run_mode={state.auto_play_run_mode}, pause_time={state.auto_play_pause_time}, clear_pattern={state.auto_play_clear_pattern}, shuffle={state.auto_play_shuffle}")
                asyncio.create_task(playlist_manager.run_playlist(
                    state.auto_play_playlist,
                    pause_time=state.auto_play_pause_time,
                    clear_pattern=state.auto_play_clear_pattern,
                    run_mode=state.auto_play_run_mode,
                    shuffle=state.auto_play_shuffle
                ))
            else:
                logger.warning("No hardware connection available, skipping auto_play mode auto-play")
        except Exception as e:
            logger.error(f"Failed to auto-play auto_play playlist: {str(e)}")
        
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

    yield  # This separates startup from shutdown code

    # Shutdown
    logger.info("Shutting down Dune Weaver application...")

    # Shutdown process pool
    if process_pool:
        process_pool.shutdown(wait=True)
        logger.info("Process pool shutdown complete")

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

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
    brightness: Optional[int] = None

class DeletePlaylistRequest(BaseModel):
    playlist_name: str

class ThetaRhoRequest(BaseModel):
    file_name: str
    pre_execution: Optional[str] = "none"

class GetCoordinatesRequest(BaseModel):
    file_name: str

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

# FastAPI routes
@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "app_name": state.app_name})

@app.get("/settings")
async def settings(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request, "app_name": state.app_name})

@app.get("/api/auto_play-mode")
async def get_auto_play_mode():
    """Get current auto_play mode settings."""
    return {
        "enabled": state.auto_play_enabled,
        "playlist": state.auto_play_playlist,
        "run_mode": state.auto_play_run_mode,
        "pause_time": state.auto_play_pause_time,
        "clear_pattern": state.auto_play_clear_pattern,
        "shuffle": state.auto_play_shuffle
    }

@app.post("/api/auto_play-mode")
async def set_auto_play_mode(request: auto_playModeRequest):
    """Update auto_play mode settings."""
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

@app.get("/api/scheduled-pause")
async def get_scheduled_pause():
    """Get current Still Sands settings."""
    return {
        "enabled": state.scheduled_pause_enabled,
        "control_wled": state.scheduled_pause_control_wled,
        "time_slots": state.scheduled_pause_time_slots
    }

@app.post("/api/scheduled-pause")
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
        state.scheduled_pause_time_slots = [slot.model_dump() for slot in request.time_slots]
        state.save()

        wled_msg = " (with WLED control)" if request.control_wled else ""
        logger.info(f"Still Sands {'enabled' if request.enabled else 'disabled'} with {len(request.time_slots)} time slots{wled_msg}")
        return {"success": True, "message": "Still Sands settings updated"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating Still Sands settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update Still Sands settings: {str(e)}")

@app.get("/list_serial_ports")
async def list_ports():
    logger.debug("Listing available serial ports")
    return await asyncio.to_thread(connection_manager.list_serial_ports)

@app.post("/connect")
async def connect(request: ConnectRequest):
    if not request.port:
        state.conn = connection_manager.WebSocketConnection('ws://fluidnc.local:81')
        connection_manager.device_init()
        logger.info('Successfully connected to websocket ws://fluidnc.local:81')
        return {"success": True}

    try:
        state.conn = connection_manager.SerialConnection(request.port)
        connection_manager.device_init()
        logger.info(f'Successfully connected to serial port {request.port}')
        return {"success": True}
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
        loop = asyncio.get_event_loop()
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
        loop = asyncio.get_event_loop()
        coordinates = await loop.run_in_executor(process_pool, parse_theta_rho_file, file_path)
        
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
        
        if pattern_manager.pattern_lock.locked():
            logger.warning("Attempted to run a pattern while another is already running")
            raise HTTPException(status_code=409, detail="Another pattern is already running")
            
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
        
        # Run homing with 15 second timeout
        success = await asyncio.to_thread(connection_manager.home)
        if not success:
            logger.error("Homing failed or timed out")
            raise HTTPException(status_code=500, detail="Homing failed or timed out after 15 seconds")
        
        return {"success": True}
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

        logger.info("Moving device to center position")
        await pattern_manager.reset_theta()
        await pattern_manager.move_polar(0, 0)
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to move to center: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/move_to_perimeter")
async def move_to_perimeter():
    try:
        if not (state.conn.is_connected() if state.conn else False):
            logger.warning("Attempted to move to perimeter without a connection")
            raise HTTPException(status_code=400, detail="Connection not established")
        await pattern_manager.reset_theta()
        await pattern_manager.move_polar(0, 1)
        return {"success": True}
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
        "port": port
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
        raise HTTPException(status_code=404, detail=f"Playlist '{name}' not found")

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
    state.save()
    logger.info(f"WLED IP updated: {request.wled_ip}")
    return {"success": True, "wled_ip": state.wled_ip}

@app.get("/get_wled_ip")
async def get_wled_ip():
    """Legacy endpoint for backward compatibility"""
    if not state.wled_ip:
        raise HTTPException(status_code=404, detail="No WLED IP set")
    return {"success": True, "wled_ip": state.wled_ip}

@app.post("/set_led_config")
async def set_led_config(request: LEDConfigRequest):
    """Configure LED provider (WLED, DW LEDs, or none)"""
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
        state.dw_led_num_leds = request.num_leds or 60
        state.dw_led_gpio_pin = request.gpio_pin or 12
        state.dw_led_brightness = request.brightness or 35
        state.wled_ip = None
        state.led_controller = LEDInterface(
            "dw_leds",
            num_leds=state.dw_led_num_leds,
            gpio_pin=state.dw_led_gpio_pin,
            brightness=state.dw_led_brightness / 100.0,
            speed=state.dw_led_speed,
            intensity=state.dw_led_intensity
        )
        logger.info(f"DW LEDs configured: {state.dw_led_num_leds} LEDs on GPIO{state.dw_led_gpio_pin}")

        # Check if initialization succeeded by checking status
        status = state.led_controller.check_status()
        if not status.get("connected", False) and status.get("error"):
            error_msg = status["error"]
            state.led_controller = None
            state.led_provider = "none"
            raise HTTPException(status_code=400, detail=error_msg)

    else:  # none
        state.wled_ip = None
        state.led_controller = None
        logger.info("LED provider disabled")

    # Show idle effect if controller is configured
    if state.led_controller:
        state.led_controller.effect_idle()

    state.save()

    return {
        "success": True,
        "provider": state.led_provider,
        "wled_ip": state.wled_ip,
        "dw_led_num_leds": state.dw_led_num_leds,
        "dw_led_gpio_pin": state.dw_led_gpio_pin,
        "dw_led_brightness": state.dw_led_brightness
    }

@app.get("/get_led_config")
async def get_led_config():
    """Get current LED provider configuration"""
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

@app.get("/api/custom_clear_patterns")
async def get_custom_clear_patterns():
    """Get the currently configured custom clear patterns."""
    return {
        "success": True,
        "custom_clear_from_in": state.custom_clear_from_in,
        "custom_clear_from_out": state.custom_clear_from_out
    }

@app.post("/api/custom_clear_patterns")
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

@app.get("/api/clear_pattern_speed")
async def get_clear_pattern_speed():
    """Get the current clearing pattern speed setting."""
    return {
        "success": True,
        "clear_pattern_speed": state.clear_pattern_speed,
        "effective_speed": state.clear_pattern_speed if state.clear_pattern_speed is not None else state.speed
    }

@app.post("/api/clear_pattern_speed")
async def set_clear_pattern_speed(request: dict):
    """Set the clearing pattern speed."""
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

@app.get("/api/app-name")
async def get_app_name():
    """Get current application name."""
    return {"app_name": state.app_name}

@app.post("/api/app-name")
async def set_app_name(request: dict):
    """Update application name."""
    app_name = request.get("app_name", "").strip()
    if not app_name:
        app_name = "Dune Weaver"  # Reset to default if empty
    
    state.app_name = app_name
    state.save()
    
    logger.info(f"Application name updated to: {app_name}")
    return {"success": True, "app_name": app_name}

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
                loop = asyncio.get_event_loop()
                coordinates = await loop.run_in_executor(process_pool, parse_theta_rho_file, pattern_file_path)
                first_coord = coordinates[0] if coordinates else None
                last_coord = coordinates[-1] if coordinates else None
                first_coord_obj = {"x": first_coord[0], "y": first_coord[1]} if first_coord else None
                last_coord_obj = {"x": last_coord[0], "y": last_coord[1]} if last_coord else None

            # Read image file asynchronously
            image_data = await asyncio.to_thread(lambda: open(cache_path, 'rb').read())
            image_b64 = base64.b64encode(image_data).decode('utf-8')
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
async def playlists(request: Request):
    logger.debug("Rendering playlists page")
    return templates.TemplateResponse("playlists.html", {"request": request, "app_name": state.app_name})

@app.get("/image2sand")
async def image2sand(request: Request):
    return templates.TemplateResponse("image2sand.html", {"request": request, "app_name": state.app_name})

@app.get("/wled")
async def wled(request: Request):
    return templates.TemplateResponse("wled.html", {"request": request, "app_name": state.app_name})

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
        return state.led_controller.set_power(state_value)
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
    """Set solid color"""
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
        return controller.set_color(r, g, b)
    except Exception as e:
        logger.error(f"Failed to set DW LED color: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/dw_leds/colors")
async def dw_leds_colors(request: dict):
    """Set effect colors (color1, color2, color3)"""
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
    """Set effect by ID"""
    if not state.led_controller or state.led_provider != "dw_leds":
        raise HTTPException(status_code=400, detail="DW LEDs not configured")

    effect_id = request.get("effect_id", 0)
    speed = request.get("speed")
    intensity = request.get("intensity")

    try:
        controller = state.led_controller.get_controller()
        return controller.set_effect(effect_id, speed=speed, intensity=intensity)
    except Exception as e:
        logger.error(f"Failed to set DW LED effect: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/dw_leds/palette")
async def dw_leds_palette(request: dict):
    """Set palette by ID"""
    if not state.led_controller or state.led_provider != "dw_leds":
        raise HTTPException(status_code=400, detail="DW LEDs not configured")

    palette_id = request.get("palette_id", 0)

    try:
        controller = state.led_controller.get_controller()
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

@app.post("/api/dw_leds/set_effects")
async def dw_leds_set_effects(request: dict):
    """Configure idle and playing effects"""
    idle_effect = request.get("idle_effect")
    playing_effect = request.get("playing_effect")

    state.dw_led_idle_effect = idle_effect if idle_effect else "off"
    state.dw_led_playing_effect = playing_effect if playing_effect else "off"
    state.save()

    logger.info(f"DW LED effects configured - Idle: {state.dw_led_idle_effect}, Playing: {state.dw_led_playing_effect}")

    return {
        "success": True,
        "idle_effect": state.dw_led_idle_effect,
        "playing_effect": state.dw_led_playing_effect
    }

@app.get("/table_control")
async def table_control(request: Request):
    return templates.TemplateResponse("table_control.html", {"request": request, "app_name": state.app_name})

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
    """Handle shutdown signals gracefully but forcefully."""
    logger.info("Received shutdown signal, cleaning up...")
    try:
        if state.led_controller:
            state.led_controller.set_power(0)
        # Run cleanup operations - need to handle async in sync context
        try:
            # Try to run in existing loop if available
            import asyncio
            loop = asyncio.get_running_loop()
            # If we're in an event loop, schedule the coroutine
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, pattern_manager.stop_actions())
                future.result(timeout=5.0)  # Wait up to 5 seconds
        except RuntimeError:
            # No running loop, create a new one
            import asyncio
            asyncio.run(pattern_manager.stop_actions())
        except Exception as cleanup_err:
            logger.error(f"Error in async cleanup: {cleanup_err}")

        state.save()
        logger.info("Cleanup completed")
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")
    finally:
        logger.info("Exiting application...")
        os._exit(0)  # Force exit regardless of other threads

@app.get("/api/version")
async def get_version_info():
    """Get current and latest version information"""
    try:
        version_info = await version_manager.get_version_info()
        return JSONResponse(content=version_info)
    except Exception as e:
        logger.error(f"Error getting version info: {e}")
        return JSONResponse(
            content={
                "current": version_manager.get_current_version(),
                "latest": version_manager.get_current_version(),
                "update_available": False,
                "error": "Unable to check for updates"
            },
            status_code=200
        )

@app.post("/api/update")
async def trigger_update():
    """Trigger software update (placeholder for future implementation)"""
    try:
        # For now, just return the GitHub release URL
        version_info = await version_manager.get_version_info()
        if version_info.get("latest_release"):
            return JSONResponse(content={
                "success": False,
                "message": "Automatic updates not implemented yet",
                "manual_update_url": version_info["latest_release"].get("html_url"),
                "instructions": "Please visit the GitHub release page to download and install the update manually"
            })
        else:
            return JSONResponse(content={
                "success": False,
                "message": "No updates available"
            })
    except Exception as e:
        logger.error(f"Error triggering update: {e}")
        return JSONResponse(
            content={"success": False, "message": "Failed to check for updates"},
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

def entrypoint():
    import uvicorn
    logger.info("Starting FastAPI server on port 8080...")
    uvicorn.run(app, host="0.0.0.0", port=8080, workers=1)  # Set workers to 1 to avoid multiple signal handlers

if __name__ == "__main__":
    entrypoint()