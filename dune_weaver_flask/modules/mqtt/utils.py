"""MQTT utilities and callback management."""
import os
from typing import Dict, Callable
from dune_weaver_flask.modules.core.pattern_manager import (
    run_theta_rho_file, stop_actions, pause_execution,
    resume_execution, THETA_RHO_DIR,
    run_theta_rho_files
)
from dune_weaver_flask.modules.core.playlist_manager import get_playlist
from dune_weaver_flask.modules.serial.serial_manager import is_connected, home
from dune_weaver_flask.modules.core.state import state

def create_mqtt_callbacks() -> Dict[str, Callable]:
    """Create and return the MQTT callback registry."""
    def set_speed(speed):
        state.speed = speed
    return {
        'run_pattern': run_theta_rho_file,  # Already handles file path
        'run_playlist': lambda name: run_theta_rho_files(
            [os.path.join(THETA_RHO_DIR, file) for file in get_playlist(name)['files']],
            run_mode='loop',
            pause_time=0,
            clear_pattern=None
        ),
        'stop': stop_actions,  # Already handles state
        'pause': pause_execution,  # Already handles state
        'resume': resume_execution,  # Already handles state
        'home': home,
        'set_speed': set_speed
    }

def get_mqtt_state():
    """Get the current state for MQTT updates."""
    # Get list of pattern files
    patterns = []
    for root, _, filenames in os.walk(THETA_RHO_DIR):
        for file in filenames:
            if file.endswith('.thr'):
                patterns.append(file)
    
    # Get current execution status
    is_running = not state.stop_requested and not state.pause_requested
    current_file = state.current_playing_file or ''
    
    # Get serial status
    serial_status = is_connected()
    
    return {
        'is_running': is_running,
        'current_file': current_file,
        'patterns': sorted(patterns),
        'serial': serial_status.get('status', ''),
    } 