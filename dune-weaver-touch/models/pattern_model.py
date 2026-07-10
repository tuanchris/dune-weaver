"""Pattern list model backed by the firmware's ``/sand_patterns`` route.

Patterns now live on the table's SD card, not the local filesystem. This model
fetches the catalogue over HTTP and renders each ``.thr`` preview locally
(cached to disk), updating rows as previews become available.
"""

import asyncio
import logging

from PySide6.QtCore import QAbstractListModel, Qt, Slot, QModelIndex
from PySide6.QtQml import QmlElement

from firmware_client import FirmwareClient
import thr_preview

QML_IMPORT_NAME = "DuneWeaver"
QML_IMPORT_MAJOR_VERSION = 1

logger = logging.getLogger("DuneWeaver.PatternModel")


@QmlElement
class PatternModel(QAbstractListModel):
    """Model for the pattern grid, sourced from the sand table over HTTP."""

    NameRole = Qt.UserRole + 1
    PathRole = Qt.UserRole + 2
    PreviewRole = Qt.UserRole + 3

    def __init__(self):
        super().__init__()
        self._patterns = []           # all patterns [{name, path}]
        self._filtered_patterns = []  # current view
        self._search_text = ""
        self._previews = {}           # rel_path -> cached png path ("" = pending)
        self._rendering = set()       # rel_paths with an in-flight render

        self._client = FirmwareClient.instance()
        self._client.baseUrlChanged.connect(self._on_table_changed)
        self.refresh()

    def roleNames(self):
        return {
            self.NameRole: b"name",
            self.PathRole: b"path",
            self.PreviewRole: b"preview",
        }

    def rowCount(self, parent=QModelIndex()):
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
            return self._preview_for(pattern["name"])

        return None

    # ------------------------------------------------------------- previews
    def _preview_for(self, rel_path):
        """Return a cached preview path, kicking off a render if needed."""
        cached = self._previews.get(rel_path)
        if cached is not None:
            return cached
        # Fast synchronous cache lookup on disk.
        on_disk = thr_preview.cached_preview(self._client.base_url, rel_path)
        if on_disk:
            self._previews[rel_path] = on_disk
            return on_disk
        # Not cached yet - render asynchronously and update the row later.
        self._schedule_render(rel_path)
        return ""

    def _schedule_render(self, rel_path):
        if rel_path in self._rendering or not self._client.base_url:
            return
        self._rendering.add(rel_path)
        try:
            asyncio.get_event_loop().create_task(self._render(rel_path))
        except RuntimeError:
            self._rendering.discard(rel_path)

    async def _render(self, rel_path):
        base_url = self._client.base_url
        try:
            path = await thr_preview.render_preview(self._client, base_url, rel_path)
        finally:
            self._rendering.discard(rel_path)
        if base_url != self._client.base_url:
            return  # table changed under us; drop stale result
        self._previews[rel_path] = path
        self._emit_preview_changed(rel_path)

    def _emit_preview_changed(self, rel_path):
        for row, pattern in enumerate(self._filtered_patterns):
            if pattern["name"] == rel_path:
                idx = self.index(row, 0)
                self.dataChanged.emit(idx, idx, [self.PreviewRole])
                break

    # -------------------------------------------------------------- fetching
    def _on_table_changed(self, _base_url):
        self._previews.clear()
        self._rendering.clear()
        self.refresh()

    @Slot()
    def refresh(self):
        try:
            asyncio.get_event_loop().create_task(self._fetch_patterns())
        except RuntimeError:
            logger.debug("No running loop yet; patterns will load once started")

    async def _fetch_patterns(self):
        if not self._client.base_url:
            self._apply_patterns([])
            return
        try:
            paths = await self._client.patterns()
        except Exception as exc:
            logger.warning(f"Failed to fetch patterns: {exc}")
            return
        patterns = []
        for p in paths:
            rel = str(p).lstrip("/")
            # /sand_patterns may return paths with or without a /patterns prefix
            if rel.startswith("patterns/"):
                rel = rel[len("patterns/"):]
            patterns.append({"name": rel, "path": rel})
        patterns.sort(key=lambda x: x["name"].lower())
        self._apply_patterns(patterns)

    def _apply_patterns(self, patterns):
        self.beginResetModel()
        self._patterns = patterns
        self._filtered_patterns = self._apply_filter(patterns, self._search_text)
        self.endResetModel()
        logger.info(f"Loaded {len(self._patterns)} patterns")

    # ---------------------------------------------------------------- filter
    @staticmethod
    def _apply_filter(patterns, search_text):
        if not search_text:
            return list(patterns)
        needle = search_text.lower()
        return [p for p in patterns if needle in p["name"].lower()]

    @Slot(str)
    def filter(self, search_text):
        self._search_text = search_text or ""
        self.beginResetModel()
        self._filtered_patterns = self._apply_filter(self._patterns, self._search_text)
        self.endResetModel()
