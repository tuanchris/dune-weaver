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
import requests

logger = logging.getLogger(__name__)


class FluidNCClient:
    """Stateless HTTP handle to one FluidNC sand-table board."""

    def __init__(self, base_url: str, timeout: float = 10.0):
        # base_url like "http://192.168.68.160"
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Mirrors the BaseConnection contract main.py relies on (is_connected/close).
        self._connected = False

    # -- low-level -----------------------------------------------------------

    def _get(self, path: str, params: dict | None = None, timeout: float | None = None):
        r = requests.get(self.base_url + path, params=params, timeout=timeout or self.timeout)
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
        except Exception as e:
            logger.debug(f"Board unreachable at {self.base_url}: {e}")
            self._connected = False
        return self._connected

    # -- reads ---------------------------------------------------------------

    def get_status(self) -> dict:
        """The board's /sand_status object (schema in API.md)."""
        return self._get("/sand_status", timeout=3.0).json()

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
            r = requests.get(self.base_url + "/sd" + sd_path, stream=True, timeout=5.0)
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
