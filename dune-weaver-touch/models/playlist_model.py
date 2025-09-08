from PySide6.QtCore import QAbstractListModel, Qt, Slot, Signal
from PySide6.QtQml import QmlElement
from pathlib import Path
import json

QML_IMPORT_NAME = "DuneWeaver"
QML_IMPORT_MAJOR_VERSION = 1

@QmlElement
class PlaylistModel(QAbstractListModel):
    """Model for playlist list with direct JSON file access"""
    
    NameRole = Qt.UserRole + 1
    ItemCountRole = Qt.UserRole + 2
    
    def __init__(self):
        super().__init__()
        self._playlists = []
        # Look for playlists in the parent directory (main dune-weaver folder)
        self.playlists_file = Path("../playlists.json")
        self.refresh()
    
    def roleNames(self):
        return {
            self.NameRole: b"name",
            self.ItemCountRole: b"itemCount"
        }
    
    def rowCount(self, parent=None):
        return len(self._playlists)
    
    def data(self, index, role):
        if not index.isValid() or index.row() >= len(self._playlists):
            return None
        
        playlist = self._playlists[index.row()]
        
        if role == self.NameRole:
            return playlist["name"]
        elif role == self.ItemCountRole:
            return playlist["itemCount"]
        
        return None
    
    @Slot()
    def refresh(self):
        self.beginResetModel()
        playlists = []
        
        if self.playlists_file.exists():
            try:
                with open(self.playlists_file, 'r') as f:
                    self._playlist_data = json.load(f)
                    for name, playlist_patterns in self._playlist_data.items():
                        # playlist_patterns is a list of pattern filenames
                        playlists.append({
                            "name": name,
                            "itemCount": len(playlist_patterns) if isinstance(playlist_patterns, list) else 0
                        })
            except (json.JSONDecodeError, KeyError, AttributeError):
                self._playlist_data = {}
        else:
            self._playlist_data = {}
        
        self._playlists = sorted(playlists, key=lambda x: x["name"])
        self.endResetModel()
    
    @Slot(str, result=list)
    def getPatternsForPlaylist(self, playlistName):
        """Get the list of patterns for a given playlist"""
        if hasattr(self, '_playlist_data') and playlistName in self._playlist_data:
            patterns = self._playlist_data[playlistName]
            if isinstance(patterns, list):
                # Clean up pattern names for display
                cleaned_patterns = []
                for pattern in patterns:
                    # Remove path and .thr extension for display
                    clean_name = pattern
                    if '/' in clean_name:
                        clean_name = clean_name.split('/')[-1]
                    if clean_name.endswith('.thr'):
                        clean_name = clean_name[:-4]
                    cleaned_patterns.append(clean_name)
                return cleaned_patterns
        return []