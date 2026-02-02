import subprocess
import logging

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

def update_software():
    """Update the software to the latest version.

    This runs inside the Docker container, so it:
    1. Pulls latest code via git (mounted volume at /app)
    2. Pulls new Docker image for the backend
    3. Restarts the container to apply updates

    Note: For a complete update including container recreation,
    run 'dw update' from the host machine instead.
    """
    error_log = []
    logger.info("Starting software update process")

    def run_command(command, error_message, capture_output=False, cwd=None):
        try:
            logger.debug(f"Running command: {' '.join(command)}")
            result = subprocess.run(command, check=True, capture_output=capture_output, text=True, cwd=cwd)
            return result.stdout if capture_output else True
        except subprocess.CalledProcessError as e:
            logger.error(f"{error_message}: {e}")
            error_log.append(error_message)
            return None

    # Step 1: Pull latest code via git (works because /app is mounted from host)
    logger.info("Pulling latest code from git...")
    git_result = run_command(
        ["git", "pull", "--ff-only"],
        "Failed to pull latest code from git",
        cwd="/app"
    )
    if git_result:
        logger.info("Git pull completed successfully")

    # Step 2: Pull new Docker image for the backend only
    # Note: There is no separate frontend image - it's either bundled or built locally
    logger.info("Pulling latest Docker image...")
    run_command(
        ["docker", "pull", "ghcr.io/tuanchris/dune-weaver:main"],
        "Failed to pull backend Docker image"
    )

    # Step 3: Restart the backend container to apply updates
    # We can't recreate ourselves from inside the container, so we just restart
    # For full container recreation with new images, use 'dw update' from host
    logger.info("Restarting backend container...")

    # Use docker restart which works from inside the container
    restart_result = run_command(
        ["docker", "restart", "dune-weaver-backend"],
        "Failed to restart backend container"
    )

    if not restart_result:
        # If docker restart fails, try a graceful approach
        logger.info("Attempting graceful restart via compose...")
        try:
            # Just restart, don't try to recreate (which would fail)
            subprocess.run(
                ["docker", "compose", "restart", "backend"],
                check=True,
                cwd="/app"
            )
            logger.info("Container restarted successfully via compose")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.warning(f"Compose restart also failed: {e}")
            error_log.append("Container restart failed - please run 'dw update' from host")

    if error_log:
        logger.error(f"Software update completed with errors: {error_log}")
        return False, "Update completed with errors. For best results, run 'dw update' from the host machine.", error_log

    logger.info("Software update completed successfully")
    return True, None, None
