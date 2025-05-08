"""SVG Cache Manager for pre-generating and managing SVG previews."""
import os
import json
import asyncio
import logging
from pathlib import Path
from modules.core.pattern_manager import list_theta_rho_files, THETA_RHO_DIR

logger = logging.getLogger(__name__)

# Constants
CACHE_DIR = os.path.join(THETA_RHO_DIR, "cached_svg")

def ensure_cache_dir():
    """Ensure the cache directory exists with proper permissions."""
    try:
        Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
        
        # Walk through the cache directory and set permissions for all files and subdirectories
        for root, dirs, files in os.walk(CACHE_DIR):
            try:
                # Set 777 for directories
                os.chmod(root, 0o777)
                
                # Set 666 for files
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
        # Continue even if permissions can't be set
        pass

def get_cache_path(pattern_file):
    """Get the cache path for a pattern file."""
    # Convert the pattern file path to a safe filename
    safe_name = pattern_file.replace('/', '_').replace('\\', '_')
    return os.path.join(CACHE_DIR, f"{safe_name}.svg")

def needs_cache(pattern_file):
    """Check if a pattern file needs its cache generated."""
    cache_path = get_cache_path(pattern_file)
    return not os.path.exists(cache_path)

async def generate_svg_preview(pattern_file):
    """Generate SVG preview for a single pattern file."""
    from modules.core.preview import generate_preview_svg
    try:
        # Generate the SVG
        svg_content = await generate_preview_svg(pattern_file)
        
        # Save to cache
        cache_path = get_cache_path(pattern_file)
        with open(cache_path, 'w', encoding='utf-8') as f:
            f.write(svg_content)
        
        # Set file permissions to 666 to allow any user to read/write
        try:
            os.chmod(cache_path, 0o666)
        except Exception as e:
            logger.error(f"Failed to set cache file permissions for {pattern_file}: {str(e)}")
            # Continue even if permissions can't be set
            pass
        
        return True
    except Exception as e:
        # Only log the error message, not the full SVG content
        logger.error(f"Failed to generate SVG for {pattern_file}")
        return False

async def generate_all_svg_previews():
    """Generate SVG previews for all pattern files."""
    ensure_cache_dir()
    
    # Get all pattern files and filter for .thr files only
    pattern_files = [f for f in list_theta_rho_files() if f.endswith('.thr')]
    
    # Filter out patterns that already have cache
    patterns_to_cache = [f for f in pattern_files if needs_cache(f)]
    total_files = len(patterns_to_cache)
    
    if total_files == 0:
        logger.info("All patterns are already cached")
        return
        
    logger.info(f"Generating SVG cache for {total_files} uncached .thr patterns...")
    
    # Process files concurrently in batches to avoid overwhelming the system
    batch_size = 5
    successful = 0
    for i in range(0, total_files, batch_size):
        batch = patterns_to_cache[i:i + batch_size]
        tasks = [generate_svg_preview(file) for file in batch]
        results = await asyncio.gather(*tasks)
        successful += sum(1 for r in results if r)
    
    logger.info(f"SVG cache generation completed: {successful}/{total_files} patterns cached") 