"""MQTT utilities and callback management."""
import os
from typing import Dict, Callable
from dune_weaver_flask.modules.core.pattern_manager import (
    run_theta_rho_file, stop_actions, pause_execution,
    resume_execution, THETA_RHO_DIR,
    run_theta_rho_files, list_theta_rho_files
)
from dune_weaver_flask.modules.core.playlist_manager import get_playlist, run_playlist
from dune_weaver_flask.modules.connection.connection_manager import home
from dune_weaver_flask.modules.core.state import state

def create_mqtt_callbacks() -> Dict[str, Callable]:
    """Create and return the MQTT callback registry."""
    def set_speed(speed):
        state.speed = speed

    return {
        'run_pattern': lambda file_path: run_theta_rho_file(file_path),
        'run_playlist': lambda playlist_name: run_playlist(
            playlist_name,
            run_mode="loop",  # Default to loop mode
            pause_time=0,  # No pause between patterns
            clear_pattern=None  # No clearing between patterns
        ),
        'stop': stop_actions,
        'pause': pause_execution,
        'resume': resume_execution,
        'home': home,
        'set_speed': set_speed
    }

def get_mqtt_state():
    """Get the current state for MQTT updates."""
    # Get list of pattern files
    patterns = list_theta_rho_files()
    
    # Get current execution status
    is_running = bool(state.current_playing_file) and not state.stop_requested
    
    # Get serial status
    serial_connected = state.conn.is_connected
    serial_port = state.port if serial_connected else None
    serial_status = f"connected to {serial_port}" if serial_connected else "disconnected"
    
    return {
        'is_running': is_running,
        'current_file': state.current_playing_file or '',
        'patterns': sorted(patterns),
        'serial': serial_status,
        'current_playlist': state.current_playlist,
        'current_playlist_index': state.current_playlist_index,
        'playlist_mode': state.playlist_mode
    } 