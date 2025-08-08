"""
Version management for Dune Weaver
Handles current version reading and GitHub API integration for latest version checking
"""

import asyncio
import aiohttp
import json
import os
from pathlib import Path
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class VersionManager:
    def __init__(self):
        self.repo_owner = "tuanchris"
        self.repo_name = "dune-weaver"
        self.github_api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}"
        self._current_version = None
        
    def get_current_version(self) -> str:
        """Read current version from VERSION file"""
        if self._current_version is None:
            try:
                version_file = Path(__file__).parent.parent.parent / "VERSION"
                if version_file.exists():
                    self._current_version = version_file.read_text().strip()
                else:
                    logger.warning("VERSION file not found, using default version")
                    self._current_version = "1.0.0"
            except Exception as e:
                logger.error(f"Error reading VERSION file: {e}")
                self._current_version = "1.0.0"
        
        return self._current_version
    
    async def get_latest_release(self) -> Dict[str, any]:
        """Get latest release info from GitHub API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.github_api_url}/releases/latest",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "version": data.get("tag_name", "").lstrip("v"),
                            "name": data.get("name", ""),
                            "published_at": data.get("published_at", ""),
                            "html_url": data.get("html_url", ""),
                            "body": data.get("body", ""),
                            "prerelease": data.get("prerelease", False)
                        }
                    elif response.status == 404:
                        # No releases found
                        logger.info("No releases found on GitHub")
                        return None
                    else:
                        logger.warning(f"GitHub API returned status {response.status}")
                        return None
                        
        except asyncio.TimeoutError:
            logger.warning("Timeout while fetching latest release from GitHub")
            return None
        except Exception as e:
            logger.error(f"Error fetching latest release: {e}")
            return None
    
    def compare_versions(self, version1: str, version2: str) -> int:
        """Compare two semantic versions. Returns -1, 0, or 1"""
        try:
            # Parse semantic versions (e.g., "1.2.3")
            v1_parts = [int(x) for x in version1.split('.')]
            v2_parts = [int(x) for x in version2.split('.')]
            
            # Pad shorter version with zeros
            max_len = max(len(v1_parts), len(v2_parts))
            v1_parts.extend([0] * (max_len - len(v1_parts)))
            v2_parts.extend([0] * (max_len - len(v2_parts)))
            
            if v1_parts < v2_parts:
                return -1
            elif v1_parts > v2_parts:
                return 1
            else:
                return 0
                
        except (ValueError, AttributeError):
            logger.warning(f"Invalid version format: {version1} vs {version2}")
            return 0
    
    async def get_version_info(self) -> Dict[str, any]:
        """Get complete version information"""
        current = self.get_current_version()
        latest_release = await self.get_latest_release()
        
        if latest_release:
            latest = latest_release["version"]
            comparison = self.compare_versions(current, latest)
            update_available = comparison < 0
        else:
            latest = current  # Fallback if no releases found
            update_available = False
            
        return {
            "current": current,
            "latest": latest,
            "update_available": update_available,
            "latest_release": latest_release
        }

# Global instance
version_manager = VersionManager()