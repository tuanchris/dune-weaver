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
        self._previews = {}           # rel_path -> cached png path ("" = none)
        self._rendering = set()       # rel_paths with an in-flight render
        self._render_attempts = {}    # rel_path -> transient-failure count
        self._warm_task = None        # background cache-warmer task

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
        """Return a cached preview path, kicking off a render if needed.

        Runs on the GUI thread for every row the grid materializes, so it
        must not touch the disk: the on-disk cache is folded into
        ``self._previews`` in one scan per refresh (see ``_fetch_patterns``).
        """
        cached = self._previews.get(rel_path)
        if cached is not None:
            return cached
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

    # Transient fetch failures (timeouts, board busy) are retried with a
    # delay; only a real result — a PNG path or a definitive "" (pattern has
    # nothing to render) — is cached. Caching "" on a timeout used to leave
    # tiles on "No Preview" forever.
    _MAX_RENDER_ATTEMPTS = 3
    _RETRY_DELAY_S = 10

    async def _render(self, rel_path):
        base_url = self._client.base_url
        try:
            path = await thr_preview.render_preview(self._client, base_url, rel_path)
        finally:
            self._rendering.discard(rel_path)
        if base_url != self._client.base_url:
            return  # table changed under us; drop stale result
        if path is None:
            attempts = self._render_attempts.get(rel_path, 0) + 1
            self._render_attempts[rel_path] = attempts
            if attempts < self._MAX_RENDER_ATTEMPTS:
                await asyncio.sleep(self._RETRY_DELAY_S)
                if base_url == self._client.base_url:
                    self._schedule_render(rel_path)
            # else: leave uncached — scrolling back to the tile retries fresh
            else:
                self._render_attempts.pop(rel_path, None)
            return
        self._render_attempts.pop(rel_path, None)
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
        if self._warm_task is not None:
            self._warm_task.cancel()
            self._warm_task = None
        self._previews.clear()
        self._rendering.clear()
        self._render_attempts.clear()
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

        # Fold the on-disk preview cache into _previews with a single
        # directory scan, off the GUI thread — data() must never hit the disk.
        base_url = self._client.base_url
        index = await asyncio.to_thread(thr_preview.preview_index, base_url)
        if base_url != self._client.base_url:
            return  # table changed under us; drop stale result
        for pattern in patterns:
            rel = pattern["name"]
            if rel not in self._previews:
                on_disk = index.get(thr_preview.safe_name(rel))
                if on_disk:
                    self._previews[rel] = on_disk

        self._apply_patterns(patterns)
        self._start_warmer()

    # ------------------------------------------------------------ cache warm
    def _start_warmer(self):
        """Render the still-missing previews in the background, one at a time.

        Without this, a fresh install shows placeholder dishes for the whole
        first pass over the library. Only patterns with a local .thr are
        warmed (no board I/O); board-only patterns stay lazy. Visible tiles
        still render on demand and win the CPU cap's other slot.
        """
        if self._warm_task is not None:
            self._warm_task.cancel()
            self._warm_task = None
        try:
            self._warm_task = asyncio.get_event_loop().create_task(self._warm_previews())
        except RuntimeError:
            pass

    async def _warm_previews(self):
        base_url = self._client.base_url
        warmed = 0
        for pattern in list(self._patterns):
            if base_url != self._client.base_url:
                return  # table changed; the new fetch starts a fresh warmer
            rel = pattern["name"]
            if rel in self._previews or rel in self._rendering:
                continue
            if not await asyncio.to_thread(thr_preview.has_local_source, rel):
                continue
            self._rendering.add(rel)
            await self._render(rel)
            warmed += 1
            # Breathe between renders so the warmer never monopolizes the pool.
            await asyncio.sleep(0.1)
        if warmed:
            logger.info(f"Preview cache warmed: {warmed} patterns rendered")

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
