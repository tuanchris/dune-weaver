"""Preview module for generating image previews of patterns."""
import os
import math
import asyncio
from io import BytesIO
from PIL import Image, ImageDraw
from modules.core.pattern_manager import parse_theta_rho_file, THETA_RHO_DIR

RENDER_SIZE = 1024

def _generate_preview_image_sync(pattern_file):
    """Synchronous version of preview generation to run in thread pool."""
    file_path = os.path.join(THETA_RHO_DIR, pattern_file)
    coordinates = parse_theta_rho_file(file_path) 
    
    if not coordinates:
        # Create an image with "No pattern data" text
        img = Image.new('RGBA', (RENDER_SIZE, RENDER_SIZE), (255, 255, 255, 0)) # Transparent background
        draw = ImageDraw.Draw(img)
        text = "No pattern data"
        try:
            bbox = draw.textbbox((0, 0), text)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = (RENDER_SIZE - text_width) / 2
            text_y = (RENDER_SIZE - text_height) / 2
        except:
            text_x = RENDER_SIZE / 4 
            text_y = RENDER_SIZE / 2
        draw.text((text_x, text_y), text, fill="black")
        img_byte_arr = BytesIO()
        img.save(img_byte_arr, format='WEBP', quality=75, method=6)
        img_byte_arr.seek(0)
        return img_byte_arr.getvalue()

    # Image drawing parameters
    img = Image.new('RGBA', (RENDER_SIZE, RENDER_SIZE), (255, 255, 255, 0)) # Transparent background
    draw = ImageDraw.Draw(img)
    
    CENTER = RENDER_SIZE / 2.0
    SCALE_FACTOR = (RENDER_SIZE / 2.0) - 40.0  # Padding for high-res
    LINE_COLOR = "black" 
    STROKE_WIDTH = 8  # Thicker for high-res

    # Optimize point drawing by reducing precision
    points_to_draw = []
    for theta, rho in coordinates:
        x = round(CENTER - rho * SCALE_FACTOR * math.cos(theta), 2)
        y = round(CENTER - rho * SCALE_FACTOR * math.sin(theta), 2)
        points_to_draw.append((x, y))
    
    if len(points_to_draw) > 1:
        draw.line(points_to_draw, fill=LINE_COLOR, width=STROKE_WIDTH, joint="curve")
    elif len(points_to_draw) == 1:
        r = 24  # Larger for high-res
        x, y = points_to_draw[0]
        draw.ellipse([(x-r, y-r), (x+r, y+r)], fill=LINE_COLOR)

    img_byte_arr = BytesIO()
    img.save(img_byte_arr, format='WEBP', quality=75, method=6)
    img_byte_arr.seek(0)
    return img_byte_arr.getvalue()

async def generate_preview_image(pattern_file):
    """Generate a WebP preview for a pattern file, rendered at 2048x2048 and downsampled to 512x512."""
    return await asyncio.to_thread(_generate_preview_image_sync, pattern_file)