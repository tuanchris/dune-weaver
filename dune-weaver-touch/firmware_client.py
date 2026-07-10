"""Async HTTP client for the Dune Weaver FluidNC firmware.

The table is a headless ESP32 (FluidNC ``sandtable`` build). It exposes a
stateless HTTP/JSON API (see the firmware's ``API.md``): status is *polled*
from ``/sand_status``, actions go out as ``$...`` commands via ``/command`` and
the dedicated ``/sand_*`` routes, and pattern/playlist files are fetched from
``/sd/...``.

This module is the single place that knows how to talk to the board. It is a
process-wide ``QObject`` singleton so the ``Backend`` controller and the
``PatternModel`` / ``PlaylistModel`` list models all share one aiohttp session
and one notion of "which table are we pointed at".
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional
from urllib.parse import quote

import aiohttp
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger("DuneWeaver.Firmware")

# Firmware LED capability is a fixed catalogue of named effects/palettes
# (API.md -> "LEDs"). The QML LED page works in terms of integer ids, so we
# expose these lists and map id <-> name by index.
LED_EFFECTS = [
    "off", "static", "rainbow", "breathe", "colorloop", "theater", "scan",
    "running", "sine", "gradient", "sinelon", "twinkle", "sparkle", "fire",
    "candle", "meteor", "bouncing", "wipe", "dualscan", "juggle", "multicomet",
    "glitter", "dissolve", "ripple", "drip", "lightning", "fireworks", "plasma",
    "heartbeat", "strobe", "police", "chase", "railway", "pacifica", "aurora",
    "pride", "colorwaves", "bpm", "ball",
]
LED_PALETTES = [
    "rainbow", "ocean", "lava", "forest", "party", "cloud", "heat", "sunset",
]

# Pattern "pre-execution" clear modes as used by the touch UI mapped to the
# firmware's clear= modes ($Sand/Run ... clear=<mode>). The touch UI speaks in
# center/perimeter terms; the firmware ships clear-from-in / clear-from-out
# templates.
CLEAR_MODE_MAP = {
    "adaptive": "adaptive",
    "clear_center": "in",      # start at the center, clear outward
    "clear_perimeter": "out",  # start at the perimeter, clear inward
    "none": "none",
    # pass-through for firmware-native names so callers may use them directly
    "in": "in", "out": "out", "sideway": "sideway", "random": "random",
}

DEFAULT_HTTP_TIMEOUT = 6      # seconds, for normal requests
STATUS_TIMEOUT = 3           # seconds, for the ~1 Hz status poll


def _raise_file_error(status: int, body) -> None:
    """Raise a helpful error from a file-op JSON body on HTTP failure."""
    if status < 400:
        return
    detail = ""
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            detail = err.get("message", "")
        detail = detail or body.get("status", "")
    raise RuntimeError(detail or f"HTTP {status}")


def normalize_base_url(value: str) -> str:
    """Turn a user/mDNS supplied host into a ``http://host[:port]`` base URL."""
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = "http://" + value
    return value


class FirmwareClient(QObject):
    """Process-wide async client for one FluidNC sand table."""

    # Emitted whenever the target table changes (empty string = no table).
    baseUrlChanged = Signal(str)
    # Emitted when reachability changes based on request success/failure.
    reachabilityChanged = Signal(bool)

    _instance: Optional["FirmwareClient"] = None

    @classmethod
    def instance(cls) -> "FirmwareClient":
        if cls._instance is None:
            cls._instance = FirmwareClient()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._base_url = ""
        self._session: Optional[aiohttp.ClientSession] = None
        self._reachable = False

    # ------------------------------------------------------------------ target
    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def reachable(self) -> bool:
        return self._reachable

    def set_base_url(self, value: str) -> None:
        normalized = normalize_base_url(value)
        if normalized == self._base_url:
            return
        logger.info(f"Target table set to: {normalized or '(none)'}")
        self._base_url = normalized
        self._set_reachable(False)
        self.baseUrlChanged.emit(self._base_url)

    def _set_reachable(self, value: bool) -> None:
        if value != self._reachable:
            self._reachable = value
            self.reachabilityChanged.emit(value)

    # ----------------------------------------------------------------- session
    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(ssl=False, limit=8)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------- HTTP helpers
    async def _get(self, path: str, *, timeout: float = DEFAULT_HTTP_TIMEOUT):
        """GET ``path`` (leading-slash relative). Returns the aiohttp response
        inside a context manager caller. Raises on transport error."""
        if not self._base_url:
            raise RuntimeError("No table selected")
        session = await self._ensure_session()
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        return session.get(f"{self._base_url}{path}", timeout=client_timeout)

    async def get_json(self, path: str, *, timeout: float = DEFAULT_HTTP_TIMEOUT):
        async with await self._get(path, timeout=timeout) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
            self._set_reachable(True)
            return data

    async def get_text(self, path: str, *, timeout: float = DEFAULT_HTTP_TIMEOUT) -> str:
        async with await self._get(path, timeout=timeout) as resp:
            resp.raise_for_status()
            text = await resp.text()
            self._set_reachable(True)
            return text

    async def get_bytes(self, path: str, *, timeout: float = DEFAULT_HTTP_TIMEOUT) -> bytes:
        async with await self._get(path, timeout=timeout) as resp:
            resp.raise_for_status()
            data = await resp.read()
            self._set_reachable(True)
            return data

    # -------------------------------------------------------------- status/read
    async def status(self) -> dict:
        """Poll ``/sand_status`` (fast, works during motion)."""
        return await self.get_json("/sand_status", timeout=STATUS_TIMEOUT)

    async def patterns(self) -> list:
        """``/sand_patterns`` -> list of ``.thr`` paths relative to /patterns."""
        data = await self.get_json("/sand_patterns")
        return data if isinstance(data, list) else []

    async def playlists(self) -> list:
        """``/sand_playlists`` -> list of ``.txt`` file names."""
        data = await self.get_json("/sand_playlists")
        return data if isinstance(data, list) else []

    async def settings(self) -> dict:
        """``/sand_settings`` -> flat dict of setting name -> string value."""
        data = await self.get_json("/sand_settings")
        return data if isinstance(data, dict) else {}

    async def fetch_sd_file(self, sd_path: str) -> bytes:
        """Fetch a file from the SD card, e.g. ``/patterns/star.thr``."""
        sd_path = "/" + sd_path.lstrip("/")
        return await self.get_bytes(f"/sd{sd_path}")

    # ------------------------------------------------------------------ actions
    async def command(self, cmd: str, *, timeout: float = DEFAULT_HTTP_TIMEOUT) -> str:
        """Fire a ``$...`` command via ``/command?plain=`` (fire-and-forget).

        Output routing over ``/command`` is racy for anything but ``$/`` reads,
        so callers that need a value should poll a ``/sand_*`` route instead.
        """
        return await self.get_text(f"/command?plain={quote(cmd)}", timeout=timeout)

    async def run_pattern(self, rel_path: str, clear: str = "none") -> None:
        """Run ``/patterns/<rel_path>`` with an optional pre-execution clear."""
        path = "/patterns/" + rel_path.lstrip("/")
        mode = CLEAR_MODE_MAP.get(clear, "none")
        if mode == "none":
            await self.command(f"$SD/Run={path}")
        else:
            await self.command(f"$Sand/Run={path} clear={mode}")

    async def run_playlist(self, name: str, *, pause_time=None, clear_pattern=None,
                           run_mode=None, shuffle=None) -> None:
        """Apply the run parameters (NVS) then start the playlist."""
        if run_mode in ("single", "loop"):
            await self.command(f"$Playlist/Mode={run_mode}")
        if shuffle is not None:
            await self.command(f"$Playlist/Shuffle={'ON' if shuffle else 'OFF'}")
        if pause_time is not None:
            await self.command(f"$Playlist/PauseTime={int(pause_time)}")
        if clear_pattern is not None:
            mode = CLEAR_MODE_MAP.get(clear_pattern, clear_pattern)
            await self.command(f"$Playlist/ClearPattern={mode}")
        await self.command(f"$Playlist/Run={name}")

    async def playlist_stop(self) -> None:
        await self.command("$Playlist/Stop")

    async def playlist_skip(self) -> None:
        await self.command("$Playlist/Skip")

    async def stop(self) -> None:
        """Stop the whole sequence (clear + pattern + playlist)."""
        await self.get_text("/sand_stop")

    async def pause(self) -> None:
        await self.get_text("/sand_pause")

    async def resume(self) -> None:
        await self.get_text("/sand_resume")

    async def home(self) -> None:
        # Homing can take a while; give it room. Runs in the main loop (safe).
        await self.get_text("/sand_home", timeout=95)

    async def goto(self, *, theta=None, rho=None) -> None:
        params = []
        if theta is not None:
            params.append(f"theta={theta}")
        if rho is not None:
            params.append(f"rho={rho}")
        await self.get_text("/sand_goto?" + "&".join(params), timeout=95)

    async def set_feed_mm(self, mm: int) -> None:
        """Set the base feed rate (motor mm/min); works mid-pattern."""
        await self.get_text(f"/sand_feed?mm={int(mm)}")

    async def set_led(self, **kwargs) -> None:
        """Live LED control via ``/sand_led?...`` (applies immediately)."""
        params = "&".join(f"{k}={quote(str(v))}" for k, v in kwargs.items() if v is not None)
        await self.get_text(f"/sand_led?{params}")

    async def set_autostart(self, name: str) -> None:
        """Set (or clear, with empty name) the boot auto-play playlist."""
        await self.command(f"$Playlist/Autostart={name}")

    async def reboot(self) -> None:
        await self.command("$Bye")

    async def sync_time(self, epoch: int) -> None:
        await self.get_text(f"/sand_time?epoch={int(epoch)}")

    # --------------------------------------------------------------- file ops
    async def upload_file(self, name: str, data: bytes, path: str = "/patterns") -> dict:
        """Upload ``data`` as ``<path>/<name>`` (multipart, firmware contract)."""
        if not self._base_url:
            raise RuntimeError("No table selected")
        session = await self._ensure_session()
        form = aiohttp.FormData()
        form.add_field(f"{name}S", str(len(data)))
        form.add_field(name, data, filename=name,
                       content_type="application/octet-stream")
        url = f"{self._base_url}/upload?path={quote(path)}"
        timeout = aiohttp.ClientTimeout(total=60)
        async with session.post(url, data=form, timeout=timeout) as resp:
            body = await resp.json(content_type=None)
            self._set_reachable(True)
            _raise_file_error(resp.status, body)
            return body

    async def _file_action(self, action: str, filename: str, path: str, **extra) -> dict:
        if not self._base_url:
            raise RuntimeError("No table selected")
        session = await self._ensure_session()
        params = {"action": action, "filename": filename, "path": path, "dontlist": "yes"}
        params.update(extra)
        query = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
        url = f"{self._base_url}/upload?{query}"
        timeout = aiohttp.ClientTimeout(total=DEFAULT_HTTP_TIMEOUT)
        async with session.get(url, timeout=timeout) as resp:
            body = await resp.json(content_type=None)
            self._set_reachable(True)
            _raise_file_error(resp.status, body)
            return body

    async def delete_file(self, filename: str, path: str = "/playlists") -> dict:
        return await self._file_action("delete", filename, path)

    async def create_dir(self, filename: str, path: str = "/") -> dict:
        return await self._file_action("createdir", filename, path)
