import subprocess
import logging
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

# Configure logging
logger = logging.getLogger(__name__)

# Trigger file location - visible to both container (/app) and host
TRIGGER_FILE = Path("/app/.update-trigger")


def check_git_updates():
    """Check for available Git updates."""
    try:
        logger.debug("Checking for Git updates")
        subprocess.run(["git", "fetch", "--tags", "--force"], check=True)
        latest_remote_tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0", "origin/main"]
        ).strip().decode()
        latest_local_tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0"]
        ).strip().decode()

        tag_behind_count = 0
        if latest_local_tag != latest_remote_tag:
            tags = subprocess.check_output(
                ["git", "tag", "--merged", "origin/main"], text=True
            ).splitlines()

            found_local = False
            for tag in tags:
                if tag == latest_local_tag:
                    found_local = True
                elif found_local:
                    tag_behind_count += 1
                    if tag == latest_remote_tag:
                        break

        updates_available = latest_remote_tag != latest_local_tag
        logger.info(f"Updates available: {updates_available}, {tag_behind_count} versions behind")

        return {
            "updates_available": updates_available,
            "tag_behind_count": tag_behind_count,
            "latest_remote_tag": latest_remote_tag,
            "latest_local_tag": latest_local_tag,
        }
    except subprocess.CalledProcessError as e:
        logger.error(f"Error checking Git updates: {e}")
        return {
            "updates_available": False,
            "tag_behind_count": 0,
            "latest_remote_tag": None,
            "latest_local_tag": None,
        }


def is_update_watcher_available() -> bool:
    """Check if the update watcher service is running on the host.

    The watcher service monitors the trigger file and runs 'dw update'
    when it detects a trigger.
    """
    # The watcher is available if we can write to the trigger file location
    # and the parent directory exists (indicating proper volume mount)
    try:
        return TRIGGER_FILE.parent.exists() and os.access(TRIGGER_FILE.parent, os.W_OK)
    except Exception:
        return False


def trigger_host_update(message: str = None) -> Tuple[bool, Optional[str]]:
    """Signal the host to run 'dw update' by creating a trigger file.

    The update watcher service on the host monitors this file and
    executes the full update process when triggered.

    Args:
        message: Optional message to include in the trigger file

    Returns:
        Tuple of (success, error_message)
    """
    try:
        # Write trigger file with timestamp and optional message
        trigger_content = f"triggered_at={datetime.now().isoformat()}\n"
        if message:
            trigger_content += f"message={message}\n"

        TRIGGER_FILE.write_text(trigger_content)
        logger.info(f"Update trigger created at {TRIGGER_FILE}")
        return True, None
    except Exception as e:
        error_msg = f"Failed to create update trigger: {e}"
        logger.error(error_msg)
        return False, error_msg


def update_software():
    """Trigger a software update on the host machine.

    When running in Docker, this creates a trigger file that the host's
    update-watcher service monitors. The watcher then runs 'dw update'
    on the host, which properly handles:
    - Git pull for latest code
    - Docker image pulls
    - Container recreation with new images
    - Cleanup of old images

    Returns:
        Tuple of (success, error_message, error_log)
    """
    logger.info("Initiating software update...")

    # Check if we can trigger host update
    if not is_update_watcher_available():
        error_msg = (
            "Update watcher not available. The update-watcher service may not be "
            "installed or the volume mount is not configured correctly. "
            "Please run 'dw update' manually from the host machine."
        )
        logger.error(error_msg)
        return False, error_msg, [error_msg]

    # Trigger the host update
    success, error = trigger_host_update("Triggered from web UI")

    if success:
        logger.info("Update triggered successfully - host will process shortly")
        return True, None, None
    else:
        return False, error, [error]
