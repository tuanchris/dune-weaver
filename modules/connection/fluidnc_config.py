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
    # FluidNC rejects runtime changes to Pin objects with a message but
    # still replies "ok" — treat that as failure, not success
    if any("not supported" in r.lower() for r in responses):
        logger.warning(f"FluidNC rejected write to {path}: {responses}")
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


###############################################################################
# Direction pin toggling via config file rewrite
#
# FluidNC (v3.7+) rejects runtime changes to Pin objects — it prints
# "Runtime setting of Pin objects is not supported" but still replies "ok",
# so $/path=value writes silently do nothing. The only way to change a pin
# is to edit the YAML config file on the controller's flash and reboot.
# We read the file with $LocalFS/Show, toggle the :low flag host-side, and
# upload the edited file back over XModem ($Xmodem/Receive).
###############################################################################

# XModem protocol bytes
_SOH, _EOT, _ACK, _NAK, _CAN, _CTRLZ = 0x01, 0x04, 0x06, 0x15, 0x18, 0x1A


def _get_serial():
    """Return the underlying pyserial object, or raise for non-serial connections."""
    conn = state.conn
    if not conn or not conn.is_connected():
        raise ConnectionError("Not connected to controller")
    ser = getattr(conn, "ser", None)
    if ser is None:
        raise ConnectionError(
            "Direction pin changes require a serial connection "
            "(file upload over WebSocket is not supported)"
        )
    return conn, ser


def _read_raw(ser, timeout: float = 10.0, silence: float = 1.0) -> str:
    """Read raw bytes until 'ok'/'error', a silence gap, or timeout.

    Unlike send_command(), preserves leading whitespace — required when
    reading YAML file content where indentation is structure.
    """
    buf = bytearray()
    start = time.time()
    last_data = start
    while time.time() - start < timeout:
        n = ser.in_waiting
        if n:
            buf += ser.read(n)
            last_data = time.time()
            tail = bytes(buf[-16:])
            if tail.rstrip().endswith(b"ok") or b"error:" in tail:
                break
        else:
            if buf and time.time() - last_data > silence:
                break
            time.sleep(0.02)
    return buf.decode("utf-8", errors="replace")


def read_config_file() -> str | None:
    """Read the active config file's raw text from the controller's flash."""
    conn, ser = _get_serial()
    filename = get_config_filename()
    with conn.lock:
        ser.reset_input_buffer()
        ser.write(f"$LocalFS/Show=/littlefs/{filename}\n".encode())
        ser.flush()
        text = _read_raw(ser, timeout=15.0, silence=1.0)

    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        # Drop protocol/status noise; keep file content (incl. indentation)
        if stripped.lower() == "ok" or stripped.startswith(("[", "<")) or stripped.startswith("error:"):
            continue
        lines.append(line.rstrip("\r"))
    content = "\n".join(lines).strip("\n")
    if not content:
        return None
    return content + "\n"


def _toggle_direction_in_text(text: str, axes: list[str]) -> tuple[str, dict[str, bool]]:
    """Toggle :low on direction_pin lines for the given axes in YAML text.

    Walks the YAML line by line with an indentation-based path stack so the
    edit is targeted (axes/<axis>/motor0/*/direction_pin) while preserving
    comments and formatting everywhere else.

    Returns (new_text, {axis: new_inverted_state}).
    """
    lines = text.split("\n")
    stack: list[tuple[int, str]] = []
    toggled: dict[str, bool] = {}

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        indent = len(line) - len(line.lstrip(" "))
        key = stripped.split(":", 1)[0].strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, key))

        parts = [k for _, k in stack]
        # Match axes/<axis>/motor0/<driver>/direction_pin for any driver type
        if (
            len(parts) == 5
            and parts[0] == "axes"
            and parts[1] in axes
            and parts[2] == "motor0"
            and parts[4] == "direction_pin"
        ):
            value = stripped.split(":", 1)[1].split("#", 1)[0].strip().strip("'\"")
            if not value:
                continue
            new_val = value.replace(":low", "") if ":low" in value else value + ":low"
            # Quote values containing ':' so the YAML stays valid
            rendered = f"'{new_val}'" if ":" in new_val else new_val
            lines[i] = " " * indent + f"direction_pin: {rendered}"
            toggled[parts[1]] = ":low" in new_val

    return "\n".join(lines), toggled


def _crc16_xmodem(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def upload_config_file(text: str) -> bool:
    """Upload config file text to the controller's flash via XModem."""
    conn, ser = _get_serial()
    filename = get_config_filename()
    data = text.encode()

    with conn.lock:
        ser.reset_input_buffer()
        ser.write(f"$Xmodem/Receive=/littlefs/{filename}\n".encode())
        ser.flush()

        # Wait for receiver handshake: 'C' = CRC mode, NAK = checksum mode
        crc_mode = None
        start = time.time()
        while time.time() - start < 15:
            b = ser.read(1)
            if not b:
                continue
            if b == b"C":
                crc_mode = True
                break
            if b[0] == _NAK:
                crc_mode = False
                break
        if crc_mode is None:
            logger.error("XModem: no handshake from controller")
            return False

        seq = 1
        for offset in range(0, len(data), 128):
            block = data[offset : offset + 128].ljust(128, bytes([_CTRLZ]))
            packet = bytes([_SOH, seq & 0xFF, 0xFF - (seq & 0xFF)]) + block
            if crc_mode:
                crc = _crc16_xmodem(block)
                packet += bytes([crc >> 8, crc & 0xFF])
            else:
                packet += bytes([sum(block) & 0xFF])

            for _attempt in range(10):
                ser.write(packet)
                ser.flush()
                resp = ser.read(1)
                # Ignore leftover handshake chars from before the first packet
                while resp == b"C":
                    resp = ser.read(1)
                if resp and resp[0] == _ACK:
                    break
                if resp and resp[0] == _CAN:
                    logger.error("XModem: transfer cancelled by controller")
                    return False
            else:
                logger.error(f"XModem: packet {seq} never acknowledged")
                ser.write(bytes([_CAN, _CAN]))
                ser.flush()
                return False
            seq += 1

        for _attempt in range(10):
            ser.write(bytes([_EOT]))
            ser.flush()
            resp = ser.read(1)
            if resp and resp[0] == _ACK:
                break
        else:
            logger.error("XModem: EOT not acknowledged")
            return False

        # Drain trailing log lines ("[MSG:INFO: Received N bytes...]")
        tail = _read_raw(ser, timeout=3.0, silence=0.5)

    logger.info(f"XModem upload complete ({len(data)} bytes): {tail.strip()}")
    return True


def toggle_direction_pins(axes: list[str]) -> dict[str, bool]:
    """Toggle :low on the direction pins by rewriting the config file.

    Reads the active config from flash, flips the :low flag on each axis's
    direction_pin line, uploads the edited file back, and verifies the
    write by re-reading. Changes take effect after a controller restart.

    Returns {axis: new_inverted_state} for axes successfully toggled.
    Raises ConnectionError if no serial connection is available.
    """
    conn, _ser = _get_serial()
    # Hold the connection lock across the whole read→edit→upload→verify
    # sequence so status polls or pattern traffic can't interleave and
    # corrupt the file transfer (the lock is reentrant, so the nested
    # send_command/raw IO calls below are fine)
    with conn.lock:
        text = read_config_file()
        if not text:
            logger.error("Could not read config file from controller")
            return {}

        new_text, toggled = _toggle_direction_in_text(text, axes)
        if not toggled:
            logger.error(
                f"No direction_pin lines found for axes {axes} in config file "
                f"({len(text)} bytes read)"
            )
            return {}

        if not upload_config_file(new_text):
            return {}

        # Verify: re-read and confirm the toggled lines are on flash
        verify_text = read_config_file()
        if verify_text:
            _, would_toggle = _toggle_direction_in_text(verify_text, list(toggled.keys()))
            # Toggling the verified file should produce the OLD state — i.e. the
            # file currently holds the NEW state for every axis we changed
            for axis, new_state in toggled.items():
                if would_toggle.get(axis) == new_state:
                    logger.error(f"Verification failed: {axis} direction pin not updated on flash")
                    return {}

    logger.info(f"Direction pins toggled via config file: {toggled}")
    return toggled
