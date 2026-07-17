"""
FluidNC HTTP client — the backend's transport to the headless board firmware.

The board runs a FluidNC fork that owns kinematics, `.thr` playback, progress
reporting and homing, and exposes an HTTP API (contract: the firmware repo's
API.md). This client is the single seam the rest of the backend uses to talk to
hardware; it replaces the old serial / websocket GRBL transport.

Design notes:
  - Calls are synchronous (``requests``). Callers that need async wrap them in
    ``asyncio.to_thread`` (the codebase already does this for blocking I/O).
  - "Actions" are fire-and-forget: the board applies them and the caller
    confirms the effect by polling ``get_status()``. This matches the firmware's
    own model (API.md: use ``/command`` + ``/sand_*`` to act, poll to confirm).
  - It is multi-client-safe: status/listing reads and action routes are stateless
    HTTP and keep working during playback.
"""

import logging
import random
import socket
import time
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# The board's single-threaded web server answers ``503 busy: low memory`` for
# every route except the status/stop/pause/resume lifeline when free heap drops
# below ~10 KB (firmware API.md, load-shedding). These transient sheds — often
# triggered by an app's launch-burst of concurrent reads — resolve in a few
# seconds, so idempotent GETs back off and retry rather than failing hard.
_RETRY_503_ATTEMPTS = 3      # total tries (1 initial + 2 retries)
_RETRY_503_BASE = 0.3        # seconds; base for exponential backoff + jitter


def _pin_ipv4(base_url: str) -> str:
    """Rewrite a hostname base URL to its numeric IPv4 address.

    The boards publish no AAAA record over mDNS, and a dual-stack getaddrinfo
    for a ``.local`` name stalls ~5s waiting for the IPv6 answer — longer than
    the 3s status timeout, so every poll would die in name resolution. Resolve
    the A record once here (milliseconds) and pin it; clients are rebuilt on
    every connect/relocate, so a DHCP move is still handled by the watchdog.
    Unresolvable hosts pass through unchanged for reachable() to report.
    """
    parsed = urlparse(base_url)
    host = parsed.hostname or ""
    if not host:
        return base_url
    try:
        socket.inet_aton(host)
        return base_url  # already a numeric IPv4 address
    except OSError:
        pass
    try:
        info = socket.getaddrinfo(host, parsed.port or 80,
                                  socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return base_url
    address = info[0][4][0]
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{address}{port}"


class FluidNCClient:
    """Stateless HTTP handle to one FluidNC sand-table board."""

    def __init__(self, base_url: str, timeout: float = 10.0, api_key: str | None = None):
        # base_url like "http://192.168.68.160"
        self.base_url = _pin_ipv4(base_url.rstrip("/"))
        self.timeout = timeout
        # $Sand/Password key (fw >= v0.1.11), sent as X-Sand-Key on every request.
        self.api_key = api_key or None
        # Mirrors the BaseConnection contract main.py relies on (is_connected/close).
        self._connected = False
        # True when the board rejected us with 401 (locked, wrong/missing key).
        self.locked = False

    # -- low-level -----------------------------------------------------------

    def _headers(self) -> dict:
        return {"X-Sand-Key": self.api_key} if self.api_key else {}

    def _send_with_retry(self, method: str, url: str, **kwargs):
        """Issue an HTTP request, retrying on the firmware's ``503 low memory``.

        Only used for idempotent GETs (never for uploads/OTA/wifi writes, which
        are non-retryable). Backs off with exponential + jittered delay; the
        final 503 is returned to the caller like any other response.
        """
        send = getattr(requests, method.lower())  # requests.get / requests.post
        for attempt in range(_RETRY_503_ATTEMPTS):
            r = send(url, **kwargs)
            if r.status_code != 503 or attempt == _RETRY_503_ATTEMPTS - 1:
                return r
            delay = _RETRY_503_BASE * (2 ** attempt) + random.uniform(0, _RETRY_503_BASE)
            logger.debug(
                f"Board 503 (low memory) on {url}; retry {attempt + 1}/"
                f"{_RETRY_503_ATTEMPTS - 1} in {delay:.2f}s")
            time.sleep(delay)
        return r  # unreachable, but keeps type-checkers happy

    def _get(self, path: str, params: dict | None = None, timeout: float | None = None):
        r = self._send_with_retry("GET", self.base_url + path, params=params,
                                  timeout=timeout or self.timeout, headers=self._headers())
        if r.status_code == 401:
            self.locked = True
        r.raise_for_status()
        return r

    # -- connection lifecycle (BaseConnection-compatible) --------------------

    def is_connected(self) -> bool:
        return self._connected

    def close(self) -> None:
        self._connected = False

    def reachable(self) -> bool:
        """True if the board answers a status read. Also updates is_connected()."""
        try:
            self._get("/sand_status", timeout=3.0)
            self._connected = True
            self.locked = False
        except Exception as e:
            logger.debug(f"Board unreachable at {self.base_url}: {e}")
            self._connected = False
        return self._connected

    # -- API password ($Sand/Password, fw >= v0.1.11) --------------------------

    def test_key(self, key: str | None) -> bool:
        """Probe whether `key` unlocks the board (a cheap $G through /command).

        True = accepted (or the board isn't locked); False = 401 rejected.
        Other errors (unreachable, etc.) propagate.
        """
        headers = {"X-Sand-Key": key} if key else {}
        r = self._send_with_retry("GET", self.base_url + "/command", params={"plain": "$G"},
                                  timeout=6.0, headers=headers)
        if r.status_code == 401:
            return False
        r.raise_for_status()
        return True

    def set_password(self, password: str) -> str:
        """Set (non-empty) or remove (empty) the board's API password."""
        return self.run_command(f"$Sand/Password={password or ''}")

    # -- reads ---------------------------------------------------------------

    def get_status(self) -> dict:
        """The board's /sand_status object (schema in API.md)."""
        return self._get("/sand_status", timeout=3.0).json()

    def get_bootlog(self) -> str:
        """Plain-text boot log ($SS startup log). After a panic reset it still
        holds the *previous* boot's log — the on-device crash breadcrumb."""
        return self._get("/sand_bootlog", timeout=6.0).text

    def get_coredump(self) -> dict:
        """JSON crash report from the coredump flash partition, written on any
        panic (incl. task-WDT hang). {present, task, pc, backtrace, ...}."""
        return self._get("/sand_coredump", timeout=6.0).json()

    def erase_coredump(self) -> None:
        """Clear the stored coredump (?erase=1)."""
        self._get("/sand_coredump", params={"erase": "1"}, timeout=6.0)

    def get_settings(self) -> dict:
        """Flat string map of board settings (keys like 'Sand/HomingMode')."""
        return self._get("/sand_settings").json()

    def list_patterns(self) -> list:
        return self._get("/sand_patterns").json()

    def list_playlists(self) -> list:
        return self._get("/sand_playlists").json()

    def fetch_file(self, sd_path: str) -> bytes:
        """Fetch raw SD file bytes, e.g. fetch_file('/patterns/star.thr')."""
        return self._get("/sd" + sd_path, timeout=15.0).content

    def file_exists(self, sd_path: str) -> bool:
        try:
            r = self._send_with_retry("GET", self.base_url + "/sd" + sd_path, stream=True,
                                      timeout=5.0, headers=self._headers())
            ok = r.status_code == 200
            r.close()
            return ok
        except Exception:
            return False

    # -- clock ----------------------------------------------------------------

    def get_time(self) -> dict:
        """The board's wall clock: {epoch, synced, local, tz}."""
        return self._get("/sand_time").json()

    def set_time(self, epoch: int | None = None, tz: str | None = None) -> dict:
        """Push the wall clock (unix epoch) and/or a POSIX timezone to the board."""
        params: dict = {}
        if epoch is not None:
            params["epoch"] = int(epoch)
        if tz is not None:
            params["tz"] = tz
        return self._get("/sand_time", params=params).json()

    # -- commands / actions --------------------------------------------------

    def run_command(self, plain: str) -> str:
        """Fire a FluidNC command via the /command gateway (fire-and-forget)."""
        return self._get("/command", params={"plain": plain}).text

    def set_setting(self, key: str, value) -> str:
        """Write one NVS-persisted board setting, e.g. set_setting('Playlist/Autostart', 'evening').

        The command response contains 'error' on rejection (e.g. idle-gated
        settings while running); raise so callers can surface it.
        """
        resp = self.run_command(f"${key}={value}")
        if "error" in resp.lower():
            raise RuntimeError(f"Board rejected ${key}={value}: {resp.strip()}")
        return resp

    def run_pattern(self, sd_path: str, clear: str | None = None) -> None:
        """
        Start a pattern. With a clear mode, uses $Sand/Run (which sequences
        clear->pattern and aborts any running job first); otherwise $SD/Run.
        Asynchronous — poll get_status() for progress/completion.
        """
        if clear and clear != "none":
            self.run_command(f"$Sand/Run={sd_path} clear={clear}")
        else:
            self.run_command(f"$SD/Run={sd_path}")

    def stop(self) -> str:
        return self._get("/sand_stop").text

    def pause(self) -> str:
        return self._get("/sand_pause").text

    def resume(self) -> str:
        return self._get("/sand_resume").text

    def skip(self) -> str:
        return self.run_command("$Playlist/Skip")

    def home(self) -> str:
        """Home honoring the board's $Sand/HomingMode; safe over HTTP."""
        return self._get("/sand_home").text

    def set_feed(self, mm: int | None = None, pct: int | None = None, d: str | None = None) -> str:
        """Set base feed (mm/min), an override percentage, or coarse up/down/reset."""
        params: dict = {}
        if mm is not None:
            params["mm"] = int(mm)
        if pct is not None:
            params["pct"] = int(pct)
        if d is not None:
            params["d"] = d
        return self._get("/sand_feed", params=params).text

    def goto(self, theta: float | None = None, rho: float | None = None) -> str:
        """Jog to an absolute theta (radians) and/or rho (0..1). Requires Idle."""
        params: dict = {}
        if theta is not None:
            params["theta"] = theta
        if rho is not None:
            params["rho"] = rho
        return self._get("/sand_goto", params=params).text

    def set_led(self, **keys) -> str:
        """Live LED control via /sand_led (keys: effect/palette/color/brightness/...)."""
        return self._get("/sand_led", params=keys).text

    def set_homing_mode(self, mode: str) -> str:
        return self.run_command(f"$Sand/HomingMode={mode}")  # sensor | crash

    def set_theta_offset(self, degrees: float) -> str:
        return self.run_command(f"$Sand/ThetaOffset={degrees}")

    def soft_reset(self) -> str:
        """Reboot the controller (loses position) — host re-homes afterward."""
        return self.run_command("$Bye")

    # -- board Wi-Fi (fw >= v0.1.8) -------------------------------------------

    def wifi_status(self) -> dict:
        """{mode: sta|fallback|standalone, sta_ssid, ap_ssid, fail}. Older
        firmware 404s (propagates as HTTPError)."""
        return self._get("/wifi_status", timeout=6.0).json()

    def wifi_scan(self, rescan: bool = False) -> dict:
        """{status:'scanning'} while the async scan runs; then {status:'ok', aps:[...]}"""
        return self._get("/wifi_scan", params={"rescan": "1"} if rescan else None,
                         timeout=8.0).json()

    def _post_wifi(self, path: str, form: dict | None = None) -> dict:
        """Wi-Fi writes are form-urlencoded POSTs answering {status, reboot, message?}.
        'busy' = idle-gated (boot auto-home / running pattern); on 'ok' with
        reboot the table restarts ~0.5s later and the link drops."""
        r = requests.post(self.base_url + path, data=form or {}, timeout=10.0,
                          headers=self._headers())
        return r.json()

    def wifi_save(self, ssid: str, password: str) -> dict:
        return self._post_wifi("/wifi_save", {"ssid": ssid, "password": password})

    def wifi_standalone(self) -> dict:
        return self._post_wifi("/wifi_standalone")

    # -- firmware OTA (/updatefw) ---------------------------------------------

    def update_probe(self) -> dict:
        """Is the board willing to take an OTA right now? Returns the parsed
        JSON on any HTTP status ('ready'/'busy'; legacy firmware returns an
        older shape = too old for OTA)."""
        r = self._send_with_retry("GET", self.base_url + "/updatefw", timeout=6.0,
                                  headers=self._headers())
        return r.json()

    def upload_firmware(self, image: bytes) -> dict:
        """Flash an app image over OTA. Same multipart shape as /upload
        (a 'firmware.binS' size field + the binary part). On 'ok' the board
        reboots ~1s later; poll get_status() until it's back."""
        r = requests.post(
            self.base_url + "/updatefw",
            data={"firmware.binS": str(len(image))},
            files={"firmware.bin": ("firmware.bin", image, "application/octet-stream")},
            timeout=180.0,
            headers=self._headers(),
        )
        return r.json()

    # -- SD file management (ESP3D /upload protocol) -------------------------

    def upload_file(self, sd_path: str, data: bytes, directory: str) -> dict:
        """
        Upload bytes to an SD path. Per the firmware's ESP3D handler the multipart
        file part is named by the full SD path, plus a '<path>S' size field; the
        ?path= query selects the directory used for the post-upload listing.
        """
        form = {f"{sd_path}S": str(len(data))}
        files = {sd_path: (sd_path, data, "application/octet-stream")}
        r = requests.post(
            self.base_url + "/upload",
            params={"path": directory},
            data=form,
            files=files,
            timeout=30.0,
            headers=self._headers(),
        )
        r.raise_for_status()
        return r.json() if r.text else {}

    def delete_file(self, directory: str, filename: str) -> dict:
        return self._get(
            "/upload",
            params={"path": directory, "action": "delete", "filename": filename, "dontlist": "yes"},
        ).json()

    def rename_file(self, directory: str, old: str, new: str) -> dict:
        return self._get(
            "/upload",
            params={"path": directory, "action": "rename", "filename": old, "newname": new, "dontlist": "yes"},
        ).json()
