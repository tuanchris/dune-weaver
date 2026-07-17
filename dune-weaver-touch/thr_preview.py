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
# The dune-weaver backend's pattern catalog, when co-located (the touch app
# normally runs on the same Pi as the backend). Reading .thr files from here
# is instant; fetching them from the board's SD over HTTP runs at ESP32 speed
# (measured ~30-60 KB/s), so local files are always preferred.
LOCAL_PATTERNS_DIR = Path(__file__).parent.parent / "patterns"
# Same supersampling scheme as the web backend (modules/core/preview.py):
# draw at RENDER_SIZE, LANCZOS-downsample to IMAGE_SIZE for smooth thin lines.
IMAGE_SIZE = 512          # final PNG is IMAGE_SIZE x IMAGE_SIZE
_RENDER_SIZE = 2048       # supersampled draw size
_MARGIN = 12              # dish margin, in IMAGE_SIZE pixels
_LINE_WIDTH = 8           # in RENDER_SIZE pixels -> 2px at IMAGE_SIZE (web parity)
# Bump when the rendering itself changes (colors, orientation, size): the
# version is part of the cache filename, so stale renders are simply ignored.
_RENDER_VERSION = 4
# One download at a time: the board's web server serializes requests, and a
# single in-flight .thr transfer already delays /sand_status by seconds
# (measured: 2 concurrent transfers starve the 1 Hz status poll almost
# completely). Previews are cached after first fetch, so this only slows the
# very first grid load.
_semaphore = asyncio.Semaphore(1)
# Rendering is CPU-heavy (2048px supersampled draw + LANCZOS downscale).
# A fast flick through uncached patterns schedules a render per tile; without
# a cap they saturate every core on the Pi and starve the GUI thread. Two at
# a time keeps a core free for the UI and one for the warmer/board I/O.
_cpu_semaphore = asyncio.Semaphore(2)


def _slug(base_url: str) -> str:
    host = urlparse(base_url).netloc or base_url or "table"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", host)


def _cache_path(base_url: str, rel_path: str, content_hash: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", rel_path)
    return CACHE_ROOT / _slug(base_url) / f"{safe}.{content_hash}.v{_RENDER_VERSION}.png"


_local_index: dict[str, Path] | None = None


def _find_local_thr(rel_path: str) -> Path | None:
    """Map a board-relative pattern path to a file in the host catalog.

    The reverse of the backend's ``make_sd_path_resolver`` matching: exact
    relative path first, then a host path whose *suffix* equals the board
    path (host 'custom_patterns/sand-patterns/patterns/x.thr' matches board
    'sand-patterns/patterns/x.thr'), then a UNIQUE basename match. Ambiguity
    or no match returns None and the caller falls back to fetching from the
    board.
    """
    global _local_index
    if _local_index is None:
        index: dict[str, Path] = {}
        try:
            for p in LOCAL_PATTERNS_DIR.rglob("*.thr"):
                index[p.relative_to(LOCAL_PATTERNS_DIR).as_posix()] = p
        except OSError:
            pass
        _local_index = index
    rel = rel_path.replace("\\", "/").lstrip("/")
    hit = _local_index.get(rel)
    if hit:
        return hit
    suffix_hits = [p for r, p in _local_index.items()
                   if r == rel or r.endswith("/" + rel)]
    if len(suffix_hits) == 1:
        return suffix_hits[0]
    if suffix_hits:
        return None  # ambiguous
    base = rel.rsplit("/", 1)[-1]
    base_hits = [p for r, p in _local_index.items()
                 if r.rsplit("/", 1)[-1] == base]
    return base_hits[0] if len(base_hits) == 1 else None


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
    size = _RENDER_SIZE
    scale = _RENDER_SIZE / IMAGE_SIZE
    margin = _MARGIN * scale
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    center = size / 2
    radius = center - margin

    # Sand-table dish backdrop — warm basalt, matching the UI's night palette
    # (the disc reads as "a window onto the table" in both UI themes).
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=(27, 23, 18, 255), outline=(62, 54, 44, 255), width=round(2 * scale),
    )

    xy = []
    # Same orientation as the web backend's previews (modules/core/preview.py:
    # CENTER - r*cos/sin then a 180° rotate, which nets to CENTER + r*cos/sin).
    for theta, rho in points:
        rho = max(0.0, min(1.0, rho))
        r = rho * radius
        xy.append((center + r * math.cos(theta), center + r * math.sin(theta)))

    # Sand under warm light rather than clinical white.
    line_color = (216, 181, 120, 255)
    if len(xy) >= 2:
        draw.line(xy, fill=line_color, width=_LINE_WIDTH, joint="curve")
    elif len(xy) == 1:
        x, y = xy[0]
        r = _LINE_WIDTH
        draw.ellipse([x - r, y - r, x + r, y + r], fill=line_color)

    img = img.resize((IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.LANCZOS)

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
    matches = sorted(folder.glob(f"{safe}.*.v{_RENDER_VERSION}.png"))
    return str(matches[0].absolute()) if matches else ""


def safe_name(rel_path: str) -> str:
    """The sanitized form of a pattern path used in cache filenames."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", rel_path)


def has_local_source(rel_path: str) -> bool:
    """True when the pattern's .thr resolves in the co-located host catalog.

    Used by the background cache warmer to render only patterns that cost
    no board I/O — board-only patterns stay lazy (rendered when viewed).
    """
    return _find_local_thr(rel_path) is not None


def preview_index(base_url: str) -> dict[str, str]:
    """Map ``safe_name(rel_path)`` -> cached PNG path, in ONE directory scan.

    ``cached_preview`` globs the cache folder per pattern — fine for a lookup
    or two, quadratic when a 1000-pattern grid asks row by row (and the model
    asks from the GUI thread). Callers scan once per catalogue refresh and
    hand rows out of the dict instead.
    """
    folder = CACHE_ROOT / _slug(base_url)
    suffix = f".v{_RENDER_VERSION}.png"
    index: dict[str, str] = {}
    if not folder.exists():
        return index
    try:
        for p in sorted(folder.iterdir()):
            name = p.name
            if not name.endswith(suffix):
                continue
            # Filename shape: <safe>.<contenthash>.v<N>.png
            parts = name.rsplit(".", 3)
            if len(parts) != 4:
                continue
            index.setdefault(parts[0], str(p.absolute()))
    except OSError:
        pass
    return index


async def render_preview(client, base_url: str, rel_path: str) -> str | None:
    """Fetch ``rel_path`` from the table and render its preview PNG.

    ``client`` is a :class:`firmware_client.FirmwareClient`. Returns the
    absolute path to the cached PNG, "" when the pattern genuinely has no
    renderable preview (empty/unparseable), or ``None`` on a *transient*
    failure (fetch timeout, board busy) that is worth retrying later —
    callers must not cache ``None`` as a permanent miss.
    """
    if Image is None:
        logger.warning("Pillow not available - cannot render previews")
        return ""
    # Local catalog first: instant, no board I/O, no semaphore needed.
    local = _find_local_thr(rel_path)
    if local is not None:
        try:
            data = await asyncio.to_thread(local.read_bytes)
        except OSError as exc:
            logger.debug(f"local pattern read failed for {rel_path}: {exc}")
            local = None
    if local is None:
        async with _semaphore:
            try:
                data = await client.fetch_sd_file(f"/patterns/{rel_path}")
            except Exception as exc:
                logger.debug(f"preview fetch failed for {rel_path}: {exc}")
                return None
    content_hash = hashlib.sha1(data).hexdigest()[:10]
    out_path = _cache_path(base_url, rel_path, content_hash)
    if out_path.exists():
        return str(out_path.absolute())
    try:
        text = data.decode("utf-8", errors="ignore")
        points = _parse_thr(text)
        if not points:
            return ""
        # Rendering is CPU-bound; keep it off the event loop and capped.
        async with _cpu_semaphore:
            ok = await asyncio.to_thread(_render_png, points, out_path)
        return str(out_path.absolute()) if ok else ""
    except Exception as exc:
        logger.error(f"preview render failed for {rel_path}: {exc}")
        return ""
