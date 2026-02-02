"""
Integration test fixtures - Hardware detection and setup.

These fixtures help determine if real hardware is available
and provide setup/teardown for hardware-dependent tests.
"""
import pytest
import serial.tools.list_ports


def pytest_addoption(parser):
    """Add --run-hardware option to pytest CLI."""
    parser.addoption(
        "--run-hardware",
        action="store_true",
        default=False,
        help="Run tests that require real hardware connection"
    )


@pytest.fixture
def run_hardware(request):
    """Check if hardware tests should run."""
    return request.config.getoption("--run-hardware")


@pytest.fixture
def available_serial_ports():
    """Return list of available serial ports on this machine.

    Filters out known non-hardware ports like debug consoles.
    """
    IGNORE_PORTS = ['/dev/cu.debug-console', '/dev/cu.Bluetooth-Incoming-Port']
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports if port.device not in IGNORE_PORTS]


@pytest.fixture
def hardware_port(available_serial_ports, run_hardware):
    """Get a hardware port for testing, or skip if not available.

    This fixture:
    1. Checks if --run-hardware flag was passed
    2. Checks if any serial ports are available
    3. Returns the first available port or skips the test
    """
    if not run_hardware:
        pytest.skip("Hardware tests disabled (use --run-hardware to enable)")

    if not available_serial_ports:
        pytest.skip("No serial ports available for hardware testing")

    # Prefer USB ports over built-in ports
    usb_ports = [p for p in available_serial_ports if 'usb' in p.lower() or 'USB' in p]
    if usb_ports:
        return usb_ports[0]

    return available_serial_ports[0]


@pytest.fixture
def serial_connection(hardware_port):
    """Create a real serial connection for testing.

    This fixture establishes an actual serial connection to the hardware.
    The connection is automatically closed after the test.
    """
    import serial

    conn = serial.Serial(hardware_port, baudrate=115200, timeout=2)
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def fast_test_speed(run_hardware):
    """Set speed to 500 for faster integration tests.

    This fixture runs automatically for all integration tests.
    Restores original speed after the test.
    """
    if not run_hardware:
        yield
        return

    from modules.core.state import state

    original_speed = state.speed
    state.speed = 500  # Fast speed for tests

    yield

    state.speed = original_speed  # Restore original speed


@pytest.fixture(autouse=True)
def reset_asyncio_events(run_hardware):
    """Reset global asyncio primitives before each test.

    The pattern_manager uses global asyncio objects (Lock, Event) that are
    bound to the event loop where they were created. When TestClient creates
    its own event loop, these become incompatible.

    This fixture resets them to None so they get recreated in the current loop.
    Also ensures pause/stop state is cleared so tests start fresh.
    """
    if not run_hardware:
        yield
        return

    import modules.core.pattern_manager as pm
    from modules.core.state import state

    # Reset pattern_manager's global async primitives
    pm.pause_event = None
    pm.pattern_lock = None  # Will be recreated via get_pattern_lock()

    # Reset state's event loop tracking so events get recreated in new loop
    state._event_loop = None
    state._stop_event = None
    state._skip_event = None

    # Clear any lingering pause/stop state from previous tests
    state._pause_requested = False
    state._stop_requested = False
    state._skip_requested = False

    # Clear playback state
    state.current_playing_file = None
    state.current_playlist = None
    state.playlist_mode = None
    state.current_playlist_index = None

    yield

    # Clean up after test
    pm.pause_event = None
    pm.pattern_lock = None
    state._event_loop = None
    state._stop_event = None
    state._skip_event = None
    state._pause_requested = False
    state._stop_requested = False
    state._skip_requested = False
