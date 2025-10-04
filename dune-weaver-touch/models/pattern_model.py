from PySide6.QtCore import QAbstractListModel, Qt, Slot, Signal
from PySide6.QtQml import QmlElement
from pathlib import Path

QML_IMPORT_NAME = "DuneWeaver"
QML_IMPORT_MAJOR_VERSION = 1

@QmlElement
class PatternModel(QAbstractListModel):
    """Model for pattern list with direct file system access"""
    
    NameRole = Qt.UserRole + 1
    PathRole = Qt.UserRole + 2
    PreviewRole = Qt.UserRole + 3
    
    def __init__(self):
        super().__init__()
        self._patterns = []
        self._filtered_patterns = []
        # Look for patterns in the parent directory (main dune-weaver folder)
        self.patterns_dir = Path("../patterns")
        self.cache_dir = Path("../patterns/cached_images")
        self.refresh()
    
    def roleNames(self):
        return {
            self.NameRole: b"name",
            self.PathRole: b"path", 
            self.PreviewRole: b"preview"
        }
    
    def rowCount(self, parent=None):
        return len(self._filtered_patterns)
    
    def data(self, index, role):
        if not index.isValid() or index.row() >= len(self._filtered_patterns):
            return None
        
        pattern = self._filtered_patterns[index.row()]
        
        if role == self.NameRole:
            return pattern["name"]
        elif role == self.PathRole:
            return pattern["path"]
        elif role == self.PreviewRole:
            # For patterns in subdirectories, check both flattened and hierarchical cache structures
            pattern_name = pattern["name"]
            
            # Try PNG format for kiosk compatibility
            # First try hierarchical structure (preserving subdirectories)
            preview_path_hierarchical = self.cache_dir / f"{pattern_name}.png"
            if preview_path_hierarchical.exists():
                return str(preview_path_hierarchical.absolute())
            
            # Then try flattened structure (replace / with _)
            preview_name_flat = pattern_name.replace("/", "_").replace("\\", "_")
            preview_path_flat = self.cache_dir / f"{preview_name_flat}.png"
            if preview_path_flat.exists():
                return str(preview_path_flat.absolute())
            
            # Fallback to WebP if PNG not found (for existing caches)
            preview_path_hierarchical_webp = self.cache_dir / f"{pattern_name}.webp"
            if preview_path_hierarchical_webp.exists():
                return str(preview_path_hierarchical_webp.absolute())
            
            preview_path_flat_webp = self.cache_dir / f"{preview_name_flat}.webp"
            if preview_path_flat_webp.exists():
                return str(preview_path_flat_webp.absolute())
            
            return ""
        
        return None
    
    @Slot()
    def refresh(self):
        print(f"Loading patterns from: {self.patterns_dir.absolute()}")
        self.beginResetModel()
        patterns = []
        for file_path in self.patterns_dir.rglob("*.thr"):
            relative = file_path.relative_to(self.patterns_dir)
            patterns.append({
                "name": str(relative),
                "path": str(file_path)
            })
        self._patterns = sorted(patterns, key=lambda x: x["name"])
        self._filtered_patterns = self._patterns.copy()
        print(f"Loaded {len(self._patterns)} patterns")
        self.endResetModel()
    
    @Slot(str)
    def filter(self, search_text):
        self.beginResetModel()
        if not search_text:
            self._filtered_patterns = self._patterns.copy()
        else:
            search_lower = search_text.lower()
            self._filtered_patterns = [
                p for p in self._patterns 
                if search_lower in p["name"].lower()
            ]
        self.endResetModel()