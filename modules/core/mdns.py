"""mDNS advertisement and discovery for multi-table support.

This module provides:
- Service advertisement: Allows this table to be discovered by other frontends
- Service discovery: Finds other Dune Weaver tables on the local network
"""

import asyncio
import logging
import socket
from typing import List, Dict, Optional
from zeroconf import ServiceInfo, Zeroconf, ServiceBrowser, ServiceListener
from zeroconf.asyncio import AsyncZeroconf, AsyncServiceBrowser

logger = logging.getLogger(__name__)

# Service type for Dune Weaver tables
SERVICE_TYPE = "_duneweaver._tcp.local."


class DuneWeaverServiceListener(ServiceListener):
    """Listener for discovered Dune Weaver services."""

    def __init__(self):
        self.discovered_tables: Dict[str, Dict] = {}

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Called when a new service is discovered."""
        info = zc.get_service_info(type_, name)
        if info:
            self._process_service_info(name, info)

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Called when an existing service is updated."""
        info = zc.get_service_info(type_, name)
        if info:
            self._process_service_info(name, info)

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Called when a service is removed."""
        if name in self.discovered_tables:
            del self.discovered_tables[name]
            logger.debug(f"Table removed: {name}")

    def _process_service_info(self, name: str, info: ServiceInfo) -> None:
        """Extract table information from service info."""
        try:
            # Get properties
            properties = {}
            if info.properties:
                for key, value in info.properties.items():
                    if isinstance(value, bytes):
                        properties[key.decode() if isinstance(key, bytes) else key] = value.decode()
                    else:
                        properties[key if isinstance(key, str) else key.decode()] = str(value)

            # Get addresses
            addresses = info.parsed_addresses()
            host = addresses[0] if addresses else None
            port = info.port

            if host and port:
                self.discovered_tables[name] = {
                    "id": properties.get("id", ""),
                    "name": properties.get("name", name.replace(f".{SERVICE_TYPE}", "")),
                    "host": host,
                    "port": port,
                    "version": properties.get("version", "unknown"),
                    "url": f"http://{host}:{port}"
                }
                logger.debug(f"Discovered table: {self.discovered_tables[name]}")
        except Exception as e:
            logger.warning(f"Error processing service info for {name}: {e}")


class MDNSManager:
    """Manages mDNS advertisement and discovery for Dune Weaver."""

    def __init__(self):
        self._zeroconf: Optional[AsyncZeroconf] = None
        self._service_info: Optional[ServiceInfo] = None
        self._browser: Optional[AsyncServiceBrowser] = None
        self._listener: Optional[DuneWeaverServiceListener] = None
        self._advertised = False

    def _get_local_ip(self) -> str:
        """Get the local IP address of this machine."""
        try:
            # Create a socket to determine our IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                # Doesn't need to be reachable
                s.connect(("10.255.255.255", 1))
                ip = s.getsockname()[0]
            except Exception:
                ip = "127.0.0.1"
            finally:
                s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    async def start_advertisement(self, table_id: str, table_name: str, version: str, port: int = 8080) -> bool:
        """
        Start advertising this table on the network.

        Args:
            table_id: Unique identifier for this table
            table_name: Human-readable name for this table
            version: Software version
            port: HTTP port the server is running on

        Returns:
            True if advertisement started successfully
        """
        try:
            if self._advertised:
                await self.stop_advertisement()

            local_ip = self._get_local_ip()
            hostname = socket.gethostname()

            # Create service info
            # Service name must be unique on the network
            service_name = f"{table_name.replace(' ', '_')}_{table_id[:8]}.{SERVICE_TYPE}"

            self._service_info = ServiceInfo(
                SERVICE_TYPE,
                service_name,
                addresses=[socket.inet_aton(local_ip)],
                port=port,
                properties={
                    "id": table_id,
                    "name": table_name,
                    "version": version,
                    "hostname": hostname
                },
                server=f"{hostname}.local."
            )

            # Start zeroconf and register service
            self._zeroconf = AsyncZeroconf()
            await self._zeroconf.async_register_service(self._service_info)
            self._advertised = True

            logger.info(f"mDNS: Advertising table '{table_name}' at {local_ip}:{port}")
            return True

        except Exception as e:
            logger.error(f"Failed to start mDNS advertisement: {e}")
            return False

    async def stop_advertisement(self) -> None:
        """Stop advertising this table."""
        try:
            if self._service_info and self._zeroconf:
                await self._zeroconf.async_unregister_service(self._service_info)
            if self._zeroconf:
                await self._zeroconf.async_close()
            self._advertised = False
            self._service_info = None
            self._zeroconf = None
            logger.info("mDNS: Stopped advertising")
        except Exception as e:
            logger.warning(f"Error stopping mDNS advertisement: {e}")

    async def discover_tables(self, timeout: float = 3.0) -> List[Dict]:
        """
        Discover Dune Weaver tables on the local network.

        Args:
            timeout: How long to wait for discovery (seconds)

        Returns:
            List of discovered tables with their info
        """
        discovered = []

        try:
            # Create a temporary zeroconf instance for discovery
            zc = Zeroconf()
            listener = DuneWeaverServiceListener()

            # Start browsing for services
            browser = ServiceBrowser(zc, SERVICE_TYPE, listener)

            # Wait for discovery
            await asyncio.sleep(timeout)

            # Collect results
            discovered = list(listener.discovered_tables.values())

            # Cleanup
            browser.cancel()
            zc.close()

            logger.info(f"mDNS: Discovered {len(discovered)} table(s)")

        except Exception as e:
            logger.error(f"Error during mDNS discovery: {e}")

        return discovered

    async def update_advertisement(self, table_name: str) -> None:
        """Update the advertised table name."""
        if self._advertised and self._service_info:
            # Get current info
            from modules.core.state import state
            from modules.core.version_manager import version_manager

            # Restart advertisement with new name
            await self.stop_advertisement()
            await self.start_advertisement(
                table_id=state.table_id,
                table_name=table_name,
                version=await version_manager.get_current_version(),
                port=state.server_port or 8080
            )


# Singleton instance
mdns_manager = MDNSManager()


async def start_mdns_advertisement():
    """Start mDNS advertisement using current state."""
    from modules.core.state import state
    from modules.core.version_manager import version_manager

    await mdns_manager.start_advertisement(
        table_id=state.table_id,
        table_name=state.table_name,
        version=await version_manager.get_current_version(),
        port=state.server_port or 8080
    )


async def stop_mdns_advertisement():
    """Stop mDNS advertisement."""
    await mdns_manager.stop_advertisement()


async def discover_tables(timeout: float = 3.0) -> List[Dict]:
    """Discover Dune Weaver tables on the network."""
    return await mdns_manager.discover_tables(timeout)
