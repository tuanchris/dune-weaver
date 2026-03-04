"""FluidNC configuration utilities.

Provides functions to read/write FluidNC settings via the main serial/WebSocket
connection. Uses $Config/Dump for bulk reads (single round-trip) and individual
$/path=value writes.

Targets FluidNC-based boards with bipolar stepper motors (DLC32, MKS boards).
"""

import time
import logging
import yaml
from modules.core.state import state

logger = logging.getLogger(__name__)

# Curated settings exposed in the Setup UI.
# Keys are FluidNC config tree paths queried via $/path.
CURATED_SETTINGS = {
    "x": [
        "axes/x/steps_per_mm",
        "axes/x/max_rate_mm_per_min",
        "axes/x/acceleration_mm_per_sec2",
        "axes/x/motor0/stepstick/direction_pin",
        "axes/x/homing/cycle",
        "axes/x/homing/positive_direction",
        "axes/x/homing/mpos_mm",
        "axes/x/homing/feed_mm_per_min",
        "axes/x/homing/seek_mm_per_min",
        "axes/x/homing/settle_ms",
        "axes/x/homing/seek_scaler",
        "axes/x/homing/feed_scaler",
        "axes/x/motor0/pulloff_mm",
    ],
    "y": [
        "axes/y/steps_per_mm",
        "axes/y/max_rate_mm_per_min",
        "axes/y/acceleration_mm_per_sec2",
        "axes/y/motor0/stepstick/direction_pin",
        "axes/y/homing/cycle",
        "axes/y/homing/positive_direction",
        "axes/y/homing/mpos_mm",
        "axes/y/homing/feed_mm_per_min",
        "axes/y/homing/seek_mm_per_min",
        "axes/y/homing/settle_ms",
        "axes/y/homing/seek_scaler",
        "axes/y/homing/feed_scaler",
        "axes/y/motor0/pulloff_mm",
    ],
    "global": [],
}


def send_command(command: str, timeout: float = 3.0, silence: float = 1.0) -> list[str]:
    """Send a command via the main connection and return response lines.

    Clears the input buffer, sends the command, then reads lines until
    'ok', 'error', silence gap, or timeout is reached.

    Args:
        command: The FluidNC command string.
        timeout: Absolute max wait time in seconds.
        silence: After receiving data, if no new data arrives for this many
                 seconds, consider the response complete. Handles commands
                 like $CD that may not end with 'ok'.
    """
    if not state.conn or not state.conn.is_connected():
        raise ConnectionError("Not connected to controller")

    # Clear input buffer
    try:
        while state.conn.in_waiting() > 0:
            state.conn.readline()
    except Exception:
        pass

    # Send command
    state.conn.send(command + "\n")
    time.sleep(0.2)

    # Read response lines
    lines: list[str] = []
    start_time = time.time()
    last_data_time = start_time
    got_data = False
    while time.time() - start_time < timeout:
        try:
            if state.conn.in_waiting() > 0:
                response = state.conn.readline()
                if response:
                    line = response.strip() if isinstance(response, str) else response.decode("utf-8", errors="replace").strip()
                    if line:
                        lines.append(line)
                        got_data = True
                        last_data_time = time.time()
                        if line.lower() == "ok" or line.lower().startswith("error"):
                            break
            else:
                # If data was flowing but has gone silent, we're done
                if got_data and (time.time() - last_data_time > silence):
                    break
                time.sleep(0.05)
        except Exception as e:
            logger.warning(f"Error reading response: {e}")
            break

    return lines


def read_setting(path: str) -> str | None:
    """Query a single FluidNC setting by config-tree path.

    Returns the value string, or None if the setting doesn't exist
    (e.g. stepstick path on a unipolar board).
    """
    try:
        responses = send_command(f"$/{path}")
    except ConnectionError:
        return None

    # Response format: "/axes/x/steps_per_mm=200.000" or similar
    leaf = path.split("/")[-1]
    for line in responses:
        if "=" in line and leaf in line:
            return line.split("=", 1)[1].strip()
        if line.lower().startswith("error"):
            return None
    return None


def _parse_value(raw: str | None, path: str) -> object:
    """Parse a raw FluidNC value string into a typed Python value."""
    if raw is None:
        return None

    # Direction pin — keep raw string but also derive inverted flag
    if "direction_pin" in path:
        return raw

    # Boolean-ish
    lower = raw.lower()
    if lower in ("true", "false"):
        return lower == "true"

    # Numeric
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def _resolve_yaml_path(data: dict, path: str):
    """Walk a nested dict by slash-separated path. Returns None if any key is missing."""
    node = data
    for key in path.split("/"):
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _make_key(path: str) -> str:
    """Convert a FluidNC config path to a flat UI key.

    e.g. "axes/x/motor0/stepstick/direction_pin" → "direction_pin"
         "axes/x/homing/feed_mm_per_min"         → "homing_feed_mm_per_min"
         "axes/x/motor0/hard_limits"              → "hard_limits"
    """
    parts = path.split("/")
    remaining = parts[2:]  # drop "axes/x" prefix
    remaining = [p for p in remaining if p not in ("motor0", "stepstick")]
    return "_".join(remaining)


def read_all_settings() -> dict:
    """Read all curated settings from the controller via $Config/Dump.

    Issues a single $Config/Dump command, parses the YAML response, and
    extracts curated settings. Much faster than individual queries
    (~1s vs ~9s for 30 settings).

    Returns a structured dict:
    {
        "axes": {
            "x": { "steps_per_mm": 320.0, "direction_inverted": True, "direction_pin": "i2so.2:low", ... },
            "y": { ... }
        },
        "start": { "must_home": False }
    }
    """
    lines = send_command("$CD", timeout=10.0, silence=1.5)
    logger.info(f"$CD returned {len(lines)} lines")

    # Filter out non-YAML lines (status messages, 'ok', etc.)
    yaml_lines = []
    for line in lines:
        if line.lower() == "ok" or line.lower().startswith("error"):
            continue
        # Skip FluidNC status messages like [MSG:...]
        if line.startswith("["):
            continue
        yaml_lines.append(line)

    yaml_text = "\n".join(yaml_lines)
    if not yaml_text.strip():
        logger.warning("$CD returned no YAML content, falling back to individual queries")
        return _read_all_settings_individual()

    try:
        config = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse $CD YAML ({len(yaml_lines)} lines): {e}")
        return _read_all_settings_individual()

    if not isinstance(config, dict):
        logger.warning(f"$CD parsed as {type(config).__name__}, falling back to individual queries")
        return _read_all_settings_individual()

    logger.info(f"$CD YAML top-level keys: {list(config.keys())}")

    result: dict = {"axes": {"x": {}, "y": {}}, "start": {}}
    resolved_count = 0

    for axis in ("x", "y"):
        for path in CURATED_SETTINGS[axis]:
            raw = _resolve_yaml_path(config, path)
            key = _make_key(path)

            if raw is not None:
                resolved_count += 1

            if "direction_pin" in path:
                raw_str = str(raw) if raw is not None else None
                result["axes"][axis][key] = raw_str
                result["axes"][axis]["direction_inverted"] = (
                    ":low" in raw_str if raw_str else None
                )
            else:
                result["axes"][axis][key] = raw

    for path in CURATED_SETTINGS["global"]:
        raw = _resolve_yaml_path(config, path)
        if raw is not None:
            resolved_count += 1
        parts = path.split("/")
        key = "_".join(parts[1:])
        result["start"][key] = raw

    # If $CD parsed but we couldn't resolve any of our settings,
    # the YAML structure doesn't match — fall back to individual queries
    if resolved_count == 0:
        logger.warning(
            f"$CD YAML parsed ({len(config)} keys) but no curated settings resolved. "
            f"Falling back to individual queries."
        )
        return _read_all_settings_individual()

    logger.info(f"$CD resolved {resolved_count}/{len(CURATED_SETTINGS['x']) * 2 + len(CURATED_SETTINGS['global'])} settings")
    return result


def _read_all_settings_individual() -> dict:
    """Fallback: read curated settings one by one via $/path queries."""
    result: dict = {"axes": {"x": {}, "y": {}}, "start": {}}

    for axis in ("x", "y"):
        for path in CURATED_SETTINGS[axis]:
            raw = read_setting(path)
            key = _make_key(path)
            parsed = _parse_value(raw, path)
            result["axes"][axis][key] = parsed

            if "direction_pin" in path:
                result["axes"][axis]["direction_inverted"] = (
                    ":low" in raw if raw else None
                )

    for path in CURATED_SETTINGS["global"]:
        raw = read_setting(path)
        parts = path.split("/")
        key = "_".join(parts[1:])
        result["start"][key] = _parse_value(raw, path)

    return result


def write_setting(path: str, value: str) -> bool:
    """Write a single FluidNC setting. Returns True on success."""
    try:
        responses = send_command(f"$/{path}={value}")
    except ConnectionError:
        return False
    return any("ok" in r.lower() for r in responses)


def get_config_filename() -> str:
    """Get the active config filename from FluidNC."""
    try:
        responses = send_command("$Config/Filename")
    except ConnectionError:
        return "config.yaml"

    for line in responses:
        if "=" in line and "Filename" in line:
            return line.split("=", 1)[1].strip()
    return "config.yaml"


def save_config() -> bool:
    """Persist current in-RAM config to flash using the active config filename."""
    filename = get_config_filename()
    try:
        responses = send_command(f"$CD=/littlefs/{filename}", timeout=5.0)
    except ConnectionError:
        return False
    return any("ok" in r.lower() for r in responses)


def toggle_direction_pin(axis: str) -> tuple[bool, bool]:
    """Toggle :low on the direction pin for the given axis.

    Returns (success, new_inverted_state).
    """
    path = f"axes/{axis}/motor0/stepstick/direction_pin"
    current = read_setting(path)
    if current is None:
        return (False, False)

    if ":low" in current:
        new_val = current.replace(":low", "")
    else:
        new_val = current + ":low"

    success = write_setting(path, new_val)
    return (success, ":low" in new_val)
