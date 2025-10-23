import os
import subprocess
import logging
from typing import Dict, List, Optional, Tuple, Callable

# Configure logging
logger = logging.getLogger(__name__)

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

def list_available_versions() -> Dict[str, List[str]]:
    """List all available Git tags and branches."""
    try:
        logger.debug("Fetching available versions")
        # Fetch latest from remote
        subprocess.run(["git", "fetch", "--all", "--tags", "--force"], check=True, capture_output=True)

        # Get all tags, sorted by version (newest first)
        tags_output = subprocess.check_output(
            ["git", "tag", "--sort=-version:refname"],
            text=True
        ).strip()
        tags = [tag for tag in tags_output.split('\n') if tag]

        # Get all remote branches
        branches_output = subprocess.check_output(
            ["git", "branch", "-r", "--format=%(refname:short)"],
            text=True
        ).strip()
        # Filter out HEAD and extract branch names
        branches = []
        for branch in branches_output.split('\n'):
            if branch and not branch.endswith('/HEAD'):
                # Remove 'origin/' prefix
                branch_name = branch.replace('origin/', '')
                if branch_name not in ['HEAD']:
                    branches.append(branch_name)

        logger.info(f"Found {len(tags)} tags and {len(branches)} branches")
        return {
            "tags": tags,
            "branches": branches
        }
    except subprocess.CalledProcessError as e:
        logger.error(f"Error listing versions: {e}")
        return {
            "tags": [],
            "branches": []
        }

def update_software(version: Optional[str] = None, log_callback: Optional[Callable[[str], None]] = None):
    """Update the software to the specified version or latest."""
    error_log = []

    def log(message: str):
        """Log message and call callback if provided."""
        logger.info(message)
        if log_callback:
            log_callback(message)

    log("Starting software update process")

    def run_command_with_output(command, description):
        """Run command and stream output to log callback."""
        try:
            log(f"Running: {description}")
            log(f"Command: {' '.join(command)}")

            # Run command and capture output in real-time
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            # Stream output line by line
            for line in iter(process.stdout.readline, ''):
                if line:
                    log(line.rstrip())

            process.wait()

            if process.returncode != 0:
                error_msg = f"{description} failed with return code {process.returncode}"
                log(f"ERROR: {error_msg}")
                error_log.append(error_msg)
                return False

            log(f"✓ {description} completed successfully")
            return True

        except Exception as e:
            error_msg = f"{description} failed: {str(e)}"
            log(f"ERROR: {error_msg}")
            error_log.append(error_msg)
            return False

    # Determine target version
    try:
        log("Fetching latest version information...")
        subprocess.run(["git", "fetch", "--all", "--tags", "--force"], check=True, capture_output=True)

        if not version or version == "latest":
            # Get latest tag
            target_version = subprocess.check_output(
                ["git", "describe", "--tags", "--abbrev=0", "origin/main"]
            ).strip().decode()
            log(f"Target version: {target_version} (latest)")
        else:
            target_version = version
            log(f"Target version: {target_version} (user selected)")

    except subprocess.CalledProcessError as e:
        error_msg = f"Failed to fetch version information: {e}"
        log(f"ERROR: {error_msg}")
        error_log.append(error_msg)
        return False, error_msg, error_log

    # Pull Docker images
    if not run_command_with_output(
        ["docker", "compose", "pull"],
        "Pulling Docker images"
    ):
        return False, "Failed to pull Docker images", error_log

    # Checkout target version
    if not run_command_with_output(
        ["git", "checkout", target_version, "--force"],
        f"Checking out version {target_version}"
    ):
        return False, f"Failed to checkout version {target_version}", error_log

    # Restart Docker containers
    if not run_command_with_output(
        ["docker", "compose", "up", "-d", "--remove-orphans"],
        "Restarting Docker containers"
    ):
        return False, "Failed to restart Docker containers", error_log

    log("✓ Software update completed successfully!")
    log(f"System is now running version: {target_version}")

    return True, None, None
