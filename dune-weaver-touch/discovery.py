"""mDNS discovery for Dune Weaver sand tables.

The firmware advertises ``_http._tcp.local`` with TXT records identifying a
sand table (``model=dune-weaver``, ``api=sandtable/1``, ``ws=<port>``). We
browse for those services and hand back a list the UI can pick from. Manual IP
entry remains the fallback (and works even when zeroconf is unavailable).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

logger = logging.getLogger("DuneWeaver.Discovery")

try:
    from zeroconf import ServiceStateChange
    from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconf
    ZEROCONF_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    ZEROCONF_AVAILABLE = False


@dataclass
class DiscoveredTable:
    name: str        # friendly service name
    host: str        # e.g. "dunetable.local"
    address: str     # numeric IP
    port: int        # HTTP port
    ws_port: int     # webui-v3 websocket port (from TXT), 0 if absent

    @property
    def base_url(self) -> str:
        # Prefer the numeric address (reliable on kiosks without working mDNS
        # resolution); fall back to the .local hostname.
        host = self.address or self.host
        if self.port and self.port != 80:
            return f"http://{host}:{self.port}"
        return f"http://{host}"


def _txt_get(info, key: str) -> str:
    try:
        raw = info.properties.get(key.encode())
        return raw.decode() if raw else ""
    except Exception:
        return ""


async def discover_tables(timeout: float = 3.0) -> list[DiscoveredTable]:
    """Browse ``_http._tcp`` for ~``timeout`` seconds; return sand tables only."""
    if not ZEROCONF_AVAILABLE:
        logger.warning("zeroconf not installed - mDNS discovery unavailable")
        return []

    results: dict[str, DiscoveredTable] = {}
    aiozc = AsyncZeroconf()

    async def resolve(zeroconf, service_type, name):
        from zeroconf.asyncio import AsyncServiceInfo
        info = AsyncServiceInfo(service_type, name)
        try:
            ok = await info.async_request(zeroconf, 2500)
        except Exception as exc:
            logger.debug(f"resolve failed for {name}: {exc}")
            return
        if not ok:
            return
        # Keep only advertisements that declare themselves a sand table.
        if _txt_get(info, "model") != "dune-weaver":
            return
        addresses = info.parsed_scoped_addresses() if hasattr(info, "parsed_scoped_addresses") else []
        address = addresses[0] if addresses else ""
        host = (info.server or "").rstrip(".")
        ws_txt = _txt_get(info, "ws")
        table = DiscoveredTable(
            name=name.split(".")[0],
            host=host,
            address=address,
            port=info.port or 80,
            ws_port=int(ws_txt) if ws_txt.isdigit() else 0,
        )
        results[table.base_url] = table
        logger.info(f"Discovered table: {table.name} @ {table.base_url}")

    pending = []

    def on_change(zeroconf, service_type, name, state_change):
        if state_change is ServiceStateChange.Added:
            pending.append(asyncio.ensure_future(resolve(zeroconf, service_type, name)))

    browser = AsyncServiceBrowser(
        aiozc.zeroconf, "_http._tcp.local.", handlers=[on_change]
    )
    try:
        await asyncio.sleep(timeout)
    finally:
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        await browser.async_cancel()
        await aiozc.async_close()

    return list(results.values())
