"""Preview module for generating image previews of patterns."""
import os
import math
import asyncio
import logging
from io import BytesIO

logger = logging.getLogger(__name__)


def _generate_preview(pattern_file, format='WEBP'):
    """Generate preview for a pattern file, optimized for 300x300 view."""
    # Import dependencies in the worker process
    from PIL import Image, ImageDraw
    from modules.core.pattern_manager import parse_theta_rho_file, THETA_RHO_DIR
    
    file_path = os.path.join(THETA_RHO_DIR, pattern_file)
    coordinates = parse_theta_rho_file(file_path)
    
    # Image generation parameters
    RENDER_SIZE = 2048  # Use 2048x2048 for high quality rendering
    DISPLAY_SIZE = 512  # Final display size
    
    if not coordinates:
        # Create an image with "No pattern data" text
        img = Image.new('RGBA', (DISPLAY_SIZE, DISPLAY_SIZE), (255, 255, 255, 0))  # Transparent background
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
    img = Image.new('RGBA', (RENDER_SIZE, RENDER_SIZE), (255, 255, 255, 0))  # Transparent background
    draw = ImageDraw.Draw(img)
    
    # Image drawing parameters
    CENTER = RENDER_SIZE / 2.0
    SCALE_FACTOR = (RENDER_SIZE / 2.0) - 10.0 
    LINE_COLOR = "black" 
    STROKE_WIDTH = 2  # Increased stroke width for better visibility after scaling

    points_to_draw = []
    for theta, rho in coordinates:
        x = CENTER - rho * SCALE_FACTOR * math.cos(theta)
        y = CENTER - rho * SCALE_FACTOR * math.sin(theta)
        points_to_draw.append((x, y))
    
    if len(points_to_draw) > 1:
        draw.line(points_to_draw, fill=LINE_COLOR, width=STROKE_WIDTH, joint="curve")
    elif len(points_to_draw) == 1:
        r = 4  # Larger radius for single point to remain visible after scaling
        x, y = points_to_draw[0]
        draw.ellipse([(x-r, y-r), (x+r, y+r)], fill=LINE_COLOR)

    # Scale down to display size with high-quality resampling
    img = img.resize((DISPLAY_SIZE, DISPLAY_SIZE), Image.Resampling.LANCZOS)
    # Rotate the image 180 degrees
    img = img.rotate(180)

    # Save to bytes
    img_byte_arr = BytesIO()
    img.save(img_byte_arr, format=format, lossless=False, alpha_quality=20, method=0)
    img_byte_arr.seek(0)
    return img_byte_arr.getvalue()


async def generate_preview_image(pattern_file, format='WEBP'):
    """Generate a preview for a pattern file."""
    try:
        result = await asyncio.to_thread(_generate_preview, pattern_file, format)
        return result
    except Exception as e:
        logger.error(f"Error generating preview for {pattern_file}: {e}")
        return None
