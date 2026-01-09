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
    """Update the software to the latest version using Docker."""
    error_log = []
    logger.info("Starting software update process")

    def run_command(command, error_message, capture_output=False):
        try:
            logger.debug(f"Running command: {' '.join(command)}")
            result = subprocess.run(command, check=True, capture_output=capture_output, text=True)
            return result.stdout if capture_output else None
        except subprocess.CalledProcessError as e:
            logger.error(f"{error_message}: {e}")
            error_log.append(error_message)
            return None

    # Pull new Docker images for both frontend and backend
    logger.info("Pulling latest Docker images...")
    run_command(
        ["docker", "pull", "ghcr.io/tuanchris/dune-weaver:main"],
        "Failed to pull backend Docker image"
    )
    run_command(
        ["docker", "pull", "ghcr.io/tuanchris/dune-weaver-frontend:main"],
        "Failed to pull frontend Docker image"
    )

    # Recreate containers with new images using docker-compose
    # Try docker-compose first, then docker compose (v2)
    logger.info("Recreating containers with new images...")
    compose_success = False

    # Try docker-compose (v1)
    try:
        subprocess.run(
            ["docker-compose", "up", "-d", "--force-recreate"],
            check=True,
            cwd="/app"
        )
        compose_success = True
        logger.info("Containers recreated successfully with docker-compose")
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.debug("docker-compose not available, trying docker compose")

    # Try docker compose (v2) if v1 failed
    if not compose_success:
        try:
            subprocess.run(
                ["docker", "compose", "up", "-d", "--force-recreate"],
                check=True,
                cwd="/app"
            )
            compose_success = True
            logger.info("Containers recreated successfully with docker compose")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.debug("docker compose not available, falling back to individual restarts")

    # Fallback: restart individual containers
    if not compose_success:
        logger.info("Falling back to individual container restarts...")
        run_command(
            ["docker", "restart", "dune-weaver-frontend"],
            "Failed to restart frontend container"
        )
        run_command(
            ["docker", "restart", "dune-weaver-backend"],
            "Failed to restart backend container"
        )

    if error_log:
        logger.error(f"Software update completed with errors: {error_log}")
        return False, "Update completed with errors", error_log

    logger.info("Software update completed successfully")
    return True, None, None
