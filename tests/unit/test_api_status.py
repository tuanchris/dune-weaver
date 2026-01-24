"""
Unit tests for status and info API endpoints.

Tests the following endpoints:
- GET /serial_status
- GET /list_serial_ports
- GET /api/settings
- GET /api/table-info
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestSerialStatus:
    """Tests for /serial_status endpoint."""

    @pytest.mark.asyncio
    async def test_serial_status_when_connected(self, async_client, mock_state):
        """Test serial_status returns connected state."""
        mock_state.conn = MagicMock()
        mock_state.conn.is_connected.return_value = True
        mock_state.port = "/dev/ttyUSB0"
        mock_state.preferred_port = "__auto__"

        with patch("main.state", mock_state):
            response = await async_client.get("/serial_status")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["port"] == "/dev/ttyUSB0"
        assert data["preferred_port"] == "__auto__"

    @pytest.mark.asyncio
    async def test_serial_status_when_disconnected(self, async_client, mock_state):
        """Test serial_status returns disconnected state."""
        mock_state.conn = None
        mock_state.port = None
        mock_state.preferred_port = "__none__"

        with patch("main.state", mock_state):
            response = await async_client.get("/serial_status")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False
        assert data["port"] is None
        assert data["preferred_port"] == "__none__"

    @pytest.mark.asyncio
    async def test_serial_status_with_disconnected_conn(self, async_client, mock_state):
        """Test serial_status when conn exists but is disconnected."""
        mock_state.conn = MagicMock()
        mock_state.conn.is_connected.return_value = False
        mock_state.port = "/dev/ttyUSB0"
        mock_state.preferred_port = "/dev/ttyUSB0"

        with patch("main.state", mock_state):
            response = await async_client.get("/serial_status")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False


class TestListSerialPorts:
    """Tests for /list_serial_ports endpoint."""

    @pytest.mark.asyncio
    async def test_list_serial_ports_returns_list(self, async_client):
        """Test list_serial_ports returns a list of available ports."""
        mock_ports = ["/dev/ttyUSB0", "/dev/ttyACM0"]

        with patch("main.connection_manager.list_serial_ports", return_value=mock_ports):
            response = await async_client.get("/list_serial_ports")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert "/dev/ttyUSB0" in data
        assert "/dev/ttyACM0" in data

    @pytest.mark.asyncio
    async def test_list_serial_ports_empty(self, async_client):
        """Test list_serial_ports returns empty list when no ports."""
        with patch("main.connection_manager.list_serial_ports", return_value=[]):
            response = await async_client.get("/list_serial_ports")

        assert response.status_code == 200
        data = response.json()
        assert data == []


class TestGetAllSettings:
    """Tests for /api/settings endpoint."""

    @pytest.mark.asyncio
    async def test_get_all_settings_returns_expected_structure(self, async_client, mock_state):
        """Test get_all_settings returns complete settings structure."""
        mock_state.app_name = "Test Table"
        mock_state.custom_logo = None
        mock_state.preferred_port = "__auto__"
        mock_state.clear_pattern_speed = 150
        mock_state.custom_clear_from_in = None
        mock_state.custom_clear_from_out = None
        mock_state.auto_play_enabled = False
        mock_state.auto_play_playlist = None
        mock_state.auto_play_run_mode = "single"
        mock_state.auto_play_pause_time = 0
        mock_state.auto_play_clear_pattern = None
        mock_state.auto_play_shuffle = False
        mock_state.scheduled_pause_enabled = False
        mock_state.scheduled_pause_control_wled = False
        mock_state.scheduled_pause_finish_pattern = False
        mock_state.scheduled_pause_timezone = None
        mock_state.scheduled_pause_time_slots = []
        mock_state.homing = 0
        mock_state.homing_user_override = False
        mock_state.angular_homing_offset_degrees = 0.0
        mock_state.auto_home_enabled = False
        mock_state.auto_home_after_patterns = 10
        mock_state.led_provider = "none"
        mock_state.wled_ip = None
        mock_state.dw_led_num_leds = 60
        mock_state.dw_led_gpio_pin = 18
        mock_state.dw_led_pixel_order = "GRB"
        mock_state.dw_led_brightness = 50
        mock_state.dw_led_speed = 128
        mock_state.dw_led_intensity = 128
        mock_state.dw_led_idle_effect = "solid"
        mock_state.dw_led_playing_effect = "rainbow"
        mock_state.dw_led_idle_timeout_enabled = False
        mock_state.dw_led_idle_timeout_minutes = 30
        mock_state.mqtt_enabled = False
        mock_state.mqtt_broker = None
        mock_state.mqtt_port = 1883
        mock_state.mqtt_username = None
        mock_state.mqtt_password = None
        mock_state.mqtt_client_id = "dune_weaver"
        mock_state.mqtt_discovery_prefix = "homeassistant"
        mock_state.mqtt_device_id = "dune_weaver_01"
        mock_state.mqtt_device_name = "Dune Weaver"
        mock_state.table_type = "dune_weaver"
        mock_state.table_type_override = None
        mock_state.gear_ratio = 10.0
        mock_state.x_steps_per_mm = 200.0
        mock_state.y_steps_per_mm = 287.0
        mock_state.timezone = "UTC"

        with patch("main.state", mock_state):
            response = await async_client.get("/api/settings")

        assert response.status_code == 200
        data = response.json()

        # Check top-level structure
        assert "app" in data
        assert "connection" in data
        assert "patterns" in data
        assert "auto_play" in data
        assert "scheduled_pause" in data
        assert "homing" in data
        assert "led" in data
        assert "mqtt" in data
        assert "machine" in data

        # Verify specific values
        assert data["app"]["name"] == "Test Table"
        assert data["connection"]["preferred_port"] == "__auto__"
        assert data["patterns"]["clear_pattern_speed"] == 150
        assert data["machine"]["detected_table_type"] == "dune_weaver"

    @pytest.mark.asyncio
    async def test_get_all_settings_effective_table_type(self, async_client, mock_state):
        """Test that effective_table_type uses override when set."""
        mock_state.app_name = "Test"
        mock_state.custom_logo = None
        mock_state.preferred_port = None
        mock_state.clear_pattern_speed = None
        mock_state.custom_clear_from_in = None
        mock_state.custom_clear_from_out = None
        mock_state.auto_play_enabled = False
        mock_state.auto_play_playlist = None
        mock_state.auto_play_run_mode = "single"
        mock_state.auto_play_pause_time = 0
        mock_state.auto_play_clear_pattern = None
        mock_state.auto_play_shuffle = False
        mock_state.scheduled_pause_enabled = False
        mock_state.scheduled_pause_control_wled = False
        mock_state.scheduled_pause_finish_pattern = False
        mock_state.scheduled_pause_timezone = None
        mock_state.scheduled_pause_time_slots = []
        mock_state.homing = 0
        mock_state.homing_user_override = False
        mock_state.angular_homing_offset_degrees = 0.0
        mock_state.auto_home_enabled = False
        mock_state.auto_home_after_patterns = 10
        mock_state.led_provider = "none"
        mock_state.wled_ip = None
        mock_state.dw_led_num_leds = 60
        mock_state.dw_led_gpio_pin = 18
        mock_state.dw_led_pixel_order = "GRB"
        mock_state.dw_led_brightness = 50
        mock_state.dw_led_speed = 128
        mock_state.dw_led_intensity = 128
        mock_state.dw_led_idle_effect = "solid"
        mock_state.dw_led_playing_effect = "rainbow"
        mock_state.dw_led_idle_timeout_enabled = False
        mock_state.dw_led_idle_timeout_minutes = 30
        mock_state.mqtt_enabled = False
        mock_state.mqtt_broker = None
        mock_state.mqtt_port = 1883
        mock_state.mqtt_username = None
        mock_state.mqtt_password = None
        mock_state.mqtt_client_id = "dune_weaver"
        mock_state.mqtt_discovery_prefix = "homeassistant"
        mock_state.mqtt_device_id = "dune_weaver_01"
        mock_state.mqtt_device_name = "Dune Weaver"
        mock_state.table_type = "dune_weaver"
        mock_state.table_type_override = "dune_weaver_mini"  # Override set
        mock_state.gear_ratio = 6.25
        mock_state.x_steps_per_mm = 256.0
        mock_state.y_steps_per_mm = 180.0
        mock_state.timezone = "UTC"

        with patch("main.state", mock_state):
            response = await async_client.get("/api/settings")

        assert response.status_code == 200
        data = response.json()

        assert data["machine"]["detected_table_type"] == "dune_weaver"
        assert data["machine"]["table_type_override"] == "dune_weaver_mini"
        assert data["machine"]["effective_table_type"] == "dune_weaver_mini"


class TestGetTableInfo:
    """Tests for /api/table-info endpoint."""

    @pytest.mark.asyncio
    async def test_get_table_info(self, async_client, mock_state):
        """Test get_table_info returns table identification info."""
        mock_state.table_id = "table-123"
        mock_state.table_name = "Living Room Table"

        with patch("main.state", mock_state):
            with patch("main.version_manager.get_current_version", return_value="1.0.0"):
                response = await async_client.get("/api/table-info")

        assert response.status_code == 200
        data = response.json()
        # API returns "id" and "name", not "table_id" and "table_name"
        assert data["id"] == "table-123"
        assert data["name"] == "Living Room Table"
        assert data["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_get_table_info_not_set(self, async_client, mock_state):
        """Test get_table_info when not configured."""
        mock_state.table_id = None
        mock_state.table_name = None

        with patch("main.state", mock_state):
            with patch("main.version_manager.get_current_version", return_value="1.0.0"):
                response = await async_client.get("/api/table-info")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] is None
        assert data["name"] is None
