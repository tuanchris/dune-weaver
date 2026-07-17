"""mDNS (zeroconf) advertisement and discovery of Dune Weaver tables.

Each backend advertises itself as a `_dune-weaver._tcp.local.` service and
browses for peers on the LAN. Discovered peers are exposed to the frontend
via GET /api/discovered-tables so users never have to type IP addresses.

Discovery is best-effort: if the zeroconf package is missing or the network
doesn't support multicast, the app runs normally without it (graceful
degradation, same pattern as the optional LED libraries).
"""

import asyncio
import logging
import re
import socket
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

SERVICE_TYPE = "_dune-weaver._tcp.local."
# FluidNC boards advertise `_http._tcp` with TXT `api=sandtable/1`,
# `model=dune-weaver` (same records dune-weaver-mobile browses for).
HTTP_SERVICE_TYPE = "_http._tcp.local."
RESOLVE_TIMEOUT_MS = 3000

try:
    from zeroconf import IPVersion, ServiceInfo, ServiceStateChange
    from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf
    ZEROCONF_AVAILABLE = True
except ImportError:
    ZEROCONF_AVAILABLE = False


def _get_local_ip() -> Optional[str]:
    """Best-effort LAN IP detection (no packets are actually sent)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def _decode_properties(properties: Dict) -> Dict[str, str]:
    """Zeroconf TXT records arrive as bytes; decode keys/values to str."""
    decoded = {}
    for key, value in (properties or {}).items():
        if isinstance(key, bytes):
            key = key.decode("utf-8", errors="replace")
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        if value is not None:
            decoded[key] = value
    return decoded


def service_info_to_table(info) -> Optional[dict]:
    """Convert a resolved ServiceInfo into a table dict for the API.

    Returns None if the service lacks the fields needed to reach it
    (an address, a port, and a table id in its TXT records).
    """
    props = _decode_properties(info.properties)
    table_id = props.get("id")
    addresses = [a for a in info.parsed_addresses() if ":" not in a]  # IPv4 only
    if not table_id or not addresses or not info.port:
        return None

    host = addresses[0]
    port = info.port
    url = f"http://{host}" if port == 80 else f"http://{host}:{port}"
    return {
        "id": table_id,
        "name": props.get("name") or "Dune Weaver",
        "url": url,
        "host": host,
        "port": port,
        "version": props.get("version") or None,
    }


def _looks_like_board(label: str, server: str, props: Dict[str, str]) -> bool:
    """Does a resolved _http._tcp service look like a Dune Weaver board?"""
    model = (props.get("model") or "").lower()
    api = (props.get("api") or "").lower()
    if model == "dune-weaver" or "sandtable" in api:
        return True
    # Fallback for firmware builds without TXT records: match the firmware's
    # default hostname / service name (same heuristic as the mobile app).
    hay = f"{label} {server}".lower()
    return bool(re.search(r"fluidnc|dune[-\s]?weaver|sand[-\s]?table", hay))


def service_info_to_board(info) -> Optional[dict]:
    """Convert a resolved _http._tcp ServiceInfo into a board dict for the API.

    Returns None for services that don't look like a Dune Weaver board or
    that lack an IPv4 address.
    """
    props = _decode_properties(info.properties)
    # "DWMP._http._tcp.local." -> "DWMP" (the firmware hostname = table name)
    label = info.name.split("._")[0] if "._" in info.name else info.name
    server = (info.server or "").rstrip(".")
    if not _looks_like_board(label, server, props):
        return None
    addresses = [a for a in info.parsed_addresses() if ":" not in a]  # IPv4 only
    if not addresses or not info.port:
        return None

    host = addresses[0]
    port = info.port
    hostname = server[: -len(".local")] if server.endswith(".local") else server
    return {
        "name": label or hostname or host,
        "hostname": hostname or None,
        "host": host,
        "port": port,
        "url": f"http://{host}" if port == 80 else f"http://{host}:{port}",
        # Stable hardware identity (fw > v0.1.7); None on older firmware.
        "mac": (props.get("mac") or "").lower() or None,
    }


class TableDiscovery:
    """Advertises this table via mDNS and tracks peer tables on the LAN."""

    def __init__(self):
        self._aiozc = None
        self._browser = None
        self._board_browser = None
        self._service_info = None
        self._own_id: Optional[str] = None
        # Keyed by mDNS service name so Removed events can evict entries
        self._discovered: Dict[str, dict] = {}
        self._boards: Dict[str, dict] = {}

    @property
    def is_running(self) -> bool:
        return self._aiozc is not None

    def get_tables(self) -> List[dict]:
        """Currently visible peer tables (excludes this table)."""
        return list(self._discovered.values())

    def get_boards(self) -> List[dict]:
        """Currently visible FluidNC controller boards (candidates for /connect)."""
        return list(self._boards.values())

    async def start(self, table_id: str, table_name: str, port: int, version: Optional[str] = None):
        if not ZEROCONF_AVAILABLE:
            logger.warning("zeroconf package not installed - mDNS table discovery disabled")
            return
        if self._aiozc:
            return

        local_ip = _get_local_ip()
        if not local_ip:
            logger.warning("Could not determine LAN IP - mDNS table discovery disabled")
            return

        self._own_id = table_id
        self._aiozc = AsyncZeroconf(ip_version=IPVersion.V4Only)

        # Instance names must be unique per network; the table id suffix
        # keeps two tables both named "Dune Weaver" from colliding.
        instance = f"{self._instance_label(table_name)}-{table_id[:8]}.{SERVICE_TYPE}"
        self._service_info = ServiceInfo(
            SERVICE_TYPE,
            instance,
            addresses=[socket.inet_aton(local_ip)],
            port=port,
            properties=self._properties(table_id, table_name, version),
            server=f"dune-weaver-{table_id[:8]}.local.",
        )

        try:
            await self._aiozc.async_register_service(self._service_info)
            self._browser = AsyncServiceBrowser(
                self._aiozc.zeroconf, SERVICE_TYPE, handlers=[self._on_service_state_change]
            )
            self._board_browser = AsyncServiceBrowser(
                self._aiozc.zeroconf, HTTP_SERVICE_TYPE, handlers=[self._on_board_state_change]
            )
            logger.info(f"mDNS: advertising '{table_name}' at {local_ip}:{port} and browsing for peer tables and boards")
        except Exception as e:
            logger.warning(f"mDNS discovery failed to start: {e}")
            await self.stop()

    async def update_name(self, table_name: str):
        """Re-advertise with a new display name after the table is renamed."""
        if not (self._aiozc and self._service_info):
            return
        try:
            # Keep the instance name stable; only the TXT records change
            self._service_info = ServiceInfo(
                SERVICE_TYPE,
                self._service_info.name,
                addresses=self._service_info.addresses,
                port=self._service_info.port,
                properties=self._properties(self._own_id, table_name, self._decoded_own_version()),
                server=self._service_info.server,
            )
            await self._aiozc.async_update_service(self._service_info)
        except Exception as e:
            logger.warning(f"mDNS: failed to update advertised name: {e}")

    async def stop(self):
        if not self._aiozc:
            return
        try:
            if self._browser:
                await self._browser.async_cancel()
            if self._board_browser:
                await self._board_browser.async_cancel()
            if self._service_info:
                await self._aiozc.async_unregister_service(self._service_info)
            await self._aiozc.async_close()
        except Exception as e:
            logger.debug(f"mDNS shutdown error: {e}")
        finally:
            self._aiozc = None
            self._browser = None
            self._board_browser = None
            self._service_info = None
            self._discovered.clear()
            self._boards.clear()

    @staticmethod
    def _properties(table_id: str, table_name: str, version: Optional[str]) -> Dict[str, str]:
        return {"id": table_id or "", "name": table_name or "Dune Weaver", "version": version or ""}

    def _decoded_own_version(self) -> Optional[str]:
        props = _decode_properties(self._service_info.properties) if self._service_info else {}
        return props.get("version") or None

    @staticmethod
    def _instance_label(table_name: str) -> str:
        # mDNS instance names allow most characters, but dots would be parsed
        # as label separators - keep it to a safe subset.
        label = re.sub(r"[^A-Za-z0-9 _-]", "", table_name or "").strip() or "Dune Weaver"
        return label[:40]

    def _on_service_state_change(self, zeroconf, service_type, name, state_change):
        """Sync callback from AsyncServiceBrowser (runs on the event loop)."""
        if state_change is ServiceStateChange.Removed:
            removed = self._discovered.pop(name, None)
            if removed:
                logger.info(f"mDNS: table '{removed['name']}' left the network")
            return
        # Added/Updated: resolve the service asynchronously
        asyncio.ensure_future(self._resolve_service(zeroconf, service_type, name))

    async def _resolve_service(self, zeroconf, service_type, name):
        try:
            info = AsyncServiceInfo(service_type, name)
            if not await info.async_request(zeroconf, RESOLVE_TIMEOUT_MS):
                return
            table = service_info_to_table(info)
            if not table or table["id"] == self._own_id:
                return
            is_new = name not in self._discovered
            self._discovered[name] = table
            if is_new:
                logger.info(f"mDNS: discovered table '{table['name']}' at {table['url']}")
        except Exception as e:
            logger.debug(f"mDNS: failed to resolve {name}: {e}")

    def _on_board_state_change(self, zeroconf, service_type, name, state_change):
        """Browser callback for _http._tcp (FluidNC controller boards)."""
        if state_change is ServiceStateChange.Removed:
            removed = self._boards.pop(name, None)
            if removed:
                logger.info(f"mDNS: board '{removed['name']}' left the network")
            return
        asyncio.ensure_future(self._resolve_board(zeroconf, service_type, name))

    async def _resolve_board(self, zeroconf, service_type, name):
        try:
            info = AsyncServiceInfo(service_type, name)
            if not await info.async_request(zeroconf, RESOLVE_TIMEOUT_MS):
                return
            board = service_info_to_board(info)
            if not board:
                return
            is_new = name not in self._boards
            self._boards[name] = board
            if is_new:
                logger.info(f"mDNS: discovered board '{board['name']}' at {board['url']}")
        except Exception as e:
            logger.debug(f"mDNS: failed to resolve board {name}: {e}")


# Module-level singleton, mirroring how other core services are exposed
discovery = TableDiscovery()
