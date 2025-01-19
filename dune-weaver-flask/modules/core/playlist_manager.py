import os
import json
import logging

logger = logging.getLogger(__name__)

PLAYLISTS_FILE = os.path.join(os.getcwd(), "playlists.json")

def load_playlists():
    """
    Load the entire playlists dictionary from the JSON file.
    Returns something like: {
        "My Playlist": ["file1.thr", "file2.thr"],
        "Another": ["x.thr"]
    }
    """
    with open(PLAYLISTS_FILE, "r") as f:
        return json.load(f)

def save_playlists(playlists_dict):
    """Save the entire playlists dictionary back to the JSON file."""
    with open(PLAYLISTS_FILE, "w") as f:
        json.dump(playlists_dict, f, indent=2)

def list_all_playlists():
    """Returns a list of all playlist names."""
    playlists_dict = load_playlists()
    return list(playlists_dict.keys())

def get_playlist(playlist_name):
    """Get a specific playlist by name."""
    playlists_dict = load_playlists()
    if playlist_name not in playlists_dict:
        return None
    return {
        "name": playlist_name,
        "files": playlists_dict[playlist_name]
    }

def create_playlist(playlist_name, files):
    """Create or update a playlist."""
    playlists_dict = load_playlists()
    playlists_dict[playlist_name] = files
    save_playlists(playlists_dict)
    return True

def modify_playlist(playlist_name, files):
    """Modify an existing playlist."""
    playlists_dict = load_playlists()
    if playlist_name not in playlists_dict:
        return False
    playlists_dict[playlist_name] = files
    save_playlists(playlists_dict)
    return True

def delete_playlist(playlist_name):
    """Delete a playlist."""
    playlists_dict = load_playlists()
    if playlist_name not in playlists_dict:
        return False
    del playlists_dict[playlist_name]
    save_playlists(playlists_dict)
    return True

def add_to_playlist(playlist_name, pattern):
    """Add a pattern to an existing playlist."""
    playlists_dict = load_playlists()
    if playlist_name not in playlists_dict:
        return False
    playlists_dict[playlist_name].append(pattern)
    save_playlists(playlists_dict)
    return True 