"""Image Cache Manager for pre-generating and managing image previews."""
import os
import json
import asyncio
import logging
from pathlib import Path
from modules.core.pattern_manager import list_theta_rho_files, THETA_RHO_DIR, parse_theta_rho_file

logger = logging.getLogger(__name__)

# Global cache progress state
cache_progress = {
    "is_running": False,
    "total_files": 0,
    "processed_files": 0,
    "current_file": "",
    "stage": "idle",  # idle, metadata, images, complete
    "error": None
}

# Constants
CACHE_DIR = os.path.join(THETA_RHO_DIR, "cached_images")
METADATA_CACHE_FILE = "metadata_cache.json"  # Now in root directory

def ensure_cache_dir():
    """Ensure the cache directory exists with proper permissions."""
    try:
        Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
        
        # Initialize metadata cache if it doesn't exist
        if not os.path.exists(METADATA_CACHE_FILE):
            with open(METADATA_CACHE_FILE, 'w') as f:
                json.dump({}, f)
            try:
                os.chmod(METADATA_CACHE_FILE, 0o644)  # More conservative permissions
            except (OSError, PermissionError) as e:
                logger.debug(f"Could not set metadata cache file permissions: {str(e)}")
        
        for root, dirs, files in os.walk(CACHE_DIR):
            try:
                os.chmod(root, 0o755)  # More conservative permissions
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        os.chmod(file_path, 0o644)  # More conservative permissions
                    except (OSError, PermissionError) as e:
                        # Log as debug instead of error since this is not critical
                        logger.debug(f"Could not set permissions for file {file_path}: {str(e)}")
            except (OSError, PermissionError) as e:
                # Log as debug instead of error since this is not critical
                logger.debug(f"Could not set permissions for directory {root}: {str(e)}")
                continue
                
    except Exception as e:
        logger.error(f"Failed to create cache directory: {str(e)}")

def get_cache_path(pattern_file):
    """Get the cache path for a pattern file."""
    # Normalize path separators to handle both forward slashes and backslashes
    pattern_file = pattern_file.replace('\\', '/')
    
    # Create subdirectories in cache to match the pattern file structure
    cache_subpath = os.path.dirname(pattern_file)
    if cache_subpath:
        # Create the same subdirectory structure in cache (including custom_patterns)
        # Convert forward slashes back to platform-specific separator for os.path.join
        cache_subpath = cache_subpath.replace('/', os.sep)
        cache_dir = os.path.join(CACHE_DIR, cache_subpath)
    else:
        # For files in root pattern directory
        cache_dir = CACHE_DIR
    
    # Ensure the subdirectory exists
    os.makedirs(cache_dir, exist_ok=True)
    try:
        os.chmod(cache_dir, 0o755)  # More conservative permissions
    except (OSError, PermissionError) as e:
        # Log as debug instead of error since this is not critical
        logger.debug(f"Could not set permissions for cache subdirectory {cache_dir}: {str(e)}")
    
    # Use just the filename part for the cache file
    filename = os.path.basename(pattern_file)
    safe_name = filename.replace('\\', '_')
    return os.path.join(cache_dir, f"{safe_name}.webp")

def delete_pattern_cache(pattern_file):
    """Delete cached preview image and metadata for a pattern file."""
    try:
        # Remove cached image
        cache_path = get_cache_path(pattern_file)
        if os.path.exists(cache_path):
            os.remove(cache_path)
            logger.info(f"Deleted cached image: {cache_path}")
        
        # Remove from metadata cache
        metadata_cache = load_metadata_cache()
        if pattern_file in metadata_cache:
            del metadata_cache[pattern_file]
            save_metadata_cache(metadata_cache)
            logger.info(f"Removed {pattern_file} from metadata cache")
        
        return True
    except Exception as e:
        logger.error(f"Failed to delete cache for {pattern_file}: {str(e)}")
        return False

def load_metadata_cache():
    """Load the metadata cache from disk."""
    try:
        if os.path.exists(METADATA_CACHE_FILE):
            with open(METADATA_CACHE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load metadata cache: {str(e)}")
    return {}

def save_metadata_cache(cache_data):
    """Save the metadata cache to disk."""
    try:
        ensure_cache_dir()
        with open(METADATA_CACHE_FILE, 'w') as f:
            json.dump(cache_data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save metadata cache: {str(e)}")

def get_pattern_metadata(pattern_file):
    """Get cached metadata for a pattern file."""
    cache_data = load_metadata_cache()
    
    # Check if we have cached metadata and if the file hasn't changed
    if pattern_file in cache_data:
        cached_entry = cache_data[pattern_file]
        pattern_path = os.path.join(THETA_RHO_DIR, pattern_file)
        
        try:
            file_mtime = os.path.getmtime(pattern_path)
            if cached_entry.get('mtime') == file_mtime:
                return cached_entry.get('metadata')
        except OSError:
            pass
    
    return None

def cache_pattern_metadata(pattern_file, first_coord, last_coord, total_coords):
    """Cache metadata for a pattern file."""
    try:
        cache_data = load_metadata_cache()
        pattern_path = os.path.join(THETA_RHO_DIR, pattern_file)
        file_mtime = os.path.getmtime(pattern_path)
        
        cache_data[pattern_file] = {
            'mtime': file_mtime,
            'metadata': {
                'first_coordinate': first_coord,
                'last_coordinate': last_coord,
                'total_coordinates': total_coords
            }
        }
        
        save_metadata_cache(cache_data)
        logger.debug(f"Cached metadata for {pattern_file}")
    except Exception as e:
        logger.warning(f"Failed to cache metadata for {pattern_file}: {str(e)}")

def needs_cache(pattern_file):
    """Check if a pattern file needs its cache generated."""
    # Check if image preview exists
    cache_path = get_cache_path(pattern_file)
    if not os.path.exists(cache_path):
        return True
        
    # Check if metadata cache exists and is valid
    metadata = get_pattern_metadata(pattern_file)
    if metadata is None:
        return True
        
    return False

async def generate_image_preview(pattern_file):
    """Generate image preview for a single pattern file."""
    from modules.core.preview import generate_preview_image
    from modules.core.pattern_manager import parse_theta_rho_file
    
    try:
        logger.debug(f"Starting preview generation for {pattern_file}")
        
        # Check if we need to update metadata cache
        metadata = get_pattern_metadata(pattern_file)
        if metadata is None:
            # Parse file to get metadata (this is the only time we need to parse)
            logger.debug(f"Parsing {pattern_file} for metadata cache")
            pattern_path = os.path.join(THETA_RHO_DIR, pattern_file)
            
            try:
                coordinates = await asyncio.to_thread(parse_theta_rho_file, pattern_path)
                
                if coordinates:
                    first_coord = {"x": coordinates[0][0], "y": coordinates[0][1]}
                    last_coord = {"x": coordinates[-1][0], "y": coordinates[-1][1]}
                    total_coords = len(coordinates)
                    
                    # Cache the metadata for future use
                    cache_pattern_metadata(pattern_file, first_coord, last_coord, total_coords)
                    logger.debug(f"Metadata cached for {pattern_file}: {total_coords} coordinates")
                else:
                    logger.warning(f"No coordinates found in {pattern_file}")
            except Exception as e:
                logger.error(f"Failed to parse {pattern_file} for metadata: {str(e)}")
                # Continue with image generation even if metadata fails
        
        # Check if we need to generate the image
        cache_path = get_cache_path(pattern_file)
        if os.path.exists(cache_path):
            logger.debug(f"Skipping image generation for {pattern_file} - already cached")
            return True
            
        # Generate the image
        logger.debug(f"Generating image preview for {pattern_file}")
        image_content = await generate_preview_image(pattern_file)
        
        if not image_content:
            logger.error(f"Generated image content is empty for {pattern_file}")
            return False
        
        # Ensure cache directory exists
        ensure_cache_dir()
        
        with open(cache_path, 'wb') as f:
            f.write(image_content)
        
        try:
            os.chmod(cache_path, 0o644)  # More conservative permissions
        except (OSError, PermissionError) as e:
            # Log as debug instead of error since this is not critical
            logger.debug(f"Could not set cache file permissions for {pattern_file}: {str(e)}")
        
        logger.debug(f"Successfully generated preview for {pattern_file}")
        return True
    except Exception as e:
        logger.error(f"Failed to generate image for {pattern_file}: {str(e)}")
        return False

async def generate_all_image_previews():
    """Generate image previews for all pattern files with progress tracking."""
    global cache_progress
    
    try:
        ensure_cache_dir()
        
        pattern_files = [f for f in list_theta_rho_files() if f.endswith('.thr')]
        
        if not pattern_files:
            logger.info("No .thr pattern files found. Skipping image preview generation.")
            return
        
        patterns_to_cache = [f for f in pattern_files if needs_cache(f)]
        total_files = len(patterns_to_cache)
        skipped_files = len(pattern_files) - total_files
        
        if total_files == 0:
            logger.info(f"All {skipped_files} pattern files already have image previews. Skipping image generation.")
            return
            
        # Update progress state
        cache_progress.update({
            "stage": "images",
            "total_files": total_files,
            "processed_files": 0,
            "current_file": "",
            "error": None
        })
        
        logger.info(f"Generating image cache for {total_files} uncached .thr patterns ({skipped_files} already cached)...")
        
        batch_size = 5
        successful = 0
        for i in range(0, total_files, batch_size):
            batch = patterns_to_cache[i:i + batch_size]
            tasks = [generate_image_preview(file) for file in batch]
            results = await asyncio.gather(*tasks)
            successful += sum(1 for r in results if r)
            
            # Update progress
            cache_progress["processed_files"] = min(i + batch_size, total_files)
            if i < total_files:
                cache_progress["current_file"] = patterns_to_cache[min(i + batch_size - 1, total_files - 1)]
            
            # Log progress
            progress = min(i + batch_size, total_files)
            logger.info(f"Image cache generation progress: {progress}/{total_files} files processed")
        
        logger.info(f"Image cache generation completed: {successful}/{total_files} patterns cached successfully, {skipped_files} patterns skipped (already cached)")
        
    except Exception as e:
        logger.error(f"Error during image cache generation: {str(e)}")
        cache_progress["error"] = str(e)
        raise

async def generate_metadata_cache():
    """Generate metadata cache for all pattern files with progress tracking."""
    global cache_progress
    
    try:
        logger.info("Starting metadata cache generation...")
        
        # Get all pattern files using the same function as the rest of the codebase
        pattern_files = list_theta_rho_files()
        
        if not pattern_files:
            logger.info("No pattern files found. Skipping metadata cache generation.")
            return
        
        # Filter out files that already have valid metadata cache
        files_to_process = []
        for file_name in pattern_files:
            if get_pattern_metadata(file_name) is None:
                files_to_process.append(file_name)
        
        total_files = len(files_to_process)
        skipped_files = len(pattern_files) - total_files
        
        if total_files == 0:
            logger.info(f"All {skipped_files} files already have metadata cache. Skipping metadata generation.")
            return
            
        # Update progress state
        cache_progress.update({
            "stage": "metadata",
            "total_files": total_files,
            "processed_files": 0,
            "current_file": "",
            "error": None
        })
        
        logger.info(f"Generating metadata cache for {total_files} new files ({skipped_files} files already cached)...")
        
        # Process in batches
        batch_size = 5
        successful = 0
        for i in range(0, total_files, batch_size):
            batch = files_to_process[i:i + batch_size]
            tasks = []
            for file_name in batch:
                pattern_path = os.path.join(THETA_RHO_DIR, file_name)
                try:
                    # Parse file to get metadata
                    coordinates = await asyncio.to_thread(parse_theta_rho_file, pattern_path)
                    if coordinates:
                        first_coord = {"x": coordinates[0][0], "y": coordinates[0][1]}
                        last_coord = {"x": coordinates[-1][0], "y": coordinates[-1][1]}
                        total_coords = len(coordinates)
                        
                        # Cache the metadata
                        cache_pattern_metadata(file_name, first_coord, last_coord, total_coords)
                        successful += 1
                        logger.debug(f"Generated metadata for {file_name}")
                        
                        # Update current file being processed
                        cache_progress["current_file"] = file_name
                except Exception as e:
                    logger.error(f"Failed to generate metadata for {file_name}: {str(e)}")
            
            # Update progress
            cache_progress["processed_files"] = min(i + batch_size, total_files)
            
            # Log progress
            progress = min(i + batch_size, total_files)
            logger.info(f"Metadata cache generation progress: {progress}/{total_files} files processed")
        
        logger.info(f"Metadata cache generation completed: {successful}/{total_files} patterns cached successfully, {skipped_files} patterns skipped (already cached)")
        
    except Exception as e:
        logger.error(f"Error during metadata cache generation: {str(e)}")
        cache_progress["error"] = str(e)
        raise

async def rebuild_cache():
    """Rebuild the entire cache for all pattern files."""
    logger.info("Starting cache rebuild...")
    
    # Ensure cache directory exists
    ensure_cache_dir()
    
    # First generate metadata cache for all files
    await generate_metadata_cache()
    
    # Then generate image previews
    pattern_files = [f for f in list_theta_rho_files() if f.endswith('.thr')]
    total_files = len(pattern_files)
    
    if total_files == 0:
        logger.info("No pattern files found to cache")
        return
        
    logger.info(f"Generating image previews for {total_files} pattern files...")
    
    # Process in batches
    batch_size = 5
    successful = 0
    for i in range(0, total_files, batch_size):
        batch = pattern_files[i:i + batch_size]
        tasks = [generate_image_preview(file) for file in batch]
        results = await asyncio.gather(*tasks)
        successful += sum(1 for r in results if r)
        
        # Log progress
        progress = min(i + batch_size, total_files)
        logger.info(f"Image preview generation progress: {progress}/{total_files} files processed")
    
    logger.info(f"Cache rebuild completed: {successful}/{total_files} patterns cached successfully")

async def generate_cache_background():
    """Run cache generation in the background with progress tracking."""
    global cache_progress
    
    try:
        cache_progress.update({
            "is_running": True,
            "stage": "starting",
            "total_files": 0,
            "processed_files": 0,
            "current_file": "",
            "error": None
        })
        
        # First generate metadata cache
        await generate_metadata_cache()
        
        # Then generate image previews
        await generate_all_image_previews()
        
        # Mark as complete
        cache_progress.update({
            "is_running": False,
            "stage": "complete",
            "current_file": "",
            "error": None
        })
        
        logger.info("Background cache generation completed successfully")
        
    except Exception as e:
        logger.error(f"Background cache generation failed: {str(e)}")
        cache_progress.update({
            "is_running": False,
            "stage": "error",
            "error": str(e)
        })
        raise

def get_cache_progress():
    """Get the current cache generation progress."""
    global cache_progress
    return cache_progress.copy()

def is_cache_generation_needed():
    """Check if cache generation is needed."""
    pattern_files = [f for f in list_theta_rho_files() if f.endswith('.thr')]
    
    if not pattern_files:
        return False
    
    # Check if any files need caching
    patterns_to_cache = [f for f in pattern_files if needs_cache(f)]
    
    # Check metadata cache
    files_needing_metadata = []
    for file_name in pattern_files:
        if get_pattern_metadata(file_name) is None:
            files_needing_metadata.append(file_name)
    
    return len(patterns_to_cache) > 0 or len(files_needing_metadata) > 0