"""
WiFi management via NetworkManager (nmcli).

Handles scanning, connecting, and managing WiFi connections.
Supports both Docker (via nsenter) and direct (venv) execution.
"""

import subprocess
import os
import logging
import asyncio
import socket

logger = logging.getLogger(__name__)

MODE_FILE = "/tmp/dw-wifi-mode"


def is_docker() -> bool:
    """Check if running inside a Docker container."""
    return os.path.exists("/.dockerenv") or os.getenv("DOCKER_CONTAINER") == "1"


def run_host_command(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a command on the host, handling Docker vs venv.

    In Docker: uses nsenter to execute in the host's namespaces.
    In venv: executes directly.
    """
    if is_docker():
        cmd = ["nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "--"] + list(args)
    else:
        cmd = list(args)

    logger.info(f"Running host command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    if result.returncode != 0:
        logger.warning(f"Command failed (rc={result.returncode}): {' '.join(cmd)}")
        if result.stderr:
            logger.warning(f"  stderr: {result.stderr.strip()}")
        if result.stdout:
            logger.warning(f"  stdout: {result.stdout.strip()}")

    return result


def run_nmcli(*args: str, timeout: int = 30) -> str:
    """Run nmcli on the host and return stdout."""
    result = run_host_command("nmcli", *args, timeout=timeout)
    return result.stdout


def get_wifi_mode() -> str:
    """Get the current WiFi mode from the mode file."""
    try:
        if is_docker():
            result = run_host_command("cat", MODE_FILE)
            return result.stdout.strip() or "unknown"
        else:
            with open(MODE_FILE, "r") as f:
                return f.read().strip() or "unknown"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "unknown"


def get_current_ssid() -> str:
    """Get the SSID of the currently connected WiFi network."""
    try:
        output = run_nmcli("-t", "-f", "GENERAL.CONNECTION", "dev", "show", "wlan0")
        for line in output.strip().splitlines():
            if "GENERAL.CONNECTION" in line:
                ssid = line.split(":", 1)[1] if ":" in line else ""
                if ssid and ssid != "--" and ssid != "DuneWeaver-Hotspot":
                    return ssid
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.debug(f"Error getting SSID: {e}")
    return ""


def get_current_ip() -> str:
    """Get the current IP address of the wlan0 interface."""
    try:
        output = run_nmcli("-t", "-f", "IP4.ADDRESS", "dev", "show", "wlan0")
        for line in output.strip().splitlines():
            if "IP4.ADDRESS" in line:
                addr = line.split(":", 1)[1] if ":" in line else ""
                if addr:
                    return addr.split("/")[0]
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.debug(f"Error getting IP: {e}")
    return ""


def get_hostname() -> str:
    """Get the host system hostname (not the container hostname)."""
    try:
        if is_docker():
            result = run_host_command("hostname")
            name = result.stdout.strip()
            if name:
                return name
        return socket.gethostname()
    except Exception:
        return "duneweaver"


def get_wifi_status() -> dict:
    """Get comprehensive WiFi status."""
    mode = get_wifi_mode()
    ssid = get_current_ssid()
    ip = get_current_ip()
    hostname = get_hostname()

    return {
        "mode": mode,
        "ssid": ssid,
        "ip": ip,
        "hostname": hostname,
    }


def scan_networks() -> list[dict]:
    """Scan for available WiFi networks."""
    try:
        # Trigger rescan
        run_nmcli("dev", "wifi", "rescan", "ifname", "wlan0")
    except Exception:
        pass

    # Brief wait for scan results
    import time
    time.sleep(2)

    try:
        output = run_nmcli("-t", "-f", "SSID,SIGNAL,SECURITY,ACTIVE", "dev", "wifi", "list", "ifname", "wlan0")
    except subprocess.TimeoutExpired:
        logger.error("WiFi scan timed out")
        return []

    # Get saved connections for cross-reference
    saved = get_saved_connections()
    saved_ssids = {c["ssid"] for c in saved}

    networks = []
    seen_ssids = set()

    for line in output.strip().splitlines():
        if not line.strip():
            continue
        # nmcli -t uses : as delimiter, but SSID can contain colons
        # Format: SSID:SIGNAL:SECURITY:ACTIVE
        # Parse from the right since SSID is the only field that can contain ':'
        parts = line.rsplit(":", 3)
        if len(parts) < 4:
            continue

        ssid = parts[0].strip()
        if not ssid or ssid in seen_ssids:
            continue
        seen_ssids.add(ssid)

        try:
            signal = int(parts[1])
        except (ValueError, IndexError):
            signal = 0

        security = parts[2] if len(parts) > 2 else ""
        active = parts[3].strip().lower() == "yes" if len(parts) > 3 else False

        networks.append({
            "ssid": ssid,
            "signal": signal,
            "security": security if security and security != "--" else "Open",
            "saved": ssid in saved_ssids,
            "active": active,
        })

    # Sort by signal strength (strongest first)
    networks.sort(key=lambda n: n["signal"], reverse=True)
    return networks


def get_saved_connections() -> list[dict]:
    """Get list of saved WiFi connections."""
    try:
        output = run_nmcli("-t", "-f", "NAME,TYPE", "con", "show")
    except subprocess.TimeoutExpired:
        return []

    connections = []
    for line in output.strip().splitlines():
        if "wireless" not in line:
            continue
        name = line.split(":")[0]
        if name == "DuneWeaver-Hotspot":
            continue

        # Get the SSID for this connection
        try:
            detail = run_nmcli("-t", "-f", "802-11-wireless.ssid", "con", "show", name)
            ssid = ""
            for detail_line in detail.strip().splitlines():
                if "802-11-wireless.ssid" in detail_line:
                    ssid = detail_line.split(":", 1)[1] if ":" in detail_line else name
                    break
            if not ssid:
                ssid = name
        except Exception:
            ssid = name

        connections.append({
            "name": name,
            "ssid": ssid,
        })

    return connections


async def connect_to_network(ssid: str, password: str) -> dict:
    """Connect to a WiFi network and schedule reboot.

    Uses explicit connection profile creation (nmcli con add) instead of
    'nmcli dev wifi connect' because the latter fails on Pi Trixie with
    'key-mgmt: property is missing' for WPA networks.
    """
    try:
        # Delete any stale connection profile for this SSID
        run_host_command("nmcli", "con", "delete", ssid, timeout=10)

        # Create connection profile with explicit security settings
        if password:
            result = run_host_command(
                "nmcli", "con", "add",
                "type", "wifi",
                "ifname", "wlan0",
                "con-name", ssid,
                "ssid", ssid,
                "wifi-sec.key-mgmt", "wpa-psk",
                "wifi-sec.psk", password,
                timeout=15,
            )
        else:
            result = run_host_command(
                "nmcli", "con", "add",
                "type", "wifi",
                "ifname", "wlan0",
                "con-name", ssid,
                "ssid", ssid,
                timeout=15,
            )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Failed to create connection"
            logger.error(f"WiFi connection add failed: {error_msg}")
            return {"success": False, "message": error_msg}

        # Activate the connection
        result = run_host_command(
            "nmcli", "con", "up", ssid,
            timeout=30,
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Failed to connect"
            logger.error(f"WiFi connect failed: {error_msg}")
            # Clean up the failed connection profile
            run_host_command("nmcli", "con", "delete", ssid, timeout=10)
            return {"success": False, "message": error_msg}

        logger.info(f"WiFi connection to '{ssid}' successful, scheduling reboot...")

        # Schedule reboot so the response can be sent first
        asyncio.get_event_loop().call_later(3, _schedule_reboot)

        return {
            "success": True,
            "message": f"Connected to '{ssid}'. Rebooting in 3 seconds...",
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Connection timed out"}
    except Exception as e:
        logger.error(f"WiFi connect error: {e}")
        return {"success": False, "message": str(e)}


def _schedule_reboot():
    """Trigger a system reboot."""
    try:
        logger.info("Rebooting system for WiFi mode change...")
        run_host_command("reboot")
    except Exception as e:
        logger.error(f"Reboot failed: {e}")


def forget_network(ssid: str) -> dict:
    """Delete a saved WiFi connection by SSID."""
    saved = get_saved_connections()
    con_name = None
    for con in saved:
        if con["ssid"] == ssid:
            con_name = con["name"]
            break

    if not con_name:
        return {"success": False, "message": f"No saved connection found for '{ssid}'"}

    try:
        result = run_host_command("nmcli", "con", "delete", con_name, timeout=15)
        if result.returncode == 0:
            logger.info(f"Forgot WiFi network '{ssid}' (connection: {con_name})")
            return {"success": True, "message": f"Forgot '{ssid}'"}
        else:
            error_msg = result.stderr.strip() or "Failed to delete connection"
            return {"success": False, "message": error_msg}
    except Exception as e:
        return {"success": False, "message": str(e)}
