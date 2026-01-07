"""Preview module for generating image previews of patterns.

Uses ProcessPoolExecutor to run CPU-intensive preview generation in separate
processes, completely eliminating Python GIL contention with the motion control thread.
"""
import os
import math
import asyncio
import sys
import logging
from io import BytesIO

logger = logging.getLogger(__name__)

# Shared process pool - set by main.py at startup
_shared_pool = None


def set_process_pool(pool):
    """Set the shared process pool for preview generation.
    
    Called by main.py at startup to share a single pool across modules.
    """
    global _shared_pool
    _shared_pool = pool
    logger.debug("Preview module using shared process pool")


def _get_process_pool():
    """Get the shared process pool."""
    if _shared_pool is None:
        raise RuntimeError("Process pool not initialized - call set_process_pool() first")
    return _shared_pool


def _get_worker_cpu_affinity():
    """Get the set of CPUs for worker processes.
    
    Returns CPUs 1 through N-1 (leaving CPU 0 for motion control),
    or None if affinity shouldn't be set.
    """
    cpu_count = os.cpu_count() or 1
    if cpu_count <= 1:
        return None  # Single core - don't set affinity
    # Use all CPUs except CPU 0 (reserved for motion control)
    return set(range(1, cpu_count))


def _setup_worker_process():
    """Setup function called at start of worker process.
    
    Configures CPU affinity and priority for the worker process.
    This runs once when each worker process starts.
    """
    if sys.platform != 'linux':
        return
    
    # Set CPU affinity dynamically based on available cores
    worker_cpus = _get_worker_cpu_affinity()
    if worker_cpus:
        try:
            os.sched_setaffinity(0, worker_cpus)
        except Exception:
            pass
    
    try:
        # Lower priority (positive nice = lower priority)
        os.nice(10)
    except Exception:
        pass


def _generate_preview_in_process(pattern_file, format='WEBP'):
    """Generate preview entirely within a worker process.
    
    This function runs in a separate process with its own GIL,
    so it cannot block the motion control thread's Python execution.
    
    All imports are done inside the function to ensure they happen
    in the worker process, not the main process.
    """
    # Setup worker process (CPU affinity + nice)
    _setup_worker_process()
    
    # Import dependencies in the worker process
    from PIL import Image, ImageDraw
    from modules.core.pattern_manager import parse_theta_rho_file, THETA_RHO_DIR
    
    file_path = os.path.join(THETA_RHO_DIR, pattern_file)
    
    # Parse the pattern file
    coordinates = []
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    theta, rho = map(float, line.split())
                    coordinates.append((theta, rho))
                except ValueError:
                    continue
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        coordinates = []
    
    # Image generation parameters
    RENDER_SIZE = 2048
    DISPLAY_SIZE = 512
    
    if not coordinates:
        # Create an image with "No pattern data" text
        img = Image.new('RGBA', (DISPLAY_SIZE, DISPLAY_SIZE), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        text = "No pattern data"
        try:
            bbox = draw.textbbox((0, 0), text)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = (DISPLAY_SIZE - text_width) / 2
            text_y = (DISPLAY_SIZE - text_height) / 2
        except:
            text_x = DISPLAY_SIZE / 4 
            text_y = DISPLAY_SIZE / 2
        draw.text((text_x, text_y), text, fill="black")
        
        img_byte_arr = BytesIO()
        img.save(img_byte_arr, format=format)
        img_byte_arr.seek(0)
        return img_byte_arr.getvalue()

    # Create image and draw pattern
    img = Image.new('RGBA', (RENDER_SIZE, RENDER_SIZE), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    CENTER = RENDER_SIZE / 2.0
    SCALE_FACTOR = (RENDER_SIZE / 2.0) - 10.0 
    LINE_COLOR = "black" 
    STROKE_WIDTH = 2

    points_to_draw = []
    for theta, rho in coordinates:
        x = CENTER - rho * SCALE_FACTOR * math.cos(theta)
        y = CENTER - rho * SCALE_FACTOR * math.sin(theta)
        points_to_draw.append((x, y))
    
    if len(points_to_draw) > 1:
        draw.line(points_to_draw, fill=LINE_COLOR, width=STROKE_WIDTH, joint="curve")
    elif len(points_to_draw) == 1:
        r = 4
        x, y = points_to_draw[0]
        draw.ellipse([(x-r, y-r), (x+r, y+r)], fill=LINE_COLOR)

    # Scale down and rotate
    img = img.resize((DISPLAY_SIZE, DISPLAY_SIZE), Image.Resampling.LANCZOS)
    img = img.rotate(180)

    # Save to bytes
    img_byte_arr = BytesIO()
    img.save(img_byte_arr, format=format, lossless=False, alpha_quality=20, method=0)
    img_byte_arr.seek(0)
    return img_byte_arr.getvalue()


async def generate_preview_image(pattern_file, format='WEBP'):
    """Generate a preview for a pattern file.
    
    Runs in a separate process via ProcessPoolExecutor to completely
    eliminate GIL contention with the motion control thread.
    """
    loop = asyncio.get_event_loop()
    pool = _get_process_pool()
    
    try:
        # Run preview generation in a separate process (separate GIL)
        result = await loop.run_in_executor(
            pool,
            _generate_preview_in_process,
            pattern_file,
            format
        )
        return result
    except Exception as e:
        logger.error(f"Error generating preview for {pattern_file}: {e}")
        return None
