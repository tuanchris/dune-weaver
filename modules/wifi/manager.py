"""
WiFi management via NetworkManager (nmcli).

Handles scanning, connecting, and managing WiFi connections.
In Docker, nmcli communicates with the host's NetworkManager over the
mounted D-Bus system socket — same mechanism systemctl uses for shutdown.
"""

import subprocess
import os
import logging
import asyncio

logger = logging.getLogger(__name__)

HOST_HOSTNAME_FILE = "/etc/host-hostname"
HOTSPOT_CON_NAME = "DuneWeaver-Hotspot"


def is_docker() -> bool:
    """Check if running inside a Docker container."""
    return os.path.exists("/.dockerenv") or os.getenv("DOCKER_CONTAINER") == "1"


def run_nmcli(*args: str, timeout: int = 30) -> str:
    """Run nmcli and return stdout.

    In both Docker and venv modes, nmcli runs directly. In Docker, it
    communicates with the host's NetworkManager via the mounted D-Bus
    system bus socket (/var/run/dbus/system_bus_socket).
    """
    cmd = ["nmcli"] + list(args)
    logger.debug(f"Running nmcli: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    if result.returncode != 0:
        logger.warning(f"nmcli failed (rc={result.returncode}): {' '.join(cmd)}")
        if result.stderr:
            logger.warning(f"  stderr: {result.stderr.strip()}")

    return result.stdout


def run_nmcli_check(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run nmcli and return the full CompletedProcess (for checking returncode)."""
    cmd = ["nmcli"] + list(args)
    logger.debug(f"Running nmcli: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    if result.returncode != 0:
        logger.warning(f"nmcli failed (rc={result.returncode}): {' '.join(cmd)}")
        if result.stderr:
            logger.warning(f"  stderr: {result.stderr.strip()}")

    return result


def get_wifi_mode() -> str:
    """Detect WiFi mode by querying NetworkManager active connections.

    Uses 'nmcli con show --active' instead of 'nmcli dev show wlan0'
    because the latter can behave differently in AP (hotspot) mode
    across NM versions.
    """
    try:
        output = run_nmcli("-t", "-f", "NAME,TYPE,DEVICE", "con", "show", "--active")
        logger.info(f"Active connections: {output.strip()}")
        for line in output.strip().splitlines():
            parts = line.split(":")
            if len(parts) >= 3 and parts[2] == "wlan0":
                con_name = parts[0]
                if con_name == HOTSPOT_CON_NAME:
                    return "hotspot"
                return "client"
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.warning(f"Error detecting WiFi mode: {e}")
    return "unknown"


def get_current_ssid() -> str:
    """Get the SSID of the currently connected WiFi network."""
    try:
        # Use active connections to find the wifi connection on wlan0
        output = run_nmcli("-t", "-f", "NAME,TYPE,DEVICE", "con", "show", "--active")
        for line in output.strip().splitlines():
            parts = line.split(":")
            if len(parts) >= 3 and parts[2] == "wlan0":
                con_name = parts[0]
                if con_name and con_name != HOTSPOT_CON_NAME:
                    return con_name
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.debug(f"Error getting SSID: {e}")
    return ""


def get_current_ip() -> str:
    """Get the current IP address of the wlan0 interface."""
    try:
        output = run_nmcli("-t", "-f", "IP4.ADDRESS", "dev", "show", "wlan0")
        logger.debug(f"IP output: {output.strip()}")
        for line in output.strip().splitlines():
            if "IP4.ADDRESS" in line:
                addr = line.split(":", 1)[1] if ":" in line else ""
                if addr:
                    return addr.split("/")[0]
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.debug(f"Error getting IP: {e}")
    return ""


def get_hostname() -> str:
    """Get the host system hostname.

    In Docker, reads from the mounted /etc/host-hostname file to get the
    real host identity instead of the container ID.
    """
    try:
        if is_docker() and os.path.exists(HOST_HOSTNAME_FILE):
            with open(HOST_HOSTNAME_FILE, "r") as f:
                name = f.read().strip()
                if name:
                    return name
        # Fallback: use nmcli to query NM's hostname
        output = run_nmcli("general", "hostname")
        name = output.strip()
        if name:
            return name
    except Exception:
        pass
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
        if name == HOTSPOT_CON_NAME:
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
    """Connect to a WiFi network.

    Uses explicit connection profile creation (nmcli con add) instead of
    'nmcli dev wifi connect' because the latter fails on Pi Trixie with
    'key-mgmt: property is missing' for WPA networks.
    """
    try:
        # Delete any stale connection profile for this SSID (ignore if not found)
        subprocess.run(
            ["nmcli", "con", "delete", ssid],
            capture_output=True, text=True, timeout=10,
        )

        # Create connection profile with explicit security settings
        if password:
            result = run_nmcli_check(
                "con", "add",
                "type", "wifi",
                "ifname", "wlan0",
                "con-name", ssid,
                "ssid", ssid,
                "wifi-sec.key-mgmt", "wpa-psk",
                "wifi-sec.psk", password,
                timeout=15,
            )
        else:
            result = run_nmcli_check(
                "con", "add",
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
        result = run_nmcli_check("con", "up", ssid, timeout=30)

        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Failed to connect"
            logger.error(f"WiFi connect failed: {error_msg}")
            # Clean up the failed connection profile
            run_nmcli_check("con", "delete", ssid, timeout=10)
            return {"success": False, "message": error_msg}

        logger.info(f"WiFi connection to '{ssid}' successful")

        return {
            "success": True,
            "message": f"Connected to '{ssid}'.",
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Connection timed out"}
    except Exception as e:
        logger.error(f"WiFi connect error: {e}")
        return {"success": False, "message": str(e)}


def save_network(ssid: str, password: str) -> dict:
    """Save a WiFi network profile without connecting.

    Creates the connection profile so autohotspot can use it on next check/boot.
    """
    try:
        # Delete any stale connection profile for this SSID (ignore if not found)
        subprocess.run(
            ["nmcli", "con", "delete", ssid],
            capture_output=True, text=True, timeout=10,
        )

        if password:
            result = run_nmcli_check(
                "con", "add",
                "type", "wifi",
                "ifname", "wlan0",
                "con-name", ssid,
                "ssid", ssid,
                "wifi-sec.key-mgmt", "wpa-psk",
                "wifi-sec.psk", password,
                timeout=15,
            )
        else:
            result = run_nmcli_check(
                "con", "add",
                "type", "wifi",
                "ifname", "wlan0",
                "con-name", ssid,
                "ssid", ssid,
                timeout=15,
            )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Failed to save network"
            logger.error(f"WiFi save failed: {error_msg}")
            return {"success": False, "message": error_msg}

        logger.info(f"Saved WiFi network '{ssid}' (not connecting)")
        return {"success": True, "message": f"Saved '{ssid}'. Will connect automatically when in range."}

    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Operation timed out"}
    except Exception as e:
        logger.error(f"WiFi save error: {e}")
        return {"success": False, "message": str(e)}


def forget_network(ssid: str) -> dict:
    """Delete a saved WiFi connection by SSID.

    If the forgotten network was the active connection, triggers the
    autohotspot script to re-evaluate and fall back to hotspot mode.
    """
    # Check if this is the currently active connection
    current_ssid = get_current_ssid()
    was_active = current_ssid == ssid or current_ssid == ssid.replace(" ", "")

    saved = get_saved_connections()
    con_name = None
    for con in saved:
        if con["ssid"] == ssid:
            con_name = con["name"]
            break

    if not con_name:
        return {"success": False, "message": f"No saved connection found for '{ssid}'"}

    try:
        result = run_nmcli_check("con", "delete", con_name, timeout=15)
        if result.returncode == 0:
            logger.info(f"Forgot WiFi network '{ssid}' (connection: {con_name})")

            # If we just forgot the active connection, re-run autohotspot
            # so it can fall back to hotspot mode
            if was_active:
                _trigger_autohotspot()

            return {"success": True, "message": f"Forgot '{ssid}'"}
        else:
            error_msg = result.stderr.strip() or "Failed to delete connection"
            return {"success": False, "message": error_msg}
    except Exception as e:
        return {"success": False, "message": str(e)}


def get_hotspot_password() -> dict:
    """Get the current hotspot password (empty string if open network)."""
    try:
        output = run_nmcli("-s", "-t", "-f", "802-11-wireless-security.psk",
                           "con", "show", HOTSPOT_CON_NAME)
        for line in output.strip().splitlines():
            if "802-11-wireless-security.psk" in line:
                psk = line.split(":", 1)[1] if ":" in line else ""
                return {"password": psk}
        return {"password": ""}
    except Exception as e:
        logger.error(f"Error getting hotspot password: {e}")
        return {"password": ""}


def set_hotspot_password(password: str) -> dict:
    """Set or remove the hotspot password.

    If password is non-empty, enables WPA-PSK. If empty, removes security
    (open network). Restarts the hotspot if it's currently active.
    """
    try:
        if password:
            if len(password) < 8:
                return {"success": False, "message": "Password must be at least 8 characters"}
            result = run_nmcli_check(
                "con", "modify", HOTSPOT_CON_NAME,
                "wifi-sec.key-mgmt", "wpa-psk",
                "wifi-sec.psk", password,
            )
        else:
            # Remove security settings entirely to make it an open network
            result = run_nmcli_check(
                "con", "modify", HOTSPOT_CON_NAME,
                "remove", "802-11-wireless-security",
            )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Failed to update hotspot password"
            return {"success": False, "message": error_msg}

        # Restart hotspot if currently active so changes take effect
        if get_wifi_mode() == "hotspot":
            run_nmcli_check("con", "down", HOTSPOT_CON_NAME, timeout=10)
            run_nmcli_check("con", "up", HOTSPOT_CON_NAME, timeout=10)

        msg = "Hotspot password updated" if password else "Hotspot password removed (open network)"
        logger.info(msg)
        return {"success": True, "message": msg}
    except Exception as e:
        logger.error(f"Error setting hotspot password: {e}")
        return {"success": False, "message": str(e)}


def _trigger_autohotspot():
    """Trigger an immediate autohotspot check.

    Called when the active network is forgotten so the user doesn't have
    to wait for the next 60s timer tick. Falls back to direct nmcli
    commands in Docker where the host script isn't available.
    """
    autohotspot_path = "/usr/local/bin/autohotspot"
    try:
        if os.path.exists(autohotspot_path):
            logger.info("Triggering autohotspot --check after forgetting active network...")
            subprocess.Popen(
                [autohotspot_path, "--check"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            # Docker fallback: directly activate hotspot via D-Bus
            logger.info("Autohotspot script not found, activating hotspot directly...")
            run_nmcli("dev", "disconnect", "wlan0")
            run_nmcli("con", "up", HOTSPOT_CON_NAME)
    except Exception as e:
        logger.error(f"Failed to trigger autohotspot: {e}")
