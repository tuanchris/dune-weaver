"""
Root conftest.py - Shared fixtures for all tests.

This file provides:
- CI environment detection for auto-skipping hardware tests
- AsyncClient fixture for API testing
- Mock state fixture for isolated testing
"""
import os
import pytest
from unittest.mock import MagicMock, AsyncMock


def pytest_configure(config):
    """Configure pytest with custom markers and CI detection."""
    # Register custom markers
    config.addinivalue_line(
        "markers", "hardware: marks tests requiring real hardware (skip in CI)"
    )
    config.addinivalue_line(
        "markers", "slow: marks slow tests"
    )


def pytest_collection_modifyitems(config, items):
    """Auto-skip hardware tests when CI=true environment variable is set."""
    if os.environ.get("CI"):
        skip_hardware = pytest.mark.skip(reason="Hardware not available in CI")
        for item in items:
            if "hardware" in item.keywords:
                item.add_marker(skip_hardware)


@pytest.fixture
async def async_client():
    """Async HTTP client for testing API endpoints.

    Uses httpx AsyncClient with ASGITransport to test FastAPI app directly
    without starting a server.
    """
    from httpx import ASGITransport, AsyncClient
    from main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def mock_state():
    """Mock global state object for isolated testing.

    Returns a MagicMock configured with common defaults to simulate
    the application state without affecting real state.
    """
    mock = MagicMock()

    # Connection mock
    mock.conn = MagicMock()
    mock.conn.is_connected.return_value = False
    mock.port = None
    mock.is_connected = False

    # Pattern execution state
    mock.current_playing_file = None
    mock.is_running = False
    mock.pause_requested = False
    mock.stop_requested = False
    mock.skip_requested = False
    mock.execution_progress = None
    mock.is_homing = False
    mock.is_clearing = False

    # Position state
    mock.current_theta = 0.0
    mock.current_rho = 0.0
    mock.machine_x = 0.0
    mock.machine_y = 0.0

    # Speed and settings
    mock.speed = 100
    mock.clear_pattern_speed = None
    mock.table_type = "dune_weaver"
    mock.table_type_override = None
    mock.homing = 0

    # Playlist state
    mock.current_playlist = None
    mock.current_playlist_name = None
    mock.current_playlist_index = None
    mock.playlist_mode = None
    mock.pause_time_remaining = 0
    mock.original_pause_time = None

    # LED state
    mock.led_controller = None
    mock.led_provider = "none"
    mock.wled_ip = None
    mock.dw_led_idle_effect = "solid"
    mock.dw_led_playing_effect = "rainbow"
    mock.dw_led_idle_timeout_enabled = False
    mock.dw_led_idle_timeout_minutes = 30

    # Scheduled pause
    mock.scheduled_pause_enabled = False
    mock.scheduled_pause_time_slots = []
    mock.scheduled_pause_control_wled = False
    mock.scheduled_pause_finish_pattern = False
    mock.scheduled_pause_timezone = None

    # Steps and gear ratio
    mock.x_steps_per_mm = 200.0
    mock.y_steps_per_mm = 287.0
    mock.gear_ratio = 10.0

    # Auto-home settings
    mock.auto_home_enabled = False
    mock.auto_home_after_patterns = 10
    mock.patterns_since_last_home = 0

    # Custom clear patterns
    mock.custom_clear_from_out = None
    mock.custom_clear_from_in = None

    # Homing offset
    mock.angular_homing_offset_degrees = 0.0

    # Methods
    mock.save = MagicMock()
    mock.get_stop_event = MagicMock(return_value=None)
    mock.get_skip_event = MagicMock(return_value=None)
    mock.wait_for_interrupt = AsyncMock(return_value='timeout')

    return mock


@pytest.fixture
def mock_connection():
    """Mock connection object for testing hardware communication.

    Returns a MagicMock configured to simulate serial/websocket connection.
    """
    mock = MagicMock()
    mock.is_connected.return_value = True
    mock.send = MagicMock()
    mock.readline = MagicMock(return_value="ok")
    mock.in_waiting = MagicMock(return_value=0)
    mock.flush = MagicMock()
    mock.close = MagicMock()
    mock.reset_input_buffer = MagicMock()
    return mock


@pytest.fixture
def patterns_dir(tmp_path):
    """Create a temporary patterns directory for testing.

    Returns the path to a temporary directory that can be used
    for pattern file operations during tests.
    """
    patterns = tmp_path / "patterns"
    patterns.mkdir()
    return patterns
