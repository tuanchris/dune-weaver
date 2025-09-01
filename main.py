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
import math
from modules.core.cache_manager import generate_all_image_previews, get_cache_path, generate_image_preview, get_pattern_metadata
from modules.core.version_manager import version_manager
import json
import base64
import time
import argparse

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
    
    try:
        connection_manager.connect_device()
    except Exception as e:
        logger.warning(f"Failed to auto-connect to serial port: {str(e)}")
        
    try:
        mqtt_handler = mqtt.init_mqtt()
    except Exception as e:
        logger.warning(f"Failed to initialize MQTT: {str(e)}")
    
    # Start cache generation in background if needed
    try:
        from modules.core.cache_manager import is_cache_generation_needed, generate_cache_background
        if is_cache_generation_needed():
            logger.info("Cache generation needed, starting background task...")
            asyncio.create_task(generate_cache_background())
        else:
            logger.info("Cache is up to date, skipping generation")
    except Exception as e:
        logger.warning(f"Failed to start cache generation: {str(e)}")

    yield  # This separates startup from shutdown code


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Pydantic models for request/response validation
class ConnectRequest(BaseModel):
    port: Optional[str] = None

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
    await websocket.accept()
    active_cache_progress_connections.add(websocket)
    try:
        while True:
            from modules.core.cache_manager import get_cache_progress
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
            await asyncio.sleep(0.5)  # Update every 500ms
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
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/settings")
async def settings(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})

@app.get("/list_serial_ports")
async def list_ports():
    logger.debug("Listing available serial ports")
    return connection_manager.list_serial_ports()

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
    files = pattern_manager.list_theta_rho_files()
    return sorted(files)

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
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"File {file_name} not found")
        
        # Parse the theta-rho file
        coordinates = parse_theta_rho_file(file_path)
        
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
    pattern_manager.stop_actions()
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
    if not os.path.exists(file_path):
        logger.error(f"Attempted to delete non-existent file: {file_path}")
        raise HTTPException(status_code=404, detail="File not found")

    try:
        # Delete the pattern file
        os.remove(file_path)
        logger.info(f"Successfully deleted theta-rho file: {request.file_name}")
        
        # Clean up cached preview image and metadata
        from modules.core.cache_manager import delete_pattern_cache
        cache_cleanup_success = delete_pattern_cache(normalized_file_name)
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
        pattern_manager.reset_theta()
        pattern_manager.move_polar(0, 0)
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
        pattern_manager.reset_theta()
        pattern_manager.move_polar(0, 1)
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
    if not os.path.exists(pattern_file_path):
        logger.error(f"Attempted to preview non-existent pattern file: {pattern_file_path}")
        raise HTTPException(status_code=404, detail="Pattern file not found")

    try:
        cache_path = get_cache_path(normalized_file_name)
        
        if not os.path.exists(cache_path):
            logger.info(f"Cache miss for {request.file_name}. Generating preview...")
            # Attempt to generate the preview if it's missing
            success = await generate_image_preview(normalized_file_name)
            if not success or not os.path.exists(cache_path):
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
        pattern_manager.move_polar(request.theta, request.rho)
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
    state.wled_ip = request.wled_ip
    state.led_controller = LEDController(request.wled_ip)
    effect_idle(state.led_controller)
    state.save()
    logger.info(f"WLED IP updated: {request.wled_ip}")
    return {"success": True, "wled_ip": state.wled_ip}

@app.get("/get_wled_ip")
async def get_wled_ip():
    if not state.wled_ip:
        raise HTTPException(status_code=404, detail="No WLED IP set")
    return {"success": True, "wled_ip": state.wled_ip}

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

    results = {}
    for file_name in file_names:
        t1 = time.time()
        try:
            # Normalize file path for cross-platform compatibility
            normalized_file_name = normalize_file_path(file_name)
            pattern_file_path = os.path.join(pattern_manager.THETA_RHO_DIR, normalized_file_name)
            if not os.path.exists(pattern_file_path):
                logger.warning(f"Pattern file not found: {pattern_file_path}")
                results[file_name] = {"error": "Pattern file not found"}
                continue

            cache_path = get_cache_path(normalized_file_name)
            
            if not os.path.exists(cache_path):
                logger.info(f"Cache miss for {file_name}. Generating preview...")
                success = await generate_image_preview(normalized_file_name)
                if not success or not os.path.exists(cache_path):
                    logger.error(f"Failed to generate or find preview for {file_name}")
                    results[file_name] = {"error": "Failed to generate preview"}
                    continue

            metadata = get_pattern_metadata(normalized_file_name)
            if metadata:
                first_coord_obj = metadata.get('first_coordinate')
                last_coord_obj = metadata.get('last_coordinate')
            else:
                logger.debug(f"Metadata cache miss for {file_name}, parsing file")
                coordinates = await asyncio.to_thread(parse_theta_rho_file, pattern_file_path)
                first_coord = coordinates[0] if coordinates else None
                last_coord = coordinates[-1] if coordinates else None
                first_coord_obj = {"x": first_coord[0], "y": first_coord[1]} if first_coord else None
                last_coord_obj = {"x": last_coord[0], "y": last_coord[1]} if last_coord else None

            with open(cache_path, 'rb') as f:
                image_data = f.read()
            image_b64 = base64.b64encode(image_data).decode('utf-8')
            results[file_name] = {
                "image_data": f"data:image/webp;base64,{image_b64}",
                "first_coordinate": first_coord_obj,
                "last_coordinate": last_coord_obj
            }
        except Exception as e:
            logger.error(f"Error processing {file_name}: {str(e)}")
            results[file_name] = {"error": str(e)}
        finally:
            logger.debug(f"Processed {file_name} in {time.time() - t1:.2f}s")

    logger.info(f"Total batch processing time: {time.time() - start:.2f}s for {len(file_names)} files")
    return JSONResponse(content=results, headers=headers)

@app.get("/playlists")
async def playlists(request: Request):
    logger.debug("Rendering playlists page")
    return templates.TemplateResponse("playlists.html", {"request": request})

@app.get("/image2sand")
async def image2sand(request: Request):
    return templates.TemplateResponse("image2sand.html", {"request": request})

@app.get("/wled")
async def wled(request: Request):
    return templates.TemplateResponse("wled.html", {"request": request})

@app.get("/table_control")
async def table_control(request: Request):
    return templates.TemplateResponse("table_control.html", {"request": request})

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
        # Run cleanup operations synchronously to ensure completion
        pattern_manager.stop_actions()
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

def entrypoint():
    import uvicorn
    logger.info("Starting FastAPI server on port 8080...")
    uvicorn.run(app, host="0.0.0.0", port=8080, workers=1)  # Set workers to 1 to avoid multiple signal handlers

if __name__ == "__main__":
    entrypoint()