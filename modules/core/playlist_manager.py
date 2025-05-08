import json
import os
import threading
import logging
import asyncio
from modules.core import pattern_manager
from modules.core.state import state

# Configure logging
logger = logging.getLogger(__name__)

# Global state
PLAYLISTS_FILE = os.path.join(os.getcwd(), "playlists.json")

# Ensure the file exists and contains at least an empty JSON object
if not os.path.isfile(PLAYLISTS_FILE):
    logger.info(f"Creating new playlists file at {PLAYLISTS_FILE}")
    with open(PLAYLISTS_FILE, "w") as f:
        json.dump({}, f, indent=2)

def load_playlists():
    """Load the entire playlists dictionary, migrating old format automatically."""
    # 1) read raw JSON
    with open(PLAYLISTS_FILE, "r") as f:
        playlists = json.load(f)

    migrated = False

    # 2) detect old‐style entries (list of strings) and convert them
    for name, items in playlists.items():
        if isinstance(items, list) and items and isinstance(items[0], str):
            logger.info(f"Migrating playlist '{name}' from old format to new format")
            # build new list of dicts, default preset = 2
            playlists[name] = [
                {"pattern": pattern_str, "preset": 2}
                for pattern_str in items
            ]
            migrated = True

    # 3) if we changed anything, write it back
    if migrated:
        with open(PLAYLISTS_FILE, "w") as f:
            json.dump(playlists, f, indent=2)
        logger.info("Playlists file migrated to new format")

    return playlists

def save_playlists(playlists_dict):
    """Save the entire playlists dictionary back to the JSON file."""
    logger.debug(f"Saving {len(playlists_dict)} playlists to file")
    with open(PLAYLISTS_FILE, "w") as f:
        json.dump(playlists_dict, f, indent=2)

def list_all_playlists():
    """Returns a list of all playlist names."""
    playlists_dict = load_playlists()
    playlist_names = list(playlists_dict.keys())
    logger.debug(f"Found {len(playlist_names)} playlists")
    return playlist_names

def get_playlist(playlist_name):
    """Get a specific playlist by name."""
    playlists_dict = load_playlists()
    if playlist_name not in playlists_dict:
        logger.warning(f"Playlist not found: {playlist_name}")
        return None
    logger.debug(f"Retrieved playlist: {playlist_name}")
    return {
        "name": playlist_name,
        "files": playlists_dict[playlist_name]
    }

def create_playlist(playlist_name, files):
    """Create or update a playlist."""
    playlists_dict = load_playlists()
    playlists_dict[playlist_name] = files
    save_playlists(playlists_dict)
    logger.info(f"Created/updated playlist '{playlist_name}' with {len(files)} files")
    return True

def modify_playlist(playlist_name, files):
    """Modify an existing playlist."""
    logger.info(f"Modifying playlist '{playlist_name}' with {len(files)} files")
    return create_playlist(playlist_name, files)

def delete_playlist(playlist_name):
    """Delete a playlist."""
    playlists_dict = load_playlists()
    if playlist_name not in playlists_dict:
        logger.warning(f"Cannot delete non-existent playlist: {playlist_name}")
        return False
    del playlists_dict[playlist_name]
    save_playlists(playlists_dict)
    logger.info(f"Deleted playlist: {playlist_name}")
    return True

def add_to_playlist(playlist_name, pattern, preset=2):
    """Add a pattern to an existing playlist."""
    playlists_dict = load_playlists()
    if playlist_name not in playlists_dict:
        logger.warning(f"Cannot add to non-existent playlist: {playlist_name}")
        return False
    # pattern may be a dict already, or a string + preset passed in

    if isinstance(pattern, dict):
        entry = pattern
    else:
        entry = {"pattern": pattern, "preset": int(preset)}
        playlists_dict[playlist_name].append(entry)
    save_playlists(playlists_dict)
    logger.info(f"Added {entry} to playlist '{playlist_name}'")
    return True

async def run_playlist(playlist_name, pause_time=0, clear_pattern=None, run_mode="single", shuffle=False):
    """Run a playlist with the given options."""
    if pattern_manager.pattern_lock.locked():
        logger.warning("Cannot start playlist: Another pattern is already running")
        return False, "Cannot start playlist: Another pattern is already running"

    playlists = load_playlists()
    if playlist_name not in playlists:
        logger.error(f"Cannot run non-existent playlist: {playlist_name}")
        return False, "Playlist not found"

    # ——— MIGRATE INTO APP STATE ———
    entries = playlists[playlist_name]
    state.current_playlist_entries = entries
    state.current_playlist_name = playlist_name
    state.current_playlist_index = 0

    # Build just the file-paths for execution
    file_paths = [
        os.path.join(pattern_manager.THETA_RHO_DIR, e["pattern"])
        for e in entries
    ]
    if not file_paths:
        logger.warning(f"Cannot run empty playlist: {playlist_name}")
        return False, "Playlist is empty"

    try:
        logger.info(f"Starting playlist '{playlist_name}' with mode={run_mode}, shuffle={shuffle}")
        state.current_playlist = file_paths
        state.current_playlist_name = playlist_name
        # remember the raw entries so we can know each preset later
        state.current_playlist_entries = playlists[playlist_name]
        asyncio.create_task(
            pattern_manager.run_theta_rho_files(
                file_paths,
                pause_time=pause_time,
                clear_pattern=clear_pattern,
                run_mode=run_mode,
                shuffle=shuffle,
            )
        )
        return True, f"Playlist '{playlist_name}' is now running."
    except Exception as e:
        logger.error(f"Failed to run playlist '{playlist_name}': {str(e)}")
        return False, str(e)
