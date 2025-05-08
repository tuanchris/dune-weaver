"""MQTT utilities and callback management."""
import os
import asyncio
from typing import Dict, Callable
from modules.core.pattern_manager import (
    run_theta_rho_files,
    stop_actions,
    pause_execution,
    resume_execution,
    THETA_RHO_DIR,
    list_theta_rho_files,
)
from modules.core.playlist_manager import run_playlist
from modules.connection.connection_manager import home
from modules.core.state import state

def create_mqtt_callbacks() -> Dict[str, Callable]:
    """Create and return the MQTT callback registry."""
    def set_speed(speed):
        state.speed = speed

    def run_pattern(file_path: str):
        # Prepare a single-entry playlist so our new preset logic runs
        state.current_playlist_entries = [
            {"pattern": os.path.basename(file_path), "preset": 2}
        ]
        # Kick off the runner (uses run_theta_rho_files under the hood)
        asyncio.create_task(
            run_theta_rho_files(
                [os.path.join(THETA_RHO_DIR, file_path)]
            )
        )

    return {
        "run_pattern": run_pattern,
        "run_playlist": lambda playlist_name, run_mode="loop", pause_time=0, clear_pattern=None, shuffle=False: asyncio.create_task(
            run_playlist(
                playlist_name,
                pause_time=pause_time,
                clear_pattern=clear_pattern,
                run_mode=run_mode,
                shuffle=shuffle,
            )
        ),
        "stop": stop_actions,
        "pause": pause_execution,
        "resume": resume_execution,
        "home": home,
        "set_speed": set_speed,
    }

def get_mqtt_state() -> Dict:
    """Get the current state for MQTT updates."""
    patterns = list_theta_rho_files()
    is_running = bool(state.current_playing_file) and not state.stop_requested
    serial_connected = (state.conn.is_connected() if state.conn else False)
    serial_port = state.port if serial_connected else None
    serial_status = f"connected to {serial_port}" if serial_connected else "disconnected"

    return {
        "is_running": is_running,
        "current_file": state.current_playing_file or "",
        "patterns": sorted(patterns),
        # now expose the raw playlist entries (pattern + preset)
        "current_playlist": state.current_playlist_entries or [],
        "current_playlist_index": state.current_playlist_index,
        "playlist_mode": state.playlist_mode,
        "serial": serial_status,
    }
