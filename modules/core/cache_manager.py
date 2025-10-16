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

# Cache schema version - increment when structure changes
CACHE_SCHEMA_VERSION = 1

# Expected cache schema structure
EXPECTED_CACHE_SCHEMA = {
    'version': CACHE_SCHEMA_VERSION,
    'structure': {
        'mtime': 'number',
        'metadata': {
            'first_coordinate': {'x': 'number', 'y': 'number'},
            'last_coordinate': {'x': 'number', 'y': 'number'},
            'total_coordinates': 'number'
        }
    }
}

def validate_cache_schema(cache_data):
    """Validate that cache data matches the expected schema structure."""
    try:
        # Check if version info exists
        if not isinstance(cache_data, dict):
            return False
        
        # Check for version field - if missing, it's old format
        cache_version = cache_data.get('version')
        if cache_version is None:
            logger.info("Cache file missing version info - treating as outdated schema")
            return False
        
        # Check if version matches current expected version
        if cache_version != CACHE_SCHEMA_VERSION:
            logger.info(f"Cache schema version mismatch: found {cache_version}, expected {CACHE_SCHEMA_VERSION}")
            return False
        
        # Check if data section exists
        if 'data' not in cache_data:
            logger.warning("Cache file missing 'data' section")
            return False
        
        # Validate structure of a few entries if they exist
        data_section = cache_data.get('data', {})
        if data_section and isinstance(data_section, dict):
            # Check first entry structure
            for pattern_file, entry in list(data_section.items())[:1]:  # Just check first entry
                if not isinstance(entry, dict):
                    return False
                if 'mtime' not in entry or 'metadata' not in entry:
                    return False
                metadata = entry.get('metadata', {})
                required_fields = ['first_coordinate', 'last_coordinate', 'total_coordinates']
                if not all(field in metadata for field in required_fields):
                    return False
                # Validate coordinate structure
                for coord_field in ['first_coordinate', 'last_coordinate']:
                    coord = metadata.get(coord_field)
                    if not isinstance(coord, dict) or 'x' not in coord or 'y' not in coord:
                        return False
        
        return True
    except Exception as e:
        logger.warning(f"Error validating cache schema: {str(e)}")
        return False

def invalidate_cache():
    """Delete only the metadata cache file, preserving image cache."""
    try:
        # Delete metadata cache file only
        if os.path.exists(METADATA_CACHE_FILE):
            os.remove(METADATA_CACHE_FILE)
            logger.info("Deleted outdated metadata cache file")
        
        # Keep image cache directory intact - images are still valid
        # Just ensure the cache directory structure exists
        ensure_cache_dir()
        
        return True
    except Exception as e:
        logger.error(f"Failed to invalidate metadata cache: {str(e)}")
        return False

async def invalidate_cache_async():
    """Async version: Delete only the metadata cache file, preserving image cache."""
    try:
        # Delete metadata cache file only
        if await asyncio.to_thread(os.path.exists, METADATA_CACHE_FILE):
            await asyncio.to_thread(os.remove, METADATA_CACHE_FILE)
            logger.info("Deleted outdated metadata cache file")
        
        # Keep image cache directory intact - images are still valid
        # Just ensure the cache directory structure exists
        await ensure_cache_dir_async()
        
        return True
    except Exception as e:
        logger.error(f"Failed to invalidate metadata cache: {str(e)}")
        return False

def ensure_cache_dir():
    """Ensure the cache directory exists with proper permissions."""
    try:
        Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
        
        # Initialize metadata cache if it doesn't exist
        if not os.path.exists(METADATA_CACHE_FILE):
            initial_cache = {
                'version': CACHE_SCHEMA_VERSION,
                'data': {}
            }
            with open(METADATA_CACHE_FILE, 'w') as f:
                json.dump(initial_cache, f)
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

async def ensure_cache_dir_async():
    """Async version: Ensure the cache directory exists with proper permissions."""
    try:
        await asyncio.to_thread(Path(CACHE_DIR).mkdir, parents=True, exist_ok=True)
        
        # Initialize metadata cache if it doesn't exist
        if not await asyncio.to_thread(os.path.exists, METADATA_CACHE_FILE):
            initial_cache = {
                'version': CACHE_SCHEMA_VERSION,
                'data': {}
            }
            def _write_initial_cache():
                with open(METADATA_CACHE_FILE, 'w') as f:
                    json.dump(initial_cache, f)
            
            await asyncio.to_thread(_write_initial_cache)
            try:
                await asyncio.to_thread(os.chmod, METADATA_CACHE_FILE, 0o644)
            except (OSError, PermissionError) as e:
                logger.debug(f"Could not set metadata cache file permissions: {str(e)}")
        
        def _set_permissions():
            for root, dirs, files in os.walk(CACHE_DIR):
                try:
                    os.chmod(root, 0o755)
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            os.chmod(file_path, 0o644)
                        except (OSError, PermissionError) as e:
                            logger.debug(f"Could not set permissions for file {file_path}: {str(e)}")
                except (OSError, PermissionError) as e:
                    logger.debug(f"Could not set permissions for directory {root}: {str(e)}")
                    continue
        
        await asyncio.to_thread(_set_permissions)
                
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
        data_section = metadata_cache.get('data', {})
        if pattern_file in data_section:
            del data_section[pattern_file]
            metadata_cache['data'] = data_section
            save_metadata_cache(metadata_cache)
            logger.info(f"Removed {pattern_file} from metadata cache")
        
        return True
    except Exception as e:
        logger.error(f"Failed to delete cache for {pattern_file}: {str(e)}")
        return False

def load_metadata_cache():
    """Load the metadata cache from disk with schema validation."""
    try:
        if os.path.exists(METADATA_CACHE_FILE):
            with open(METADATA_CACHE_FILE, 'r') as f:
                cache_data = json.load(f)
            
            # Validate schema
            if not validate_cache_schema(cache_data):
                logger.info("Cache schema validation failed - invalidating cache")
                invalidate_cache()
                # Return empty cache structure after invalidation
                return {
                    'version': CACHE_SCHEMA_VERSION,
                    'data': {}
                }
            
            return cache_data
    except Exception as e:
        logger.warning(f"Failed to load metadata cache: {str(e)} - invalidating cache")
        try:
            invalidate_cache()
        except Exception as invalidate_error:
            logger.error(f"Failed to invalidate corrupted cache: {str(invalidate_error)}")
    
    # Return empty cache structure
    return {
        'version': CACHE_SCHEMA_VERSION,
        'data': {}
    }

async def load_metadata_cache_async():
    """Async version: Load the metadata cache from disk with schema validation."""
    try:
        if await asyncio.to_thread(os.path.exists, METADATA_CACHE_FILE):
            def _load_json():
                with open(METADATA_CACHE_FILE, 'r') as f:
                    return json.load(f)
            
            cache_data = await asyncio.to_thread(_load_json)
            
            # Validate schema
            if not validate_cache_schema(cache_data):
                logger.info("Cache schema validation failed - invalidating cache")
                await invalidate_cache_async()
                # Return empty cache structure after invalidation
                return {
                    'version': CACHE_SCHEMA_VERSION,
                    'data': {}
                }
            
            return cache_data
    except Exception as e:
        logger.warning(f"Failed to load metadata cache: {str(e)} - invalidating cache")
        try:
            await invalidate_cache_async()
        except Exception as invalidate_error:
            logger.error(f"Failed to invalidate corrupted cache: {str(invalidate_error)}")
    
    # Return empty cache structure
    return {
        'version': CACHE_SCHEMA_VERSION,
        'data': {}
    }

def save_metadata_cache(cache_data):
    """Save the metadata cache to disk with version info."""
    try:
        ensure_cache_dir()
        
        # Ensure cache data has proper structure
        if not isinstance(cache_data, dict) or 'version' not in cache_data:
            # Convert old format or create new structure
            if isinstance(cache_data, dict) and 'data' not in cache_data:
                # Old format - wrap existing data
                structured_cache = {
                    'version': CACHE_SCHEMA_VERSION,
                    'data': cache_data
                }
            else:
                structured_cache = cache_data
        else:
            structured_cache = cache_data
        
        with open(METADATA_CACHE_FILE, 'w') as f:
            json.dump(structured_cache, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save metadata cache: {str(e)}")

def get_pattern_metadata(pattern_file):
    """Get cached metadata for a pattern file."""
    cache_data = load_metadata_cache()
    data_section = cache_data.get('data', {})
    
    # Check if we have cached metadata and if the file hasn't changed
    if pattern_file in data_section:
        cached_entry = data_section[pattern_file]
        pattern_path = os.path.join(THETA_RHO_DIR, pattern_file)
        
        try:
            file_mtime = os.path.getmtime(pattern_path)
            if cached_entry.get('mtime') == file_mtime:
                return cached_entry.get('metadata')
        except OSError:
            pass
    
    return None

async def get_pattern_metadata_async(pattern_file):
    """Async version: Get cached metadata for a pattern file."""
    cache_data = await load_metadata_cache_async()
    data_section = cache_data.get('data', {})
    
    # Check if we have cached metadata and if the file hasn't changed
    if pattern_file in data_section:
        cached_entry = data_section[pattern_file]
        pattern_path = os.path.join(THETA_RHO_DIR, pattern_file)
        
        try:
            file_mtime = await asyncio.to_thread(os.path.getmtime, pattern_path)
            if cached_entry.get('mtime') == file_mtime:
                return cached_entry.get('metadata')
        except OSError:
            pass
    
    return None

def cache_pattern_metadata(pattern_file, first_coord, last_coord, total_coords):
    """Cache metadata for a pattern file."""
    try:
        cache_data = load_metadata_cache()
        data_section = cache_data.get('data', {})
        pattern_path = os.path.join(THETA_RHO_DIR, pattern_file)
        file_mtime = os.path.getmtime(pattern_path)
        
        data_section[pattern_file] = {
            'mtime': file_mtime,
            'metadata': {
                'first_coordinate': first_coord,
                'last_coordinate': last_coord,
                'total_coordinates': total_coords
            }
        }
        
        cache_data['data'] = data_section
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

def needs_image_cache_only(pattern_file):
    """Quick check if a pattern file needs its image cache generated.
    
    Only checks for image file existence, not metadata validity.
    Used during startup for faster checking.
    """
    cache_path = get_cache_path(pattern_file)
    return not os.path.exists(cache_path)

async def needs_cache_async(pattern_file):
    """Async version: Check if a pattern file needs its cache generated."""
    # Check if image preview exists
    cache_path = get_cache_path(pattern_file)
    if not await asyncio.to_thread(os.path.exists, cache_path):
        return True
        
    # Check if metadata cache exists and is valid
    metadata = await get_pattern_metadata_async(pattern_file)
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
    """Generate image previews for missing patterns using set difference."""
    global cache_progress
    
    try:
        await ensure_cache_dir_async()
        
        # Step 1: Get all pattern files
        pattern_files = await list_theta_rho_files_async()
        
        if not pattern_files:
            logger.info("No .thr pattern files found. Skipping image preview generation.")
            return
        
        # Step 2: Find patterns with existing cache
        def _find_cached_patterns():
            cached = set()
            for pattern in pattern_files:
                cache_path = get_cache_path(pattern)
                if os.path.exists(cache_path):
                    cached.add(pattern)
            return cached
        
        cached_patterns = await asyncio.to_thread(_find_cached_patterns)
        
        # Step 3: Calculate delta (patterns missing image cache)
        pattern_set = set(pattern_files)
        patterns_to_cache = list(pattern_set - cached_patterns)
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
    """Generate metadata cache for missing patterns using set difference."""
    global cache_progress
    
    try:
        logger.info("Starting metadata cache generation...")
        
        # Step 1: Get all pattern files
        pattern_files = await list_theta_rho_files_async()
        
        if not pattern_files:
            logger.info("No pattern files found. Skipping metadata cache generation.")
            return
        
        # Step 2: Get existing metadata keys
        metadata_cache = await load_metadata_cache_async()
        existing_keys = set(metadata_cache.get('data', {}).keys())
        
        # Step 3: Calculate delta (patterns missing from metadata)
        pattern_set = set(pattern_files)
        files_to_process = list(pattern_set - existing_keys)
        
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
        
        # Process in smaller batches for Pi Zero 2 W
        batch_size = 3  # Reduced from 5
        successful = 0
        for i in range(0, total_files, batch_size):
            batch = files_to_process[i:i + batch_size]
            
            # Process files sequentially within batch (no parallel tasks)
            for file_name in batch:
                pattern_path = os.path.join(THETA_RHO_DIR, file_name)
                cache_progress["current_file"] = file_name
                
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
                        
                    # Small delay to reduce I/O pressure
                    await asyncio.sleep(0.05)
                    
                except Exception as e:
                    logger.error(f"Failed to generate metadata for {file_name}: {str(e)}")
            
            # Update progress
            cache_progress["processed_files"] = min(i + batch_size, total_files)
            
            # Log progress
            progress = min(i + batch_size, total_files)
            logger.info(f"Metadata cache generation progress: {progress}/{total_files} files processed")
            
            # Delay between batches for system recovery
            if i + batch_size < total_files:
                await asyncio.sleep(0.3)
        
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
    """Get the current cache generation progress.

    Returns a reference to the cache_progress dict for read-only access.
    The WebSocket handler should not modify this dict.
    """
    global cache_progress
    return cache_progress  # Return reference instead of copy for better performance

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

async def is_cache_generation_needed_async():
    """Check if cache generation is needed using simple set difference.
    
    Returns True if any patterns are missing from either metadata or image cache.
    """
    try:
        # Step 1: List all patterns
        pattern_files = await list_theta_rho_files_async()
        if not pattern_files:
            return False
        
        pattern_set = set(pattern_files)
        
        # Step 2: Check metadata cache
        metadata_cache = await load_metadata_cache_async()
        metadata_keys = set(metadata_cache.get('data', {}).keys())
        
        if pattern_set != metadata_keys:
            # Metadata is missing some patterns
            return True
        
        # Step 3: Check image cache
        def _list_cached_images():
            """List all patterns that have cached images."""
            cached = set()
            if os.path.exists(CACHE_DIR):
                for pattern in pattern_files:
                    cache_path = get_cache_path(pattern)
                    if os.path.exists(cache_path):
                        cached.add(pattern)
            return cached
        
        cached_images = await asyncio.to_thread(_list_cached_images)
        
        if pattern_set != cached_images:
            # Some patterns missing image cache
            return True
        
        return False
        
    except Exception as e:
        logger.warning(f"Error checking cache status: {e}")
        return False  # Don't block startup on errors

async def list_theta_rho_files_async():
    """Async version: List all theta-rho files."""
    def _walk_files():
        files = []
        for root, _, filenames in os.walk(THETA_RHO_DIR):
            # Only process .thr files to reduce memory usage
            thr_files = [f for f in filenames if f.endswith('.thr')]
            for file in thr_files:
                relative_path = os.path.relpath(os.path.join(root, file), THETA_RHO_DIR)
                # Normalize path separators to always use forward slashes for consistency across platforms
                relative_path = relative_path.replace(os.sep, '/')
                files.append(relative_path)
        return files
    
    files = await asyncio.to_thread(_walk_files)
    logger.debug(f"Found {len(files)} theta-rho files")
    return files  # Already filtered for .thr