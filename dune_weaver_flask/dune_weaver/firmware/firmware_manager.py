import os
import subprocess
from ..serial.serial_manager import serial_manager

class FirmwareManager:
    def __init__(self):
        self.MOTOR_TYPE_MAPPING = {
            "TMC2209": "./firmware/arduino_code_TMC2209/arduino_code_TMC2209.ino",
            "DRV8825": "./firmware/arduino_code/arduino_code.ino",
            "esp32": "./firmware/esp32/esp32.ino",
            "esp32_TMC2209": "./firmware/esp32_TMC2209/esp32_TMC2209.ino"
        }

    def get_ino_firmware_details(self, ino_file_path):
        """Extract firmware details from the given .ino file."""
        try:
            if not ino_file_path:
                raise ValueError("Invalid path: ino_file_path is None or empty.")

            firmware_details = {"version": None, "motorType": None}

            with open(ino_file_path, "r") as file:
                for line in file:
                    if "firmwareVersion" in line:
                        start = line.find('"') + 1
                        end = line.rfind('"')
                        if start != -1 and end != -1 and start < end:
                            firmware_details["version"] = line[start:end]

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

    def check_git_updates(self):
        """Check for available Git updates."""
        try:
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

            return {
                "updates_available": updates_available,
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

    def update_software(self):
        """Update the software to the latest version."""
        error_log = []

        def run_command(command, error_message):
            try:
                subprocess.run(command, check=True)
            except subprocess.CalledProcessError as e:
                print(f"{error_message}: {e}")
                error_log.append(error_message)

        try:
            subprocess.run(["git", "fetch", "--tags"], check=True)
            latest_remote_tag = subprocess.check_output(
                ["git", "describe", "--tags", "--abbrev=0", "origin/main"]
            ).strip().decode()
        except subprocess.CalledProcessError as e:
            error_log.append(f"Failed to fetch tags or get latest remote tag: {e}")
            return False, "Failed to fetch tags or determine the latest version.", error_log

        run_command(["git", "checkout", latest_remote_tag, '--force'], f"Failed to checkout version {latest_remote_tag}")
        run_command(["docker", "compose", "pull"], "Failed to fetch Docker containers")
        run_command(["docker", "compose", "up", "-d"], "Failed to restart Docker containers")

        update_status = self.check_git_updates()

        if (
            update_status["updates_available"] is False
            and update_status["latest_local_tag"] == update_status["latest_remote_tag"]
        ):
            return True, None, None
        else:
            return False, "Update incomplete", error_log

    def get_firmware_info(self, motor_type=None):
        """Get firmware information for the current or specified motor type."""
        if motor_type and motor_type not in self.MOTOR_TYPE_MAPPING:
            return False, "Invalid motor type"

        installed_version = serial_manager.firmware_version
        installed_type = serial_manager.arduino_driver_type

        if motor_type:
            # POST request with specified motor type
            ino_path = self.MOTOR_TYPE_MAPPING[motor_type]
            firmware_details = self.get_ino_firmware_details(ino_path)

            if not firmware_details:
                return False, "Failed to retrieve .ino firmware details"

            return True, {
                "installedVersion": 'Unknown',
                "installedType": motor_type,
                "inoVersion": firmware_details["version"],
                "inoType": firmware_details["motorType"],
                "updateAvailable": True
            }
        else:
            # GET request for current firmware info
            if installed_version != 'Unknown' and installed_type != 'Unknown':
                ino_path = self.MOTOR_TYPE_MAPPING.get(installed_type)
                firmware_details = self.get_ino_firmware_details(ino_path)

                if not firmware_details or not firmware_details.get("version") or not firmware_details.get("motorType"):
                    return False, "Failed to retrieve .ino firmware details"

                update_available = (
                    installed_version != firmware_details["version"] or
                    installed_type != firmware_details["motorType"]
                )

                return True, {
                    "installedVersion": installed_version,
                    "installedType": installed_type,
                    "inoVersion": firmware_details["version"],
                    "inoType": firmware_details["motorType"],
                    "updateAvailable": update_available
                }

            return True, {
                "installedVersion": installed_version,
                "installedType": installed_type,
                "updateAvailable": False
            }

    def flash_firmware(self, motor_type):
        """Flash firmware for the specified motor type."""
        if not motor_type or motor_type not in self.MOTOR_TYPE_MAPPING:
            return False, "Invalid or missing motor type"

        if not serial_manager.is_connected():
            return False, "No device connected or connection lost"

        try:
            ino_file_path = self.MOTOR_TYPE_MAPPING[motor_type]
            hex_file_path = f"{ino_file_path}.hex"
            bin_file_path = f"{ino_file_path}.bin"

            if motor_type.lower() in ["esp32", "esp32_tmc2209"]:
                if not os.path.exists(bin_file_path):
                    return False, f"Firmware binary not found: {bin_file_path}"

                flash_command = [
                    "esptool.py",
                    "--chip", "esp32",
                    "--port", serial_manager.get_port(),
                    "--baud", "115200",
                    "write_flash", "-z", "0x1000", bin_file_path
                ]
            else:
                if not os.path.exists(hex_file_path):
                    return False, f"Hex file not found: {hex_file_path}"

                flash_command = [
                    "avrdude",
                    "-v",
                    "-c", "arduino",
                    "-p", "atmega328p",
                    "-P", serial_manager.get_port(),
                    "-b", "115200",
                    "-D",
                    "-U", f"flash:w:{hex_file_path}:i"
                ]

            flash_process = subprocess.run(flash_command, capture_output=True, text=True)
            if flash_process.returncode != 0:
                return False, flash_process.stderr

            return True, "Firmware flashed successfully"
        except Exception as e:
            return False, str(e)

# Create a global instance
firmware_manager = FirmwareManager()
