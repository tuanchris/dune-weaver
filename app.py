from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from pathlib import Path
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
from modules.core.cache_manager import generate_all_image_previews, get_cache_path, generate_image_preview

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
    ]
)

logger = logging.getLogger(__name__)

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
    
    # Generate image previews for all patterns
    try:
        logger.info("Starting image cache generation...")
        await generate_all_image_previews()
    except Exception as e:
        logger.warning(f"Failed to generate image cache: {str(e)}")

    yield  # This separates startup from shutdown code


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")
SVG_CACHE_DIR = os.path.dirname(get_cache_path("placeholder.thr"))
app.mount("/static", StaticFiles(directory="static"), name="static")
# serve that directory at /svg_cache/*
app.mount(
    "/svg_cache",
    StaticFiles(directory=SVG_CACHE_DIR),
    name="svg_cache",
)
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

# Store active WebSocket connections
active_status_connections = set()

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

# FastAPI routes
@app.get("/")
async def index():
    return templates.TemplateResponse("index.html", {"request": {}})

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
    files = pattern_manager.list_theta_rho_files()
    result = []
    for name in sorted(files):
        # if it's a custom pattern (i.e. contains a slash), swap '/' → '--'
        safe_name = name
        if "/" in name:
            safe_name = name.replace("/", "--")

        thumb_url = f"/preview/{safe_name}"
        result.append({
            "name": name,
            "thumb": thumb_url
        })

    logger.info(f"Returning {len(result)} patterns with SVG thumbs")
    return result


@app.post("/upload_theta_rho")
async def upload_theta_rho(file: UploadFile = File(...)):
    """Upload a theta-rho file."""
    try:
        # Save the file
        # Ensure custom_patterns directory exists
        custom_patterns_dir = os.path.join(pattern_manager.THETA_RHO_DIR, "custom_patterns")
        os.makedirs(custom_patterns_dir, exist_ok=True)
        
        file_path_in_patterns_dir = os.path.join("custom_patterns", file.filename)
        full_file_path = os.path.join(pattern_manager.THETA_RHO_DIR, file_path_in_patterns_dir)
        
        with open(full_file_path, "wb") as f:
            f.write(await file.read())
        
        # Generate image preview for the new file
        await generate_image_preview(file_path_in_patterns_dir)
        
        return {"success": True, "message": f"File {file.filename} uploaded successfully"}
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

class ThetaRhoRequest(BaseModel):
    file_name: str
    pre_execution: Optional[str] = "none"

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
        file_path = os.path.join(pattern_manager.THETA_RHO_DIR, request.file_name)
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
        connection_manager.home()
        return {"success": True}
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

    file_path = os.path.join(pattern_manager.THETA_RHO_DIR, request.file_name)
    if not os.path.exists(file_path):
        logger.error(f"Attempted to delete non-existent file: {file_path}")
        raise HTTPException(status_code=404, detail="File not found")

    try:
        os.remove(file_path)
        logger.info(f"Successfully deleted theta-rho file: {request.file_name}")
        return {"success": True}
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

    # Construct the full path to the pattern file to check existence
    pattern_file_path = os.path.join(pattern_manager.THETA_RHO_DIR, request.file_name)
    if not os.path.exists(pattern_file_path):
        logger.error(f"Attempted to preview non-existent pattern file: {pattern_file_path}")
        raise HTTPException(status_code=404, detail="Pattern file not found")

    try:
        cache_path = get_cache_path(request.file_name)
        
        if not os.path.exists(cache_path):
            logger.info(f"Cache miss for {request.file_name}. Generating preview...")
            # Attempt to generate the preview if it's missing
            success = await generate_image_preview(request.file_name)
            if not success or not os.path.exists(cache_path):
                logger.error(f"Failed to generate or find preview for {request.file_name} after attempting generation.")
                raise HTTPException(status_code=500, detail="Failed to generate preview image.")

        # Get the coordinates for display
        coordinates = parse_theta_rho_file(pattern_file_path)
        first_coord = coordinates[0] if coordinates else None
        last_coord = coordinates[-1] if coordinates else None

        # Return JSON with preview URL and coordinates
        # URL encode the file_name for the preview URL
        encoded_filename = request.file_name.replace('/', '--')
        return {
            "preview_url": f"/preview/{encoded_filename}",
            "first_coordinate": first_coord,
            "last_coordinate": last_coord
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate or serve preview for {request.file_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to serve preview image: {str(e)}")

@app.get("/preview/{encoded_filename}")
async def serve_preview(encoded_filename: str):
    """Serve a preview image for a pattern file."""
    # Decode the filename by replacing -- with /
    file_name = encoded_filename.replace('--', '/')
    cache_path = get_cache_path(file_name)
    
    if not os.path.exists(cache_path):
        logger.error(f"Preview image not found for {file_name}")
        raise HTTPException(status_code=404, detail="Preview image not found")
        
    return FileResponse(cache_path, media_type="image/png")

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

@app.get("/download/{filepath:path}")
async def download_file(filepath: str):
    # Resolve and make sure it’s still under THETA_RHO_DIR
    base = Path(pattern_manager.THETA_RHO_DIR).resolve()
    full = (base / filepath).resolve()
    if not str(full).startswith(str(base)):
        raise HTTPException(400, "Invalid file path")
    if not full.is_file():
        raise HTTPException(404, "File not found")

    return FileResponse(
        path=full,
        filename=full.name,
        media_type="application/octet-stream",
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
        if not os.path.exists(playlist_manager.PLAYLISTS_FILE):
            raise HTTPException(status_code=404, detail=f"Playlist '{request.playlist_name}' not found")

        # Start the playlist execution
        asyncio.create_task(playlist_manager.run_playlist(
            request.playlist_name,
            pause_time=request.pause_time,
            clear_pattern=request.clear_pattern,
            run_mode=request.run_mode,
            shuffle=request.shuffle
        ))

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

def entrypoint():
    import uvicorn
    logger.info("Starting FastAPI server on port 8080...")
    uvicorn.run(app, host="0.0.0.0", port=8080, workers=1)  # Set workers to 1 to avoid multiple signal handlers

if __name__ == "__main__":
    entrypoint()