"""PNG Cache Manager for dune-weaver-touch

Converts WebP previews to PNG format for optimal Qt/QML compatibility.
"""

import asyncio
import os
import logging
from pathlib import Path
from typing import List, Tuple
try:
    from PIL import Image
except ImportError:
    Image = None

logger = logging.getLogger(__name__)

class PngCacheManager:
    """Manages PNG cache generation from WebP sources for touch interface"""
    
    def __init__(self, cache_dir: Path = None):
        # Default to the main cache directory relative to touch app
        self.cache_dir = cache_dir or Path("../patterns/cached_images")
        self.conversion_stats = {
            "total_webp_found": 0,
            "png_already_exist": 0,
            "converted_successfully": 0,
            "conversion_errors": 0
        }
    
    async def ensure_png_cache_available(self) -> bool:
        """
        Ensure PNG previews are available for all WebP files.
        Returns True if all conversions completed successfully.
        """
        if not Image:
            logger.error("PIL (Pillow) not available - cannot convert WebP to PNG")
            return False
        
        if not self.cache_dir.exists():
            logger.info(f"Cache directory {self.cache_dir} does not exist - no conversion needed")
            return True
        
        logger.info(f"Starting PNG cache check for directory: {self.cache_dir}")
        
        # Find all WebP files that need PNG conversion
        webp_files = await self._find_webp_files_needing_conversion()
        
        if not webp_files:
            logger.info("All WebP files already have PNG equivalents")
            return True
        
        logger.info(f"Found {len(webp_files)} WebP files needing PNG conversion")
        
        # Convert WebP files to PNG in batches
        success = await self._convert_webp_to_png_batch(webp_files)
        
        # Log conversion statistics
        self._log_conversion_stats()
        
        return success
    
    async def _find_webp_files_needing_conversion(self) -> List[Path]:
        """Find WebP files that don't have corresponding PNG files"""
        def _scan_webp():
            webp_files = []
            for webp_file in self.cache_dir.rglob("*.webp"):
                # Check if corresponding PNG exists
                png_file = webp_file.with_suffix(".png")
                if not png_file.exists():
                    webp_files.append(webp_file)
                else:
                    self.conversion_stats["png_already_exist"] += 1
                self.conversion_stats["total_webp_found"] += 1
            return webp_files
        
        return await asyncio.to_thread(_scan_webp)
    
    async def _convert_webp_to_png_batch(self, webp_files: List[Path]) -> bool:
        """Convert WebP files to PNG in parallel batches"""
        batch_size = 5  # Process 5 files at a time to avoid overwhelming the system
        all_success = True
        
        for i in range(0, len(webp_files), batch_size):
            batch = webp_files[i:i + batch_size]
            batch_tasks = [self._convert_single_webp_to_png(webp_file) for webp_file in batch]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            # Check results
            for webp_file, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Failed to convert {webp_file}: {result}")
                    self.conversion_stats["conversion_errors"] += 1
                    all_success = False
                elif result:
                    self.conversion_stats["converted_successfully"] += 1
                    logger.debug(f"Converted {webp_file} to PNG")
                else:
                    self.conversion_stats["conversion_errors"] += 1
                    all_success = False
            
            # Log progress
            processed = min(i + batch_size, len(webp_files))
            logger.info(f"PNG conversion progress: {processed}/{len(webp_files)} files processed")
        
        return all_success
    
    async def _convert_single_webp_to_png(self, webp_file: Path) -> bool:
        """Convert a single WebP file to PNG format"""
        try:
            png_file = webp_file.with_suffix(".png")
            
            def _convert():
                # Open WebP image and convert to PNG
                with Image.open(webp_file) as img:
                    # Convert to RGB if necessary (PNG doesn't support some WebP modes)
                    if img.mode in ('RGBA', 'LA', 'P'):
                        # Keep transparency for these modes
                        img.save(png_file, "PNG", optimize=True)
                    else:
                        # Convert to RGB for other modes
                        rgb_img = img.convert('RGB')
                        rgb_img.save(png_file, "PNG", optimize=True)
                
                # Set file permissions to match the WebP file
                try:
                    webp_stat = webp_file.stat()
                    os.chmod(png_file, webp_stat.st_mode)
                except (OSError, PermissionError):
                    # Not critical if we can't set permissions
                    pass
            
            await asyncio.to_thread(_convert)
            return True
            
        except Exception as e:
            logger.error(f"Failed to convert {webp_file} to PNG: {e}")
            return False
    
    def _log_conversion_stats(self):
        """Log conversion statistics"""
        stats = self.conversion_stats
        logger.info("PNG Cache Conversion Statistics:")
        logger.info(f"  Total WebP files found: {stats['total_webp_found']}")
        logger.info(f"  PNG files already existed: {stats['png_already_exist']}")
        logger.info(f"  Files converted successfully: {stats['converted_successfully']}")
        logger.info(f"  Conversion errors: {stats['conversion_errors']}")
        
        if stats['conversion_errors'] > 0:
            logger.warning(f"⚠️ {stats['conversion_errors']} files failed to convert")
        else:
            logger.info("✅ All WebP to PNG conversions completed successfully")
    
    async def convert_specific_pattern(self, pattern_name: str) -> bool:
        """Convert a specific pattern's WebP to PNG if needed"""
        if not Image:
            return False
        
        # Handle both hierarchical and flat naming conventions
        webp_files = []
        
        # Try hierarchical structure first
        webp_hierarchical = self.cache_dir / f"{pattern_name}.webp"
        if webp_hierarchical.exists():
            png_hierarchical = webp_hierarchical.with_suffix(".png")
            if not png_hierarchical.exists():
                webp_files.append(webp_hierarchical)
        
        # Try flattened structure
        pattern_name_flat = pattern_name.replace("/", "_").replace("\\", "_")
        webp_flat = self.cache_dir / f"{pattern_name_flat}.webp"
        if webp_flat.exists():
            png_flat = webp_flat.with_suffix(".png")
            if not png_flat.exists():
                webp_files.append(webp_flat)
        
        if not webp_files:
            return True  # No conversion needed
        
        # Convert found WebP files
        tasks = [self._convert_single_webp_to_png(webp_file) for webp_file in webp_files]
        results = await asyncio.gather(*tasks)
        
        return all(results)


async def ensure_png_cache_startup():
    """
    Startup function to ensure PNG cache is available.
    Call this during application startup.
    """
    try:
        cache_manager = PngCacheManager()
        success = await cache_manager.ensure_png_cache_available()
        
        if success:
            logger.info("PNG cache startup check completed successfully")
        else:
            logger.warning("PNG cache startup check completed with some errors")
        
        return success
    except Exception as e:
        logger.error(f"PNG cache startup check failed: {e}")
        return False