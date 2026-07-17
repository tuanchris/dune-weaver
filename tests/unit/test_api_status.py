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
        """Test serial_status returns connected state and the board URL."""
        mock_state.conn = MagicMock()
        mock_state.conn.is_connected.return_value = True

        with patch("main.state", mock_state), \
             patch("main.connection_manager.board_url", return_value="http://192.168.68.160"):
            response = await async_client.get("/serial_status")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["port"] == "http://192.168.68.160"

    @pytest.mark.asyncio
    async def test_serial_status_when_disconnected(self, async_client, mock_state):
        """Test serial_status still reports the configured board URL when disconnected."""
        mock_state.conn = None

        with patch("main.state", mock_state), \
             patch("main.connection_manager.board_url", return_value="http://192.168.68.160"):
            response = await async_client.get("/serial_status")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False
        assert data["port"] == "http://192.168.68.160"

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

        with patch("main.connection_manager.list_board_urls", return_value=mock_ports):
            response = await async_client.get("/list_serial_ports")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert "/dev/ttyUSB0" in data
        assert "/dev/ttyACM0" in data

    @pytest.mark.asyncio
    async def test_list_serial_ports_empty(self, async_client):
        """Test list_serial_ports returns empty list when no ports."""
        with patch("main.connection_manager.list_board_urls", return_value=[]):
            response = await async_client.get("/list_serial_ports")

        assert response.status_code == 200
        data = response.json()
        assert data == []


class TestGetAllSettings:
    """Tests for /api/settings endpoint."""

    @pytest.mark.asyncio
    async def test_get_all_settings_returns_expected_structure(self, async_client, mock_state):
        """Test get_all_settings returns the unified settings structure."""
        mock_state.app_name = "Test Table"
        mock_state.custom_logo = None
        mock_state.clear_pattern_speed = 150
        mock_state.custom_clear_from_in = None
        mock_state.custom_clear_from_out = None
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
        mock_state.dw_led_control_mode = "automated"
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
        mock_state.timezone = "UTC"

        with patch("main.state", mock_state):
            response = await async_client.get("/api/settings")

        assert response.status_code == 200
        data = response.json()

        # Check top-level structure (auto_play/connection are gone: auto-play
        # lives on the board, serial ports no longer exist)
        assert "app" in data
        assert "patterns" in data
        assert "scheduled_pause" in data
        assert "homing" in data
        assert "led" in data
        assert "mqtt" in data
        assert "machine" in data
        assert "auto_play" not in data
        assert "connection" not in data

        # Verify specific values
        assert data["app"]["name"] == "Test Table"
        assert data["patterns"]["clear_pattern_speed"] == 150
        assert data["machine"]["timezone"] == "UTC"


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
