"""Playlist list model backed by the firmware's playlist routes.

Playlists are plain ``.txt`` files on the table's SD card (one SD-relative
pattern path per line). We list them via ``/sand_playlists`` and read their
contents from ``/sd/playlists/<name>.txt``.
"""

import asyncio
import logging

from PySide6.QtCore import QAbstractListModel, Qt, Slot, QModelIndex
from PySide6.QtQml import QmlElement

from firmware_client import FirmwareClient

QML_IMPORT_NAME = "DuneWeaver"
QML_IMPORT_MAJOR_VERSION = 1

logger = logging.getLogger("DuneWeaver.PlaylistModel")


def _strip_txt(name):
    return name[:-4] if name.endswith(".txt") else name


def _parse_playlist(text):
    """Parse a playlist file into a list of SD-relative pattern paths."""
    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        items.append(line)
    return items


@QmlElement
class PlaylistModel(QAbstractListModel):
    """Model for playlists, sourced from the sand table over HTTP."""

    NameRole = Qt.UserRole + 1
    ItemCountRole = Qt.UserRole + 2

    def __init__(self):
        super().__init__()
        self._playlists = []        # [{name, itemCount}]
        self._contents = {}         # name -> [raw pattern path, ...]

        self._client = FirmwareClient.instance()
        self._client.baseUrlChanged.connect(lambda _u: self.refresh())
        self.refresh()

    def roleNames(self):
        return {
            self.NameRole: b"name",
            self.ItemCountRole: b"itemCount",
        }

    def rowCount(self, parent=QModelIndex()):
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

    # -------------------------------------------------------------- fetching
    @Slot()
    def refresh(self):
        try:
            asyncio.get_event_loop().create_task(self._fetch())
        except RuntimeError:
            logger.debug("No running loop yet; playlists will load once started")

    async def _fetch(self):
        if not self._client.base_url:
            self._apply([], {})
            return
        try:
            names = await self._client.playlists()
        except Exception as exc:
            logger.warning(f"Failed to fetch playlists: {exc}")
            return

        contents = {}
        playlists = []
        for raw_name in names:
            name = _strip_txt(str(raw_name).lstrip("/"))
            items = []
            try:
                text_bytes = await self._client.fetch_sd_file(f"/playlists/{name}.txt")
                items = _parse_playlist(text_bytes.decode("utf-8", errors="ignore"))
            except Exception as exc:
                logger.debug(f"Failed to read playlist {name}: {exc}")
            contents[name] = items
            playlists.append({"name": name, "itemCount": len(items)})

        playlists.sort(key=lambda x: x["name"].lower())
        self._apply(playlists, contents)

    def _apply(self, playlists, contents):
        self.beginResetModel()
        self._playlists = playlists
        self._contents = contents
        self.endResetModel()
        logger.info(f"Loaded {len(self._playlists)} playlists")

    # --------------------------------------------------------------- queries
    @Slot(str, result=list)
    def getPatternsForPlaylist(self, playlistName):
        """Cleaned pattern names for display (no path, no .thr)."""
        cleaned = []
        for pattern in self._contents.get(playlistName, []):
            clean = pattern.split("/")[-1]
            if clean.endswith(".thr"):
                clean = clean[:-4]
            cleaned.append(clean)
        return cleaned

    @Slot(str, result=list)
    def getRawPatternsForPlaylist(self, playlistName):
        """Raw SD-relative pattern paths (for API calls / editing)."""
        return list(self._contents.get(playlistName, []))

    @Slot(result=list)
    def getAllPlaylistNames(self):
        return sorted(self._contents.keys())
