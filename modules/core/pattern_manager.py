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
        for file in filenames:
            relative_path = os.path.relpath(os.path.join(root, file), THETA_RHO_DIR)
            # Normalize path separators to always use forward slashes for consistency across platforms
            relative_path = relative_path.replace(os.sep, '/')
            files.append(relative_path)
    logger.debug(f"Found {len(files)} theta-rho files")
    return [file for file in files if file.endswith('.thr')]

def parse_theta_rho_file(file_path):
    """Parse a theta-rho file and return a list of (theta, rho) pairs."""
    coordinates = []
    try:
        logger.debug(f"Parsing theta-rho file: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as file:
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

        logger.debug(f"Parsed {len(coordinates)} coordinates from {file_path}")
    return coordinates

def get_first_rho_from_cache(file_path):
    """Get the first rho value from cached metadata, falling back to file parsing if needed."""
    try:
        # Import cache_manager locally to avoid circular import
        from modules.core import cache_manager
        
        # Try to get from metadata cache first
        file_name = os.path.basename(file_path)
        metadata = cache_manager.get_pattern_metadata(file_name)
        
        if metadata and 'first_coordinate' in metadata:
            # In the cache, 'x' is theta and 'y' is rho
            return metadata['first_coordinate']['y']
        
        # Fallback to parsing the file if not in cache
        logger.debug(f"Metadata not cached for {file_name}, parsing file")
        coordinates = parse_theta_rho_file(file_path)
        if coordinates:
            return coordinates[0][1]  # Return rho value
        
        return None
    except Exception as e:
        logger.warning(f"Error getting first rho from cache for {file_path}: {str(e)}")
        return None

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
            'clear_from_out_Ultra': './patterns/clear_from_out_Ultra.thr',
            'clear_from_in': './patterns/clear_from_in_pro.thr',
            'clear_from_in_Ultra': './patterns/clear_from_in_Ultra.thr',
            'clear_sideway': './patterns/clear_sideway_pro.thr'
        }
    }
    
    # Get patterns for current table type, fallback to standard patterns if type not found
    table_patterns = clear_patterns.get(state.table_type, clear_patterns['dune_weaver'])
    
    # Check for custom patterns first
    if state.custom_clear_from_out and clear_pattern_mode in ['clear_from_out', 'adaptive']:
        if clear_pattern_mode == 'adaptive':
            # For adaptive mode, use cached metadata to check first rho
            if path:
                first_rho = get_first_rho_from_cache(path)
                if first_rho is not None and first_rho < 0.5:
                    # Use custom clear_from_out if set
                    custom_path = os.path.join('./patterns', state.custom_clear_from_out)
                    if os.path.exists(custom_path):
                        logger.debug(f"Using custom clear_from_out: {custom_path}")
                        return custom_path
        elif clear_pattern_mode == 'clear_from_out':
            custom_path = os.path.join('./patterns', state.custom_clear_from_out)
            if os.path.exists(custom_path):
                logger.debug(f"Using custom clear_from_out: {custom_path}")
                return custom_path
    
    if state.custom_clear_from_in and clear_pattern_mode in ['clear_from_in', 'adaptive']:
        if clear_pattern_mode == 'adaptive':
            # For adaptive mode, use cached metadata to check first rho
            if path:
                first_rho = get_first_rho_from_cache(path)
                if first_rho is not None and first_rho >= 0.5:
                    # Use custom clear_from_in if set
                    custom_path = os.path.join('./patterns', state.custom_clear_from_in)
                    if os.path.exists(custom_path):
                        logger.debug(f"Using custom clear_from_in: {custom_path}")
                        return custom_path
        elif clear_pattern_mode == 'clear_from_in':
            custom_path = os.path.join('./patterns', state.custom_clear_from_in)
            if os.path.exists(custom_path):
                logger.debug(f"Using custom clear_from_in: {custom_path}")
                return custom_path
    
    logger.debug(f"Clear pattern mode: {clear_pattern_mode} for table type: {state.table_type}")
    
    if clear_pattern_mode == "random":
        return random.choice(list(table_patterns.values()))

    if clear_pattern_mode == 'adaptive':
        if not path:
            logger.warning("No path provided for adaptive clear pattern")
            return random.choice(list(table_patterns.values()))
            
        # Use cached metadata to get first rho value
        first_rho = get_first_rho_from_cache(path)
        if first_rho is None:
            logger.warning("Could not determine first rho value for adaptive clear pattern")
            return random.choice(list(table_patterns.values()))
            
        if first_rho < 0.5:
            return table_patterns['clear_from_out']
        else:
            return table_patterns['clear_from_in']
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

async def run_theta_rho_file(file_path, is_playlist=False):
    """Run a theta-rho file by sending data in optimized batches with tqdm ETA tracking."""
    if pattern_lock.locked():
        logger.warning("Another pattern is already running. Cannot start a new one.")
        return

    async with pattern_lock:  # This ensures only one pattern can run at a time
        # Start progress update task only if not part of a playlist
        global progress_update_task
        if not is_playlist and not progress_update_task:
            progress_update_task = asyncio.create_task(broadcast_progress())
        
        coordinates = parse_theta_rho_file(file_path)
        total_coordinates = len(coordinates)

        if total_coordinates < 2:
            logger.warning("Not enough coordinates for interpolation")
            if not is_playlist:
                state.current_playing_file = None
                state.execution_progress = None
            return

        # Determine if this is a clearing pattern and set appropriate speed
        is_clear_file = is_clear_pattern(file_path)
        # Use clear_pattern_speed if it's set and this is a clear file, otherwise use state.speed
        if is_clear_file and state.clear_pattern_speed is not None:
            pattern_speed = state.clear_pattern_speed
        else:
            pattern_speed = state.speed
        
        if is_clear_file:
            logger.info(f"Running clearing pattern at speed {pattern_speed}")
        else:
            logger.info(f"Running normal pattern at speed {pattern_speed}")

        state.execution_progress = (0, total_coordinates, None, 0)
        
        # stop actions without resetting the playlist
        stop_actions(clear_playlist=False)

        state.current_playing_file = file_path
        state.stop_requested = False
        logger.info(f"Starting pattern execution: {file_path}")
        logger.info(f"t: {state.current_theta}, r: {state.current_rho}")
        reset_theta()
        
        start_time = time.time()
        if state.led_controller:
            effect_playing(state.led_controller)
            
        with tqdm(
            total=total_coordinates,
            unit="coords",
            desc=f"Executing Pattern {file_path}",
            dynamic_ncols=True,
            disable=False,
            mininterval=1.0
        ) as pbar:
            for i, coordinate in enumerate(coordinates):
                theta, rho = coordinate
                if state.stop_requested:
                    logger.info("Execution stopped by user")
                    if state.led_controller:
                        effect_idle(state.led_controller)
                    break
                
                if state.skip_requested:
                    logger.info("Skipping pattern...")
                    connection_manager.check_idle()
                    if state.led_controller:
                        effect_idle(state.led_controller)
                    break

                # Wait for resume if paused
                if state.pause_requested:
                    logger.info("Execution paused...")
                    if state.led_controller:
                        effect_idle(state.led_controller)
                    await pause_event.wait()
                    logger.info("Execution resumed...")
                    if state.led_controller:
                        effect_playing(state.led_controller)

                move_polar(theta, rho, pattern_speed)
                
                # Update progress for all coordinates including the first one
                pbar.update(1)
                elapsed_time = time.time() - start_time
                estimated_remaining_time = (total_coordinates - (i + 1)) / pbar.format_dict['rate'] if pbar.format_dict['rate'] and total_coordinates else 0
                state.execution_progress = (i + 1, total_coordinates, estimated_remaining_time, elapsed_time)
                
                # Add a small delay to allow other async operations
                await asyncio.sleep(0.001)

        # Update progress one last time to show 100%
        elapsed_time = time.time() - start_time
        state.execution_progress = (total_coordinates, total_coordinates, 0, elapsed_time)
        # Give WebSocket a chance to send the final update
        await asyncio.sleep(0.1)
        
        if not state.conn:
            logger.error("Device is not connected. Stopping pattern execution.")
            return
            
        connection_manager.check_idle()
        
        # Set LED back to idle when pattern completes normally (not stopped early)
        if state.led_controller and not state.stop_requested:
            effect_idle(state.led_controller)
            logger.debug("LED effect set to idle after pattern completion")
        
        # Only clear state if not part of a playlist
        if not is_playlist:
            state.current_playing_file = None
            state.execution_progress = None
            logger.info("Pattern execution completed and state cleared")
        else:
            logger.info("Pattern execution completed, maintaining state for playlist")
        
        # Only cancel progress update task if not part of a playlist
        if not is_playlist and progress_update_task:
            progress_update_task.cancel()
            try:
                await progress_update_task
            except asyncio.CancelledError:
                pass
            progress_update_task = None
            

async def run_theta_rho_files(file_paths, pause_time=0, clear_pattern=None, run_mode="single", shuffle=False):
    """Run multiple .thr files in sequence with options."""
    state.stop_requested = False
    
    # Set initial playlist state
    state.playlist_mode = run_mode
    state.current_playlist_index = 0
    # Start progress update task for the playlist
    global progress_update_task
    if not progress_update_task:
        progress_update_task = asyncio.create_task(broadcast_progress())
    
    
    if shuffle:
        random.shuffle(file_paths)
        logger.info("Playlist shuffled")


    if shuffle:
        random.shuffle(file_paths)
        logger.info("Playlist shuffled")

    try:
        while True:
            # Construct the complete pattern sequence
            pattern_sequence = []
            for path in file_paths:
                # Add clear pattern if specified
                if clear_pattern and clear_pattern != 'none':
                    clear_file_path = get_clear_pattern_file(clear_pattern, path)
                    if clear_file_path:
                        pattern_sequence.append(clear_file_path)
                
                # Add main pattern
                pattern_sequence.append(path)

            # Shuffle if requested
            if shuffle:
                # Get pairs of patterns (clear + main) to keep them together
                pairs = [pattern_sequence[i:i+2] for i in range(0, len(pattern_sequence), 2)]
                random.shuffle(pairs)
                # Flatten the pairs back into a single list
                pattern_sequence = [pattern for pair in pairs for pattern in pair]
                logger.info("Playlist shuffled")

            # Set the playlist to the first pattern
            state.current_playlist = pattern_sequence
            # Execute the pattern sequence
            for idx, file_path in enumerate(pattern_sequence):
                state.current_playlist_index = idx
                if state.stop_requested:
                    logger.info("Execution stopped")
                    return

                # Update state for main patterns only
                logger.info(f"Running pattern {file_path}")
                
                # Execute the pattern
                await run_theta_rho_file(file_path, is_playlist=True)

                # Handle pause between patterns
                if idx < len(pattern_sequence) - 1 and not state.stop_requested and pause_time > 0 and not state.skip_requested:
                    # Check if current pattern is a clear pattern
                    if is_clear_pattern(file_path):
                        logger.info("Skipping pause after clear pattern")
                    else:
                        logger.info(f"Pausing for {pause_time} seconds")
                        state.original_pause_time = pause_time
                        pause_start = time.time()
                        while time.time() - pause_start < pause_time:
                            state.pause_time_remaining = pause_start + pause_time - time.time()
                            if state.skip_requested:
                                logger.info("Pause interrupted by stop/skip request")
                                break
                            await asyncio.sleep(1)
                        state.pause_time_remaining = 0
                    
                state.skip_requested = False

            if run_mode == "indefinite":
                logger.info("Playlist completed. Restarting as per 'indefinite' run mode")
                if pause_time > 0:
                    logger.debug(f"Pausing for {pause_time} seconds before restarting")
                    pause_start = time.time()
                    while time.time() - pause_start < pause_time:
                        state.pause_time_remaining = pause_start + pause_time - time.time()
                        if state.skip_requested:
                            logger.info("Pause interrupted by stop/skip request")
                            break
                        await asyncio.sleep(1)
                    state.pause_time_remaining = 0
                continue
            else:
                logger.info("Playlist completed")
                break

    finally:
        # Clean up progress update task
        if progress_update_task:
            progress_update_task.cancel()
            try:
                await progress_update_task
            except asyncio.CancelledError:
                pass
            progress_update_task = None
            
        # Clear all state variables
        state.current_playing_file = None
        state.execution_progress = None
        state.current_playlist = None
        state.current_playlist_index = None
        state.playlist_mode = None
        
        if state.led_controller:
            effect_idle(state.led_controller)
        
        logger.info("All requested patterns completed (or stopped) and state cleared")

def stop_actions(clear_playlist = True):
    """Stop all current actions."""
    try:
        with state.pause_condition:
            state.pause_requested = False
            state.stop_requested = True
            state.current_playing_file = None
            state.execution_progress = None
            state.is_clearing = False
            
            if clear_playlist:
                # Clear playlist state
                state.current_playlist = None
                state.current_playlist_index = None
                state.playlist_mode = None
                
                # Cancel progress update task if we're clearing the playlist
                global progress_update_task
                if progress_update_task and not progress_update_task.done():
                    progress_update_task.cancel()
                
            state.pause_condition.notify_all()
            connection_manager.update_machine_position()
    except Exception as e:
        logger.error(f"Error during stop_actions: {e}")
        # Ensure we still update machine position even if there's an error
        connection_manager.update_machine_position()

def move_polar(theta, rho, speed=None):
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
        speed (int, optional): Speed override. If None, uses state.speed
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
    
    # Use provided speed or fall back to state.speed
    actual_speed = speed if speed is not None else state.speed
    
    # dynamic_speed = compute_dynamic_speed(rho, max_speed=actual_speed)
    
    connection_manager.send_grbl_coordinates(round(new_x_abs, 3), round(new_y_abs,3), actual_speed)
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
    state.current_theta = state.current_theta % (2 * pi)
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
        "speed": state.speed,
        "pause_time_remaining": state.pause_time_remaining,
        "original_pause_time": getattr(state, 'original_pause_time', None),
        "connection_status": state.conn.is_connected() if state.conn else False,
        "current_theta": state.current_theta,
        "current_rho": state.current_rho
    }
    
    # Add playlist information if available
    if state.current_playlist and state.current_playlist_index is not None:
        next_index = state.current_playlist_index + 1
        status["playlist"] = {
            "current_index": state.current_playlist_index,
            "total_files": len(state.current_playlist),
            "mode": state.playlist_mode,
            "next_file": state.current_playlist[next_index] if next_index < len(state.current_playlist) else None
        }
    
    if state.execution_progress:
        current, total, remaining_time, elapsed_time = state.execution_progress
        status["progress"] = {
            "current": current,
            "total": total,
            "remaining_time": remaining_time,
            "elapsed_time": elapsed_time,
            "percentage": (current / total * 100) if total > 0 else 0
        }
    
    return status

async def broadcast_progress():
    """Background task to broadcast progress updates."""
    from main import broadcast_status_update
    while True:
        # Send status updates regardless of pattern_lock state
        status = get_status()
        
        # Use the existing broadcast function from main.py
        await broadcast_status_update(status)
            
        # Check if we should stop broadcasting
        if not state.current_playlist:
            # If no playlist, only stop if no pattern is being executed
            if not pattern_lock.locked():
                logger.info("No playlist or pattern running, stopping broadcast")
                break
        
        # Wait before next update
        await asyncio.sleep(1)
