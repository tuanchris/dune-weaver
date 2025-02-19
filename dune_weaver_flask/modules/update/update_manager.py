import os
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
    """Update the software to the latest version."""
    error_log = []
    logger.info("Starting software update process")

    def run_command(command, error_message):
        try:
            logger.debug(f"Running command: {' '.join(command)}")
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"{error_message}: {e}")
            error_log.append(error_message)

    try:
        subprocess.run(["git", "fetch", "--tags"], check=True)
        latest_remote_tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0", "origin/main"]
        ).strip().decode()
        logger.info(f"Latest remote tag: {latest_remote_tag}")
    except subprocess.CalledProcessError as e:
        error_msg = f"Failed to fetch tags or get latest remote tag: {e}"
        logger.error(error_msg)
        error_log.append(error_msg)
        return False, error_msg, error_log

    run_command(["git", "checkout", latest_remote_tag, '--force'], f"Failed to checkout version {latest_remote_tag}")
    run_command(["docker", "compose", "pull"], "Failed to fetch Docker containers")
    run_command(["docker", "compose", "up", "-d"], "Failed to restart Docker containers")

    update_status = check_git_updates()

    if (
        update_status["updates_available"] is False
        and update_status["latest_local_tag"] == update_status["latest_remote_tag"]
    ):
        logger.info("Software update completed successfully")
        return True, None, None
    else:
        logger.error("Software update incomplete")
        return False, "Update incomplete", error_log
