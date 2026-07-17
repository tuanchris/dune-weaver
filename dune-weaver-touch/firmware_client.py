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
import random
import socket
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
# 503 low-memory load-shedding retry, mirroring the backend's FluidNCClient.
_RETRY_503_ATTEMPTS = 3       # total tries (1 initial + 2 retries)
_RETRY_503_BASE = 0.3         # seconds; base for exponential backoff + jitter
# The board's web server serializes requests, so a request behind a big file
# transfer can legitimately time out once and succeed a moment later.
_TRANSIENT_RETRY_DELAY = 0.5  # seconds between transient-error retries
# Status poll budget. The board's web server serializes requests, so a status
# read legitimately waits several seconds behind a file transfer — a tight
# timeout here makes a busy board look dead.
STATUS_TIMEOUT = 5           # seconds, for the ~1 Hz status poll


def friendly_error(exc: BaseException) -> str:
    """Human-readable message for a request failure.

    ``str(asyncio.TimeoutError())`` is an EMPTY string — surfacing raw
    exceptions produced blank error dialogs. Every user-facing error goes
    through here instead.
    """
    if isinstance(exc, asyncio.TimeoutError):
        return "The table didn't respond in time — it may be busy. Try again."
    if isinstance(exc, aiohttp.ClientResponseError) and exc.status == 401:
        return "The table rejected the password. Set it under Table connection."
    if isinstance(exc, (aiohttp.ClientConnectionError, aiohttp.ClientError)):
        return "Can't reach the table. Check that it's powered on and on your network."
    return str(exc) or type(exc).__name__


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


def posix_tz() -> Optional[str]:
    """POSIX TZ rule for the system zone (from the TZif v2+ footer line).

    Same derivation as the backend's board_settings.posix_tz(): modern TZif
    files end with a footer holding exactly the rule string the firmware's
    $Time/Zone wants (e.g. 'EST5EDT,M3.2.0,M11.1.0'). None if unreadable.
    """
    try:
        with open("/etc/localtime", "rb") as f:
            data = f.read()
        if not data.startswith(b"TZif"):
            return None
        end = data.rfind(b"\n")
        if end <= 0:
            return None
        begin = data.rfind(b"\n", 0, end)
        footer = data[begin + 1:end].decode("ascii").strip()
        return footer or None
    except Exception as exc:
        logger.debug(f"Could not derive POSIX tz: {exc}")
        return None


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
        # $Sand/Password key (fw >= v0.1.11), sent as X-Sand-Key on every
        # request — same contract as the backend's FluidNCClient.
        self._api_key: Optional[str] = None
        # True when the board rejected us with 401 (locked, wrong/missing key).
        self.locked = False

    def set_api_key(self, key: Optional[str]) -> None:
        self._api_key = key or None
        self.locked = False

    def _headers(self) -> dict:
        return {"X-Sand-Key": self._api_key} if self._api_key else {}

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
            # IPv4 only: the boards publish no AAAA record over mDNS, and a
            # dual-stack getaddrinfo stalls ~5s waiting for it (longer than the
            # 3s status timeout, so every poll would die in name resolution).
            connector = aiohttp.TCPConnector(
                ssl=False, limit=8, family=socket.AF_INET, ttl_dns_cache=300
            )
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------- HTTP helpers
    async def _fetch(self, path: str, parse: str, *, timeout: float,
                     transient_retries: int = 1):
        """GET ``path`` and return the parsed body ("json" | "text" | "bytes").

        Retries the firmware's ``503 busy: low memory`` load-shedding with
        exponential backoff, like the backend's FluidNCClient (the board sheds
        every route except the status/stop/pause/resume lifeline when free
        heap drops below ~10 KB; these resolve in a few seconds). Tracks 401s
        in ``self.locked`` so the UI can prompt for the table password.

        ``transient_retries`` additionally retries timeouts and connection
        errors (the board's serialized web server queues requests behind file
        transfers, so a one-off timeout is normal). Callers whose requests are
        NOT safe to re-send (``$...`` commands) pass 0.
        """
        if not self._base_url:
            raise RuntimeError("No table selected")
        session = await self._ensure_session()
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        url = f"{self._base_url}{path}"
        attempt_503 = 0
        transient_left = transient_retries
        while True:
            try:
                async with session.get(url, timeout=client_timeout,
                                       headers=self._headers()) as resp:
                    if resp.status == 503 and attempt_503 < _RETRY_503_ATTEMPTS - 1:
                        attempt_503 += 1
                        delay = _RETRY_503_BASE * (2 ** attempt_503) + random.uniform(0, _RETRY_503_BASE)
                        logger.debug(f"Board 503 (low memory) on {path}; retrying in {delay:.2f}s")
                        await asyncio.sleep(delay)
                        continue
                    self.locked = resp.status == 401
                    resp.raise_for_status()
                    if parse == "json":
                        data = await resp.json(content_type=None)
                    elif parse == "text":
                        data = await resp.text()
                    else:
                        data = await resp.read()
                    self._set_reachable(True)
                    return data
            except (asyncio.TimeoutError, aiohttp.ClientConnectionError) as exc:
                if transient_left <= 0:
                    raise
                transient_left -= 1
                logger.debug(f"Transient failure on {path} ({exc!r}); retrying")
                await asyncio.sleep(_TRANSIENT_RETRY_DELAY)

    async def get_json(self, path: str, *, timeout: float = DEFAULT_HTTP_TIMEOUT,
                       transient_retries: int = 1):
        return await self._fetch(path, "json", timeout=timeout,
                                 transient_retries=transient_retries)

    async def get_text(self, path: str, *, timeout: float = DEFAULT_HTTP_TIMEOUT,
                       transient_retries: int = 1) -> str:
        return await self._fetch(path, "text", timeout=timeout,
                                 transient_retries=transient_retries)

    async def get_bytes(self, path: str, *, timeout: float = DEFAULT_HTTP_TIMEOUT,
                        transient_retries: int = 1) -> bytes:
        return await self._fetch(path, "bytes", timeout=timeout,
                                 transient_retries=transient_retries)

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

    async def fetch_sd_file(self, sd_path: str, *, timeout: float = 45) -> bytes:
        """Fetch a file from the SD card, e.g. ``/patterns/star.thr``.

        Default timeout is generous: the board serves large .thr files slowly
        (measured up to ~26s for 500KB when it is busy), and the default 6s
        budget made every big pattern's preview fetch fail.
        """
        sd_path = "/" + sd_path.lstrip("/")
        return await self.get_bytes(f"/sd{sd_path}", timeout=timeout)

    # ------------------------------------------------------------------ actions
    async def command(self, cmd: str, *, timeout: float = DEFAULT_HTTP_TIMEOUT) -> str:
        """Fire a ``$...`` command via ``/command?plain=`` (fire-and-forget).

        Output routing over ``/command`` is racy for anything but ``$/`` reads,
        so callers that need a value should poll a ``/sand_*`` route instead.
        No transient retry: a timed-out command may still execute on the board
        once its queue drains, and re-sending e.g. ``$Playlist/Run`` or ``$Bye``
        would double-fire it.
        """
        return await self.get_text(f"/command?plain={quote(cmd)}",
                                   timeout=timeout, transient_retries=0)

    async def run_pattern(self, rel_path: str, clear: str = "none") -> None:
        """Run ``/patterns/<rel_path>`` with an optional pre-execution clear."""
        path = "/patterns/" + rel_path.lstrip("/")
        mode = CLEAR_MODE_MAP.get(clear, "none")
        if mode == "none":
            await self.command(f"$SD/Run={path}")
        else:
            await self.command(f"$Sand/Run={path} clear={mode}")

    async def _wait_for_idle(self, timeout_s: float) -> bool:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_s
        while loop.time() < deadline:
            try:
                st = await self.status()
                state = (st.get("state") or "").split(":", 1)[0]
                if state == "Idle" and not st.get("running"):
                    return True
            except Exception as exc:
                logger.debug(f"Idle wait poll failed: {exc}")
            await asyncio.sleep(0.5)
        return False

    async def run_playlist(self, name: str, *, pause_time=None, clear_pattern=None,
                           run_mode=None, shuffle=None) -> None:
        """Apply the run parameters (NVS) then start the playlist.

        NVS writes are idle-gated on the firmware (rejected mid-motion), so a
        run-while-running stops the board first — same as the backend's
        execution.start_playlist.
        """
        try:
            st = await self.status()
        except Exception:
            st = None
        state = ((st or {}).get("state") or "").split(":", 1)[0]
        if st and (st.get("running") or state not in ("Idle", "Alarm")):
            await self.stop()
            if not await self._wait_for_idle(15.0):
                raise RuntimeError("Table is busy and did not stop in time")
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

    async def sync_time(self, epoch: int, tz: Optional[str] = None) -> None:
        """Push the wall clock and (optionally) a POSIX timezone rule.

        The tz matters: board-side quiet-hours/autostart schedules run on the
        board's local time. The backend always sends both; so do we.
        """
        query = f"epoch={int(epoch)}"
        if tz:
            query += f"&tz={quote(tz)}"
        await self.get_text(f"/sand_time?{query}")

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
        async with session.post(url, data=form, timeout=timeout,
                                headers=self._headers()) as resp:
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
        async with session.get(url, timeout=timeout,
                               headers=self._headers()) as resp:
            body = await resp.json(content_type=None)
            self._set_reachable(True)
            _raise_file_error(resp.status, body)
            return body

    async def delete_file(self, filename: str, path: str = "/playlists") -> dict:
        return await self._file_action("delete", filename, path)

    async def create_dir(self, filename: str, path: str = "/") -> dict:
        return await self._file_action("createdir", filename, path)
