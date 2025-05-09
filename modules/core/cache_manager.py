"""Image Cache Manager for pre-generating and managing image previews."""
import os
import json
import asyncio
import logging
from pathlib import Path
from modules.core.pattern_manager import list_theta_rho_files, THETA_RHO_DIR

logger = logging.getLogger(__name__)

# Constants
CACHE_DIR = os.path.join(THETA_RHO_DIR, "cached_images")

def ensure_cache_dir():
    """Ensure the cache directory exists with proper permissions."""
    try:
        Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
        
        for root, dirs, files in os.walk(CACHE_DIR):
            try:
                os.chmod(root, 0o777)
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        os.chmod(file_path, 0o666)
                    except Exception as e:
                        logger.error(f"Failed to set permissions for file {file_path}: {str(e)}")
            except Exception as e:
                logger.error(f"Failed to set permissions for directory {root}: {str(e)}")
                continue
                
    except Exception as e:
        logger.error(f"Failed to set cache directory permissions: {str(e)}")
        pass

def get_cache_path(pattern_file):
    """Get the cache path for a pattern file."""
    # Create subdirectories in cache to match the pattern file structure
    cache_subpath = os.path.dirname(pattern_file)
    cache_dir = os.path.join(CACHE_DIR, cache_subpath)
    
    # Ensure the subdirectory exists
    os.makedirs(cache_dir, exist_ok=True)
    try:
        os.chmod(cache_dir, 0o777)
    except Exception as e:
        logger.error(f"Failed to set permissions for cache subdirectory {cache_dir}: {str(e)}")
    
    # Use just the filename part for the cache file
    filename = os.path.basename(pattern_file)
    safe_name = filename.replace('\\', '_')
    return os.path.join(cache_dir, f"{safe_name}.png")

def needs_cache(pattern_file):
    """Check if a pattern file needs its cache generated."""
    cache_path = get_cache_path(pattern_file)
    return not os.path.exists(cache_path)

async def generate_image_preview(pattern_file):
    """Generate image preview for a single pattern file."""
    from modules.core.preview import generate_preview_image
    try:
        image_content = await generate_preview_image(pattern_file)
        
        cache_path = get_cache_path(pattern_file)
        with open(cache_path, 'wb') as f:
            f.write(image_content)
        
        try:
            os.chmod(cache_path, 0o666)
        except Exception as e:
            logger.error(f"Failed to set cache file permissions for {pattern_file}: {str(e)}")
            pass
        
        return True
    except Exception as e:
        logger.error(f"Failed to generate image for {pattern_file}: {str(e)}")
        return False

async def generate_all_image_previews():
    """Generate image previews for all pattern files."""
    ensure_cache_dir()
    
    pattern_files = [f for f in list_theta_rho_files() if f.endswith('.thr')]
    patterns_to_cache = [f for f in pattern_files if needs_cache(f)]
    total_files = len(patterns_to_cache)
    
    if total_files == 0:
        logger.info("All patterns are already cached")
        return
        
    logger.info(f"Generating image cache for {total_files} uncached .thr patterns...")
    
    batch_size = 5
    successful = 0
    for i in range(0, total_files, batch_size):
        batch = patterns_to_cache[i:i + batch_size]
        tasks = [generate_image_preview(file) for file in batch]
        results = await asyncio.gather(*tasks)
        successful += sum(1 for r in results if r)
    
    logger.info(f"Image cache generation completed: {successful}/{total_files} patterns cached")