# modules/core/thumbnail.py
from pathlib import Path
from PIL import Image, ImageDraw
import math

# Base directory of this module
BASE_DIR = Path(__file__).resolve().parent
# Directory to save and serve thumbnails (relative to app root)
THUMB_DIR = BASE_DIR / "../../thumbs"
THUMB_DIR.mkdir(parents=True, exist_ok=True)


def generate_thumbnail(
    thr_path: Path,
    size=(200, 200),
    margin=5,
    line_color="#FFFFFF",
    bg_color="#C4B4A0"
) -> Path:
    """
    Generate and cache a thumbnail PNG for the given .thr file using Pillow,
    with configurable background and line colors, corrected vertical orientation,
    and a margin to accommodate border radii.

    Args:
        thr_path (Path): Path to the .thr file.
        size (tuple): Width and height of the thumbnail in pixels.
        margin (int): Margin around the drawing area in pixels.
        line_color (str): Line color as hex string (e.g. "#ffcc00").
        bg_color (str): Background color as hex string (e.g. "#ffffff").

    Returns:
        Path: Filesystem path to the generated (or existing) thumbnail PNG.
    """
    thr_path = Path(thr_path)
    if not thr_path.exists():
        raise FileNotFoundError(f".thr file not found: {thr_path}")

    # Build thumbnail filename and path
    thumb_name = thr_path.stem + ".png"
    thumb_path = (THUMB_DIR / thumb_name).resolve()

    # If already generated, return it
    if thumb_path.exists():
        return thumb_path

    # Read θ–ρ coords, skipping comments and malformed lines
    coords = []
    for line in thr_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            theta, rho = float(parts[0]), float(parts[1])
            coords.append((theta, rho))
        except ValueError:
            continue

    # Create an image with configurable background color
    img = Image.new("RGB", size, bg_color)
    draw = ImageDraw.Draw(img)

    if coords:
        # Compute drawing area dimensions
        inner_w = size[0] - 2 * margin
        inner_h = size[1] - 2 * margin
        # Determine scaling based on max radius
        max_rho = max(r for _, r in coords) or 1.0
        cx, cy = margin + inner_w / 2, margin + inner_h / 2
        scale = min(inner_w, inner_h) / (2 * max_rho)

        # Convert polar to Cartesian with corrected Y-axis
        pts = []
        for theta, rho in coords:
            x = cx + rho * math.cos(theta) * scale
            # correct vertical orientation
            y = cy + rho * math.sin(theta) * scale
            pts.append((x, y))

        # Draw the polyline using the specified line color
        draw.line(pts, fill=line_color, width=1)

    # Save thumbnail
    img.save(thumb_path)
    return thumb_path