"""MQTT utilities and callback management."""
from typing import Dict, Callable
from modules.core.pattern_manager import list_theta_rho_files
from modules.core import execution
from modules.connection.connection_manager import home
from modules.core.state import state

def create_mqtt_callbacks() -> Dict[str, Callable]:
    """Create and return the MQTT callback registry.

    All execution actions are firmware-delegated (modules/core/execution).
    The MQTT handler checks and handles both async and sync callables.
    """
    return {
        'run_pattern': execution.run_pattern,       # async
        'run_playlist': execution.start_playlist,   # async
        'stop': execution.stop,                     # async
        'pause': execution.pause,                   # async
        'resume': execution.resume,                 # async
        'skip': execution.skip,                     # async
        'home': home,
        'set_speed': execution.set_speed,           # async
    }

def get_mqtt_state():
    """Get the current state for MQTT updates."""
    patterns = list_theta_rho_files()

    status = execution.get_cached_status()
    is_running = bool(status.get("is_running"))

    board_connected = (state.conn.is_connected() if state.conn else False)
    board_status = f"connected to {state.port}" if board_connected else "disconnected"

    return {
        'is_running': is_running,
        'current_file': state.current_playing_file or '',
        'patterns': sorted(patterns),
        'serial': board_status,
        'current_playlist': state.current_playlist,
        'current_playlist_index': (status.get("playlist") or {}).get("current_index"),
        'playlist_mode': state.playlist_mode
    }
