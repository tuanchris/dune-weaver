"""Render polar ``.thr`` pattern files to cached PNG previews.

The firmware serves no thumbnails - only the raw ``.thr`` files (lists of
``<theta_radians> <rho_0..1>`` points). Clients render previews locally. We
fetch each ``.thr`` from ``/sd/patterns/...``, draw the polar path, and cache
the PNG on disk so it renders instantly next time.

Previews are cached under ``preview_cache/<table-slug>/`` keyed by the pattern
path plus a hash of the file contents, so a changed pattern re-renders.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger("DuneWeaver.Preview")

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    Image = None
    ImageDraw = None

CACHE_ROOT = Path(__file__).parent / "preview_cache"
IMAGE_SIZE = 320          # rendered PNG is IMAGE_SIZE x IMAGE_SIZE
_MARGIN = 12
# Limit concurrent renders so a full grid doesn't stampede the ESP32's small
# HTTP socket pool.
_semaphore = asyncio.Semaphore(4)


def _slug(base_url: str) -> str:
    host = urlparse(base_url).netloc or base_url or "table"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", host)


def _cache_path(base_url: str, rel_path: str, content_hash: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", rel_path)
    return CACHE_ROOT / _slug(base_url) / f"{safe}.{content_hash}.png"


def _parse_thr(text: str) -> list[tuple[float, float]]:
    points = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.replace(",", " ").split()
        if len(parts) < 2:
            continue
        try:
            theta = float(parts[0])
            rho = float(parts[1])
        except ValueError:
            continue
        points.append((theta, rho))
    return points


def _render_png(points: list[tuple[float, float]], out_path: Path) -> bool:
    if Image is None:
        return False
    size = IMAGE_SIZE
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    center = size / 2
    radius = center - _MARGIN

    # Sand-table dish backdrop.
    draw.ellipse(
        [_MARGIN, _MARGIN, size - _MARGIN, size - _MARGIN],
        fill=(28, 28, 30, 255), outline=(70, 70, 74, 255), width=2,
    )

    xy = []
    for theta, rho in points:
        rho = max(0.0, min(1.0, rho))
        r = rho * radius
        xy.append((center + r * math.cos(theta), center - r * math.sin(theta)))

    if len(xy) >= 2:
        draw.line(xy, fill=(0xF5, 0xC9, 0x6b, 255), width=2, joint="curve")
    elif len(xy) == 1:
        x, y = xy[0]
        draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(0xF5, 0xC9, 0x6b, 255))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".tmp.png")
    img.save(tmp, "PNG")
    tmp.replace(out_path)
    return True


def cached_preview(base_url: str, rel_path: str) -> str:
    """Return an existing cached preview for this pattern, or "" if none.

    Cheap, synchronous lookup for the list model's ``data()`` fast path. Because
    the cache filename embeds a content hash we don't know here, we glob for any
    cached render of this pattern (patterns rarely change on disk).
    """
    folder = CACHE_ROOT / _slug(base_url)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", rel_path)
    if not folder.exists():
        return ""
    matches = sorted(folder.glob(f"{safe}.*.png"))
    return str(matches[0].absolute()) if matches else ""


async def render_preview(client, base_url: str, rel_path: str) -> str:
    """Fetch ``rel_path`` from the table and render its preview PNG.

    ``client`` is a :class:`firmware_client.FirmwareClient`. Returns the absolute
    path to the cached PNG, or "" on failure.
    """
    if Image is None:
        logger.warning("Pillow not available - cannot render previews")
        return ""
    async with _semaphore:
        try:
            data = await client.fetch_sd_file(f"/patterns/{rel_path}")
        except Exception as exc:
            logger.debug(f"preview fetch failed for {rel_path}: {exc}")
            return ""
        content_hash = hashlib.sha1(data).hexdigest()[:10]
        out_path = _cache_path(base_url, rel_path, content_hash)
        if out_path.exists():
            return str(out_path.absolute())
        try:
            text = data.decode("utf-8", errors="ignore")
            points = _parse_thr(text)
            if not points:
                return ""
            # Rendering is CPU-bound; keep it off the event loop.
            ok = await asyncio.to_thread(_render_png, points, out_path)
            return str(out_path.absolute()) if ok else ""
        except Exception as exc:
            logger.error(f"preview render failed for {rel_path}: {exc}")
            return ""
