import os
import subprocess
import json
import logging

MOTOR_TYPE_MAPPING = {
    "TMC2209": "./firmware/arduino_code_TMC2209/arduino_code_TMC2209.ino",
    "DRV8825": "./firmware/arduino_code/arduino_code.ino",
    "esp32": "./firmware/esp32/esp32.ino"
}

logger=logging.getLogger(__name__)

def get_ino_firmware_details(ino_file_path):
    """
    Extract firmware details, including version and motor type, from the given .ino file.
    """
    try:
        if not ino_file_path:
            raise ValueError("Invalid path: ino_file_path is None or empty.")

        firmware_details = {"version": None, "motorType": None}

        with open(ino_file_path, "r") as file:
            for line in file:
                # Extract firmware version
                if "firmwareVersion" in line:
                    start = line.find('"') + 1
                    end = line.rfind('"')
                    if start != -1 and end != -1 and start < end:
                        firmware_details["version"] = line[start:end]

                # Extract motor type
                if "motorType" in line:
                    start = line.find('"') + 1
                    end = line.rfind('"')
                    if start != -1 and end != -1 and start < end:
                        firmware_details["motorType"] = line[start:end]

        if not firmware_details["version"]:
            print(f"Firmware version not found in file: {ino_file_path}")
        if not firmware_details["motorType"]:
            print(f"Motor type not found in file: {ino_file_path}")

        return firmware_details if any(firmware_details.values()) else None

    except FileNotFoundError:
        print(f"File not found: {ino_file_path}")
        return None
    except Exception as e:
        print(f"Error reading .ino file: {str(e)}")
        return None

def get_firmware_info(installed_version, installed_type, motor_type=None):
    """
    Compare installed firmware with available firmware.
    """
    if motor_type:
        # For POST request with specific motor type
        if motor_type not in MOTOR_TYPE_MAPPING:
            return None, "Invalid motor type"

        ino_path = MOTOR_TYPE_MAPPING[motor_type]
        firmware_details = get_ino_firmware_details(ino_path)

        if not firmware_details:
            return None, "Failed to retrieve .ino firmware details"

        return {
            "success": True,
            "installedVersion": 'Unknown',
            "installedType": motor_type,
            "inoVersion": firmware_details["version"],
            "inoType": firmware_details["motorType"],
            "updateAvailable": True
        }, None

    # For GET request to check current firmware
    if installed_version != 'Unknown' and installed_type != 'Unknown':
        ino_path = MOTOR_TYPE_MAPPING.get(installed_type)
        firmware_details = get_ino_firmware_details(ino_path)

        if not firmware_details:
            return None, "Failed to retrieve .ino firmware details"

        update_available = (
            installed_version != firmware_details["version"] or
            installed_type != firmware_details["motorType"]
        )

        return {
            "success": True,
            "installedVersion": installed_version,
            "installedType": installed_type,
            "inoVersion": firmware_details["version"],
            "inoType": firmware_details["motorType"],
            "updateAvailable": update_available
        }, None

    return {
        "success": True,
        "installedVersion": installed_version,
        "installedType": installed_type,
        "updateAvailable": False
    }, None

def flash_firmware(ser_port, motor_type):
    """
    Compile and flash the firmware to the connected Arduino.
    """
    if motor_type not in MOTOR_TYPE_MAPPING:
        return False, "Invalid motor type"

    build_dir = "/tmp/arduino_build"  # Temporary build directory
    os.makedirs(build_dir, exist_ok=True)

    try:
        # Get the .ino file path based on the motor type
        ino_file_path = MOTOR_TYPE_MAPPING[motor_type]
        ino_file_name = os.path.basename(ino_file_path)

        # Install required libraries
        required_libraries = ["AccelStepper"]
        for library in required_libraries:
            library_install_command = ["arduino-cli", "lib", "install", library]
            install_process = subprocess.run(library_install_command, capture_output=True, text=True)
            if install_process.returncode != 0:
                return False, f"Library installation failed for {library}: {install_process.stderr}"

        # Compile the .ino file
        compile_command = [
            "arduino-cli",
            "compile",
            "--fqbn", "arduino:avr:uno",
            "--output-dir", build_dir,
            ino_file_path
        ]

        compile_process = subprocess.run(compile_command, capture_output=True, text=True)
        if compile_process.returncode != 0:
            return False, compile_process.stderr

        # Flash the .hex file
        hex_file_path = os.path.join(build_dir, f"{ino_file_name}.hex")
        flash_command = [
            "avrdude",
            "-v",
            "-c", "arduino",
            "-p", "atmega328p",
            "-P", ser_port,
            "-b", "115200",
            "-D",
            "-U", f"flash:w:{hex_file_path}:i"
        ]

        flash_process = subprocess.run(flash_command, capture_output=True, text=True)
        if flash_process.returncode != 0:
            return False, flash_process.stderr

        return True, "Firmware flashed successfully"

    except Exception as e:
        logger.error(f"Error flashing firmware: {str(e)}", exc_info=True)
        return False, str(e)
    finally:
        # Clean up temporary files
        if os.path.exists(build_dir):
            for file in os.listdir(build_dir):
                os.remove(os.path.join(build_dir, file))
            os.rmdir(build_dir)

def check_git_updates():
    """
    Check for available software updates.
    """
    try:
        # Fetch the latest updates from the remote repository
        subprocess.run(["git", "fetch", "--tags", "--force"], check=True)

        # Get the latest tag from the remote
        latest_remote_tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0", "origin/main"]
        ).strip().decode()

        # Get the latest tag from the local branch
        latest_local_tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0"]
        ).strip().decode()

        # Count how many tags the local branch is behind
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

        return {
            "updates_available": latest_remote_tag != latest_local_tag,
            "tag_behind_count": tag_behind_count,
            "latest_remote_tag": latest_remote_tag,
            "latest_local_tag": latest_local_tag,
        }
    except subprocess.CalledProcessError as e:
        print(f"Error checking Git updates: {e}")
        return {
            "updates_available": False,
            "tag_behind_count": 0,
            "latest_remote_tag": None,
            "latest_local_tag": None,
        }

def update_software():
    """
    Update the software to the latest version.
    """
    error_log = []

    def run_command(command, error_message):
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as e:
            print(f"{error_message}: {e}")
            error_log.append(error_message)

    try:
        # Fetch the latest version tag from remote
        subprocess.run(["git", "fetch", "--tags"], check=True)
        latest_remote_tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0", "origin/main"]
        ).strip().decode()
    except subprocess.CalledProcessError as e:
        error_log.append(f"Failed to fetch tags or get latest remote tag: {e}")
        return False, "Failed to fetch tags or determine the latest version.", error_log

    # Checkout the latest tag
    run_command(["git", "checkout", latest_remote_tag, '--force'], 
                f"Failed to checkout version {latest_remote_tag}")

    # Restart Docker containers
    run_command(["docker", "compose", "up", "-d"], 
                "Failed to restart Docker containers")

    # Check if the update was successful
    update_status = check_git_updates()

    if (
        update_status["updates_available"] is False
        and update_status["latest_local_tag"] == update_status["latest_remote_tag"]
    ):
        return True, "Update successful", None
    else:
        return False, "Update incomplete", error_log 