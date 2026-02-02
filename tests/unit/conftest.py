"""
Unit test conftest.py - Fixtures specific to unit tests.

Provides fixtures for mocking FastAPI dependencies and isolating tests
from real state and hardware connections.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.fixture
def mock_state_unit():
    """Mock state for unit tests with common defaults.

    This is a more comprehensive mock than the root conftest version,
    specifically designed for API endpoint testing where we need to
    control the application state precisely.
    """
    mock = MagicMock()

    # Connection mock
    mock.conn = MagicMock()
    mock.conn.is_connected.return_value = False
    mock.port = None
    mock.is_connected = False
    mock.preferred_port = None

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
    mock.hyperion_ip = None
    mock.hyperion_port = 19444
    mock.dw_led_num_leds = 60
    mock.dw_led_gpio_pin = 18
    mock.dw_led_pixel_order = "GRB"
    mock.dw_led_brightness = 50
    mock.dw_led_speed = 128
    mock.dw_led_intensity = 128
    mock.dw_led_idle_effect = "solid"
    mock.dw_led_playing_effect = "rainbow"
    mock.dw_led_idle_timeout_enabled = False
    mock.dw_led_idle_timeout_minutes = 30
    mock.dw_led_last_activity_time = 0

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

    # App settings
    mock.app_name = "Dune Weaver"
    mock.custom_logo_path = None

    # MQTT settings
    mock.mqtt_enabled = False
    mock.mqtt_broker = None
    mock.mqtt_port = 1883
    mock.mqtt_username = None
    mock.mqtt_password = None
    mock.mqtt_topic_prefix = "dune_weaver"

    # Table info
    mock.table_id = None
    mock.table_name = None
    mock.known_tables = []

    # Methods
    mock.save = MagicMock()
    mock.get_stop_event = MagicMock(return_value=None)
    mock.get_skip_event = MagicMock(return_value=None)
    mock.wait_for_interrupt = AsyncMock(return_value='timeout')
    mock.pause_condition = MagicMock()
    mock.pause_condition.__enter__ = MagicMock()
    mock.pause_condition.__exit__ = MagicMock()
    mock.pause_condition.notify_all = MagicMock()

    return mock


@pytest.fixture
def mock_connection_unit():
    """Mock connection for unit tests.

    Provides a connection mock that simulates a connected device
    without requiring actual hardware.
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
def app_with_mocked_state(mock_state_unit):
    """Fixture that patches state module before importing app.

    This ensures the app uses mocked state for all operations.
    Must be used before creating async_client.
    """
    with patch("modules.core.state.state", mock_state_unit):
        with patch("modules.core.pattern_manager.state", mock_state_unit):
            with patch("modules.core.playlist_manager.state", mock_state_unit):
                with patch("modules.connection.connection_manager.state", mock_state_unit):
                    from main import app
                    yield app, mock_state_unit


@pytest.fixture
async def async_client_with_mocked_state(app_with_mocked_state):
    """AsyncClient with mocked state for isolated API testing.

    This fixture combines the app patching with the async client creation.
    """
    from httpx import ASGITransport, AsyncClient

    app, mock_state = app_with_mocked_state

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client, mock_state


@pytest.fixture
def cleanup_app_overrides():
    """Fixture to ensure app.dependency_overrides is cleaned up after tests."""
    from main import app

    yield

    # Cleanup after test
    app.dependency_overrides.clear()
