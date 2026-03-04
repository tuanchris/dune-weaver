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

    Pulls latest code, installs updated Python dependencies,
    and restarts the systemd service.

    For a full update (including frontend rebuild), run 'dw update' instead.
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

    # Step 1: Pull latest code via git
    logger.info("Pulling latest code from git...")
    git_result = run_command(
        ["git", "pull", "--ff-only"],
        "Failed to pull latest code from git"
    )
    if git_result:
        logger.info("Git pull completed successfully")

    # Step 2: Install updated Python dependencies
    logger.info("Installing updated dependencies...")
    run_command(
        [".venv/bin/pip", "install", "-r", "requirements.txt"],
        "Failed to install updated dependencies"
    )

    # Step 3: Restart the service
    logger.info("Restarting dune-weaver service...")
    restart_result = run_command(
        ["sudo", "systemctl", "restart", "dune-weaver"],
        "Failed to restart dune-weaver service"
    )

    if not restart_result:
        error_log.append("Service restart failed - please run 'dw restart' manually")

    if error_log:
        logger.error(f"Software update completed with errors: {error_log}")
        return False, "Update completed with errors. Run 'dw update' for a full update.", error_log

    logger.info("Software update completed successfully")
    return True, None, None
