"""Board firmware OTA — GitHub release lookup and version comparison.

Firmware releases are published as GitHub Release assets on the firmware repo
(`firmware.bin` = the ESP32 app-partition image). The flash itself goes through
FluidNCClient.upload_firmware (POST /updatefw); this module only knows how to
find the latest release and compare versions.
"""

import logging
import re
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

FIRMWARE_REPO = "tuanchris/dune-weaver-firmware"
_CACHE_TTL = 600  # GitHub unauthenticated rate limit is 60/hr - cache lookups

_cache: dict = {"at": 0.0, "release": None}


def get_latest_release(force: bool = False) -> Optional[dict]:
    """Latest published firmware release, or None when unreachable / no
    firmware.bin asset. Cached for 10 minutes."""
    now = time.time()
    if not force and _cache["release"] and now - _cache["at"] < _CACHE_TTL:
        return _cache["release"]
    try:
        r = requests.get(
            f"https://api.github.com/repos/{FIRMWARE_REPO}/releases/latest",
            headers={"Accept": "application/vnd.github+json"},
            timeout=10.0,
        )
        r.raise_for_status()
        data = r.json()
        asset = next((a for a in data.get("assets", []) if a.get("name") == "firmware.bin"), None)
        if not asset:
            logger.warning("Latest firmware release has no firmware.bin asset")
            return None
        release = {
            "version": data.get("tag_name") or "",
            "download_url": asset.get("browser_download_url"),
            "release_url": data.get("html_url") or f"https://github.com/{FIRMWARE_REPO}/releases",
            "published_at": data.get("published_at"),
        }
        _cache.update(at=now, release=release)
        return release
    except Exception as e:
        logger.warning(f"Firmware release lookup failed: {e}")
        return None


def parse_version(fw: Optional[str]) -> Optional[tuple]:
    """'v0.1.10 (main-5ce4400d-dirty)' -> (0, 1, 10); None if unparseable."""
    if not fw:
        return None
    m = re.search(r"v?(\d+)\.(\d+)\.(\d+)", fw)
    return tuple(int(g) for g in m.groups()) if m else None


def is_newer(latest_tag: str, current_fw: Optional[str]) -> bool:
    latest = parse_version(latest_tag)
    current = parse_version(current_fw)
    if not latest or not current:
        return False
    return latest > current


def download_image(url: str) -> bytes:
    """Download and sanity-check a firmware image (ESP32 magic byte 0xE9)."""
    r = requests.get(url, timeout=60.0)
    r.raise_for_status()
    image = r.content
    if len(image) < 100_000 or image[0] != 0xE9:
        raise ValueError("Downloaded firmware image looks invalid")
    return image
