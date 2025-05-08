# pattern_manager.py
import os
import threading
import time
import random
import logging
from datetime import datetime
from tqdm import tqdm
from modules.connection import connection_manager
from modules.core.state import state
from math import pi
import asyncio
import json
from modules.led.led_controller import effect_playing, effect_idle

# Configure logging
logger = logging.getLogger(__name__)

# Global state
THETA_RHO_DIR = './patterns'
os.makedirs(THETA_RHO_DIR, exist_ok=True)

# Create an asyncio Event for pause/resume
pause_event = asyncio.Event()
pause_event.set()  # Initially not paused

# Create an asyncio Lock for pattern execution
pattern_lock = asyncio.Lock()

# Progress update task
progress_update_task = None

async def cleanup_pattern_manager():
    """Clean up pattern manager resources"""
    global progress_update_task, pattern_lock, pause_event
    
    try:
        # Cancel progress update task if running
        if progress_update_task and not progress_update_task.done():
            try:
                progress_update_task.cancel()
                # Wait for task to actually cancel
                try:
                    await progress_update_task
                except asyncio.CancelledError:
                    pass
            except Exception as e:
                logger.error(f"Error cancelling progress update task: {e}")
        
        # Clean up pattern lock
        if pattern_lock:
            try:
                if pattern_lock.locked():
                    pattern_lock.release()
                pattern_lock = None
            except Exception as e:
                logger.error(f"Error cleaning up pattern lock: {e}")
        
        # Clean up pause event
        if pause_event:
            try:
                pause_event.set()  # Wake up any waiting tasks
                pause_event = None
            except Exception as e:
                logger.error(f"Error cleaning up pause event: {e}")
        
        # Clean up pause condition from state
        if state.pause_condition:
            try:
                with state.pause_condition:
                    state.pause_condition.notify_all()
                state.pause_condition = threading.Condition()
            except Exception as e:
                logger.error(f"Error cleaning up pause condition: {e}")

        # Clear all state variables
        state.current_playing_file = None
        state.execution_progress = 0
        state.is_running = False
        state.pause_requested = False
        state.stop_requested = True
        state.is_clearing = False
        
        # Reset machine position
        await connection_manager.update_machine_position()
        
        logger.info("Pattern manager resources cleaned up")
        
    except Exception as e:
        logger.error(f"Error during pattern manager cleanup: {e}")
    finally:
        # Ensure we always reset these
        progress_update_task = None
        pattern_lock = None
        pause_event = None

def list_theta_rho_files():
    files = []
    for root, _, filenames in os.walk(THETA_RHO_DIR):
        for fname in filenames:
            # only include .thr files
            if not fname.lower().endswith('.thr'):
                continue

            full_path = os.path.join(root, fname)
            relative_path = os.path.relpath(full_path, THETA_RHO_DIR)
            files.append(relative_path)

    logger.debug(f"Found {len(files)} theta-rho files")
    return files

def parse_theta_rho_file(file_path):
    """Parse a theta-rho file and return a list of (theta, rho) pairs."""
    coordinates = []
    try:
        logger.debug(f"Parsing theta-rho file: {file_path}")
        with open(file_path, 'r') as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    theta, rho = map(float, line.split())
                    coordinates.append((theta, rho))
                except ValueError:
                    logger.warning(f"Skipping invalid line: {line}")
                    continue
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        return coordinates

    # Normalization Step
    if coordinates:
        first_theta = coordinates[0][0]
        normalized = [(theta - first_theta, rho) for theta, rho in coordinates]
        coordinates = normalized
        logger.debug(f"Parsed {len(coordinates)} coordinates from {file_path}")
        # Apply the user-requested rotation (in radians):
        rot = getattr(state, 'rotation_angle', 0.0)
        if rot:
            coordinates = [(theta + rot, rho) for theta, rho in coordinates]
            logger.debug(f"Applied rotation {rot:.3f} rad to all θ")
    return coordinates

def get_clear_pattern_file(clear_pattern_mode, path=None):
    """Return a .thr file path based on pattern_name and table type."""
    if not clear_pattern_mode or clear_pattern_mode == 'none':
        return
    
    # Define patterns for each table type
    clear_patterns = {
        'dune_weaver': {
            'clear_from_out': './patterns/clear_from_out.thr',
            'clear_from_in': './patterns/clear_from_in.thr',
            'clear_sideway': './patterns/clear_sideway.thr'
        },
        'dune_weaver_mini': {
            'clear_from_out': './patterns/clear_from_out_mini.thr',
            'clear_from_in': './patterns/clear_from_in_mini.thr',
            'clear_sideway': './patterns/clear_sideway_mini.thr'
        },
        'dune_weaver_pro': {
            'clear_from_out': './patterns/clear_from_out_pro.thr',
            'clear_from_in': './patterns/clear_from_in_pro.thr',
            'clear_sideway': './patterns/clear_sideway_pro.thr'
        }
    }
    
    # Get patterns for current table type, fallback to standard patterns if type not found
    table_patterns = clear_patterns.get(state.table_type, clear_patterns['dune_weaver'])
    
    logger.debug(f"Clear pattern mode: {clear_pattern_mode} for table type: {state.table_type}")
    
    if clear_pattern_mode == "random":
        return random.choice(list(table_patterns.values()))

    if clear_pattern_mode == 'adaptive':
        if not path:
            logger.warning("No path provided for adaptive clear pattern")
            return random.choice(list(table_patterns.values()))
            
        coordinates = parse_theta_rho_file(path)
        if not coordinates:
            logger.warning("No valid coordinates found in file for adaptive clear pattern")
            return random.choice(list(table_patterns.values()))
            
        first_rho = coordinates[0][1]
        if first_rho < 0.5:
            return table_patterns['clear_from_out']
        else:
            return random.choice([table_patterns['clear_from_in'], table_patterns['clear_sideway']])
    else:
        if clear_pattern_mode not in table_patterns:
            return False
        return table_patterns[clear_pattern_mode]

def is_clear_pattern(file_path):
    """Check if a file path is a clear pattern file."""
    # Get all possible clear pattern files for all table types
    clear_patterns = []
    for table_type in ['dune_weaver', 'dune_weaver_mini', 'dune_weaver_pro']:
        clear_patterns.extend([
            f'./patterns/clear_from_out{("_" + table_type.split("_")[-1]) if table_type != "dune_weaver" else ""}.thr',
            f'./patterns/clear_from_in{("_" + table_type.split("_")[-1]) if table_type != "dune_weaver" else ""}.thr',
            f'./patterns/clear_sideway{("_" + table_type.split("_")[-1]) if table_type != "dune_weaver" else ""}.thr'
        ])
    
    # Normalize paths for comparison
    normalized_path = os.path.normpath(file_path)
    normalized_clear_patterns = [os.path.normpath(p) for p in clear_patterns]
    
    # Check if the file path matches any clear pattern path
    return normalized_path in normalized_clear_patterns

async def run_theta_rho_file(file_path, is_playlist=False, preset: int = None):
    """Run a single .thr file, applying the correct WLED preset at start & resume."""
    if pattern_lock.locked():
        logger.warning("Another pattern is already running. Cannot start a new one.")
        return

    async with pattern_lock:
        global progress_update_task
        # start progress updater if this isn’t part of a playlist
        if not is_playlist and not progress_update_task:
            progress_update_task = asyncio.create_task(broadcast_progress())

        coords = parse_theta_rho_file(file_path)
        total = len(coords)
        if total < 2:
            logger.warning("Not enough coordinates for interpolation")
            if not is_playlist:
                state.current_playing_file = None
                state.execution_progress = None
            return

        # prepare state
        state.execution_progress = (0, total, None, 0)
        stop_actions(clear_playlist=False)
        state.current_playing_file = file_path
        state.stop_requested = False
        reset_theta()
        start_time = time.time()

        # decide which preset to use
        logger.info(f"Preset passed is: {preset} for '{file_path}'")
        if preset is None:
            chosen = 2
        else:
            chosen = preset
        logger.info(f"Applying preset {chosen} for '{file_path}'")
        state.led_controller.set_preset(chosen)

        # run all points
        with tqdm(total=total, unit="coords", desc=f"Executing {file_path}") as pbar:
            for i, (theta, rho) in enumerate(coords):
                if state.stop_requested or state.skip_requested:
                    if state.led_controller:
                        effect_idle(state.led_controller)
                    break

                # handle pause/resume
                if state.pause_requested:
                    if state.led_controller:
                        effect_idle(state.led_controller)
                    await pause_event.wait()
                    # re-apply preset after resume
                    state.led_controller.set_preset(chosen)

                move_polar(theta, rho)
                pbar.update(1)

                # update progress
                elapsed = time.time() - start_time
                rate = pbar.format_dict.get("rate") or 1
                remaining = (total - (i+1)) / rate
                state.execution_progress = (i+1, total, remaining, elapsed)
                await asyncio.sleep(0.001)

        # final cleanup
        state.execution_progress = (total, total, 0, time.time() - start_time)
        await asyncio.sleep(0.1)
        connection_manager.check_idle()

        if not is_playlist:
            state.current_playing_file = None
            state.execution_progress = None
        else:
            logger.info("Playlist step complete; keeping state for next item")

        if not is_playlist and progress_update_task:
            progress_update_task.cancel()
            try: await progress_update_task
            except asyncio.CancelledError: pass
            progress_update_task = None


async def run_theta_rho_files(file_paths, pause_time=0, clear_pattern=None, run_mode="single", shuffle=False):
    """Run a full playlist, injecting clear patterns (with next‐item preset) automatically."""
    state.stop_requested = False
    state.playlist_mode = run_mode
    state.current_playlist_index = 0

    # build a flat sequence of (path, preset) pairs
    entries = state.current_playlist_entries or []
    seq = []
    for e in entries:
        # inject clear-pattern step if requested
        if clear_pattern and clear_pattern != "none":
            cp = get_clear_pattern_file(clear_pattern, os.path.join(THETA_RHO_DIR, e["pattern"]))
            if cp:
                seq.append((cp, e["preset"]))
        # then the real pattern
        seq.append((os.path.join(THETA_RHO_DIR, e["pattern"]), e["preset"]))
    logger.info(f"Playlist sequence: {seq}")
    if shuffle:
        random.shuffle(seq)

    global progress_update_task
    if not progress_update_task:
        progress_update_task = asyncio.create_task(broadcast_progress())

    try:
        for idx, (path, preset) in enumerate(seq):
            state.current_playlist_index = idx
            if state.stop_requested:
                break

            logger.info(f"Playlist idx={idx}: running {path} with preset {preset}")

            await run_theta_rho_file(path, is_playlist=True, preset=preset)

            # pause between main patterns only
            if idx + 1 < len(seq) and pause_time > 0 and not state.skip_requested:
                prev = seq[idx][0]
                # skip pause after a clear‐pattern step
                if not is_clear_pattern(prev):
                    await asyncio.sleep(pause_time)

            state.skip_requested = False

        # if indefinite, loop again
        if run_mode == "indefinite" and not state.stop_requested:
            return await run_theta_rho_files(file_paths, pause_time, clear_pattern, run_mode, shuffle)

    finally:
        # final cleanup
        if progress_update_task:
            progress_update_task.cancel()
            try: await progress_update_task
            except asyncio.CancelledError: pass
            progress_update_task = None

        state.current_playing_file = None
        state.execution_progress = None
        state.current_playlist_index = None
        state.playlist_mode = None
        state.current_playlist_entries = None
        state.current_playlist_name = None
        if state.led_controller:
            effect_idle(state.led_controller)
        logger.info("Playlist fully completed")
def stop_actions(clear_playlist=True):
    """Stop all current actions."""
    try:
        with state.pause_condition:
            state.pause_requested = False
            state.stop_requested = True
            state.current_playing_file = None
            state.execution_progress = None
            state.is_clearing = False

            if clear_playlist:
                # Clear out entries & name instead of the old playlist array
                state.current_playlist_entries = None
                state.current_playlist_name = None
                state.current_playlist_index = None
                state.playlist_mode = None

                # Cancel the progress task
                global progress_update_task
                if progress_update_task and not progress_update_task.done():
                    progress_update_task.cancel()

            state.pause_condition.notify_all()
            connection_manager.update_machine_position()
    except Exception as e:
        logger.error(f"Error during stop_actions: {e}")
        connection_manager.update_machine_position()


def move_polar(theta, rho):
    """
    This functions take in a pair of theta rho coordinate, compute the distance to travel based on current theta, rho,
    and translate the motion to gcode jog command and sent to grbl. 
    
    Since having similar steps_per_mm will make x and y axis moves at around the same speed, we have to scale the 
    x_steps_per_mm and y_steps_per_mm so that they are roughly the same. Here's the range of motion:
    
    X axis (angular): 50mm = 1 revolution
    Y axis (radial): 0 => 20mm = theta 0 (center) => 1 (perimeter)
    
    Args:
        theta (_type_): _description_
        rho (_type_): _description_
    """
    # Adding soft limit to reduce hardware sound
    # soft_limit_inner = 0.01
    # if rho < soft_limit_inner:
    #     rho = soft_limit_inner
    
    # soft_limit_outter = 0.015
    # if rho > (1-soft_limit_outter):
    #     rho = (1-soft_limit_outter)
    
    if state.table_type == 'dune_weaver_mini':
        x_scaling_factor = 2
        y_scaling_factor = 3.7
    else:
        x_scaling_factor = 2
        y_scaling_factor = 5
    
    delta_theta = theta - state.current_theta
    delta_rho = rho - state.current_rho
    x_increment = delta_theta * 100 / (2 * pi * x_scaling_factor)  # Added -1 to reverse direction
    y_increment = delta_rho * 100 / y_scaling_factor
    
    x_total_steps = state.x_steps_per_mm * (100/x_scaling_factor)
    y_total_steps = state.y_steps_per_mm * (100/y_scaling_factor)
        
    offset = x_increment * (x_total_steps * x_scaling_factor / (state.gear_ratio * y_total_steps * y_scaling_factor))

    if state.table_type == 'dune_weaver_mini':
        y_increment -= offset
    else:
        y_increment += offset
    
    new_x_abs = state.machine_x + x_increment
    new_y_abs = state.machine_y + y_increment
    
    # dynamic_speed = compute_dynamic_speed(rho, max_speed=state.speed)
    
    connection_manager.send_grbl_coordinates(round(new_x_abs, 3), round(new_y_abs,3), state.speed)
    state.current_theta = theta
    state.current_rho = rho
    state.machine_x = new_x_abs
    state.machine_y = new_y_abs
    
def pause_execution():
    """Pause pattern execution using asyncio Event."""
    logger.info("Pausing pattern execution")
    state.pause_requested = True
    pause_event.clear()  # Clear the event to pause execution
    return True

def resume_execution():
    """Resume pattern execution using asyncio Event."""
    logger.info("Resuming pattern execution")
    state.pause_requested = False
    pause_event.set()  # Set the event to resume execution
    return True
    
def reset_theta():
    logger.info('Resetting Theta')
    state.current_theta = 0
    connection_manager.update_machine_position()

def set_speed(new_speed):
    state.speed = new_speed
    logger.info(f'Set new state.speed {new_speed}')

def get_status():
    """Get the current status of pattern execution."""
    status = {
        "current_file": state.current_playing_file,
        "is_paused": state.pause_requested,
        "is_running": bool(state.current_playing_file and not state.stop_requested),
        "progress": None,
        "playlist": None,
        "speed": state.speed
    }

    # Use the entries list, not current_playlist
    entries = state.current_playlist_entries or []
    idx = state.current_playlist_index
    total = len(entries)
    if total > 0 and idx is not None:
        next_file = None
        if idx + 1 < total:
            next_file = entries[idx + 1]["pattern"]
        status["playlist"] = {
            "current_index": idx,
            "total_files": total,
            "mode": state.playlist_mode,
            "next_file": next_file
        }

    if state.execution_progress:
        current, total_coords, remaining_time, elapsed_time = state.execution_progress
        status["progress"] = {
            "current": current,
            "total": total_coords,
            "remaining_time": remaining_time,
            "elapsed_time": elapsed_time,
            "percentage": (current / total_coords * 100) if total_coords > 0 else 0
        }

    return status


async def broadcast_progress():
    """Background task to broadcast progress updates."""
    from app import active_status_connections
    while True:
        # Send status updates regardless of pattern_lock state
        status = get_status()
        disconnected = set()
        
        # Create a copy of the set for iteration
        active_connections = active_status_connections.copy()
        
        for websocket in active_connections:
            try:
                await websocket.send_json(status)
            except Exception as e:
                logger.warning(f"Failed to send status update: {e}")
                disconnected.add(websocket)
        
        # Clean up disconnected clients
        if disconnected:
            active_status_connections.difference_update(disconnected)
            
        # Check if we should stop broadcasting
        if not state.current_playlist:
            # If no playlist, only stop if no pattern is being executed
            if not pattern_lock.locked():
                logger.info("No playlist or pattern running, stopping broadcast")
                break
        
        # Wait before next update
        await asyncio.sleep(1)
