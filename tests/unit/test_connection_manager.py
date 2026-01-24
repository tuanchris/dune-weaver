"""
Unit tests for connection_manager parsing functions.

Tests the pure functions that parse GRBL responses:
- Machine position parsing (MPos and WPos formats)
- Serial port listing/filtering
"""
import pytest
from unittest.mock import patch, MagicMock


class TestParseMachinePosition:
    """Tests for parse_machine_position function."""

    def test_parse_machine_position_mpos_format(self):
        """Test parsing MPos format from GRBL status response."""
        from modules.connection.connection_manager import parse_machine_position

        response = "<Idle|MPos:100.500,-50.250,0.000|Bf:15,128>"
        result = parse_machine_position(response)

        assert result is not None
        assert result == (100.5, -50.25)

    def test_parse_machine_position_wpos_format(self):
        """Test parsing WPos format from GRBL status response."""
        from modules.connection.connection_manager import parse_machine_position

        response = "<Idle|WPos:0.000,19.000,0.000|Bf:15,128>"
        result = parse_machine_position(response)

        assert result is not None
        assert result == (0.0, 19.0)

    def test_parse_machine_position_prefers_mpos(self):
        """Test that MPos is preferred when both are present (rare but possible)."""
        from modules.connection.connection_manager import parse_machine_position

        # This response has both MPos and WPos - MPos should be used first
        response = "<Idle|MPos:10.0,20.0,0.0|WPos:5.0,10.0,0.0|Bf:15,128>"
        result = parse_machine_position(response)

        assert result is not None
        assert result == (10.0, 20.0)

    def test_parse_machine_position_invalid(self):
        """Test parsing returns None for invalid response."""
        from modules.connection.connection_manager import parse_machine_position

        # No position info
        result = parse_machine_position("ok")
        assert result is None

        # Empty string
        result = parse_machine_position("")
        assert result is None

        # Malformed response
        result = parse_machine_position("<Idle|Bf:15,128>")
        assert result is None

    def test_parse_machine_position_run_state(self):
        """Test parsing position during run state."""
        from modules.connection.connection_manager import parse_machine_position

        response = "<Run|MPos:-994.869,-321.861,0.000|Bf:15,127>"
        result = parse_machine_position(response)

        assert result is not None
        assert result[0] == pytest.approx(-994.869)
        assert result[1] == pytest.approx(-321.861)

    def test_parse_machine_position_alarm_state(self):
        """Test parsing position during alarm state."""
        from modules.connection.connection_manager import parse_machine_position

        response = "<Alarm|MPos:0.000,0.000,0.000|Bf:15,128|Pn:XY>"
        result = parse_machine_position(response)

        assert result is not None
        assert result == (0.0, 0.0)

    def test_parse_machine_position_with_extra_info(self):
        """Test parsing position with extra fields in response."""
        from modules.connection.connection_manager import parse_machine_position

        # Response with WCO (Work Coordinate Offset)
        response = "<Idle|MPos:5.0,10.0,0.0|FS:0,0|WCO:0,0,0>"
        result = parse_machine_position(response)

        assert result is not None
        assert result == (5.0, 10.0)

    def test_parse_machine_position_negative_coords(self):
        """Test parsing negative coordinates."""
        from modules.connection.connection_manager import parse_machine_position

        response = "<Idle|MPos:-100.123,-200.456,0.000|Bf:15,128>"
        result = parse_machine_position(response)

        assert result is not None
        assert result[0] == pytest.approx(-100.123)
        assert result[1] == pytest.approx(-200.456)

    def test_parse_machine_position_high_precision(self):
        """Test parsing high precision coordinates."""
        from modules.connection.connection_manager import parse_machine_position

        response = "<Idle|MPos:123.456789,987.654321,0.000000|Bf:15,128>"
        result = parse_machine_position(response)

        assert result is not None
        assert result[0] == pytest.approx(123.456789)
        assert result[1] == pytest.approx(987.654321)


class TestListSerialPorts:
    """Tests for list_serial_ports function."""

    def test_list_serial_ports_filters_ignored(self):
        """Test that ignored ports are filtered out."""
        # Create mock port objects
        mock_port1 = MagicMock()
        mock_port1.device = "/dev/ttyUSB0"

        mock_port2 = MagicMock()
        mock_port2.device = "/dev/cu.debug-console"  # Should be filtered

        mock_port3 = MagicMock()
        mock_port3.device = "/dev/cu.Bluetooth-Incoming-Port"  # Should be filtered

        mock_port4 = MagicMock()
        mock_port4.device = "/dev/ttyACM0"

        with patch("serial.tools.list_ports.comports", return_value=[mock_port1, mock_port2, mock_port3, mock_port4]):
            from modules.connection.connection_manager import list_serial_ports

            ports = list_serial_ports()

        assert "/dev/ttyUSB0" in ports
        assert "/dev/ttyACM0" in ports
        assert "/dev/cu.debug-console" not in ports
        assert "/dev/cu.Bluetooth-Incoming-Port" not in ports
        assert len(ports) == 2

    def test_list_serial_ports_empty(self):
        """Test list_serial_ports returns empty when no ports available."""
        with patch("serial.tools.list_ports.comports", return_value=[]):
            from modules.connection.connection_manager import list_serial_ports

            ports = list_serial_ports()

        assert ports == []

    def test_list_serial_ports_all_ignored(self):
        """Test list_serial_ports when all ports are ignored."""
        mock_port1 = MagicMock()
        mock_port1.device = "/dev/cu.debug-console"

        mock_port2 = MagicMock()
        mock_port2.device = "/dev/cu.Bluetooth-Incoming-Port"

        with patch("serial.tools.list_ports.comports", return_value=[mock_port1, mock_port2]):
            from modules.connection.connection_manager import list_serial_ports

            ports = list_serial_ports()

        assert ports == []


class TestConnectionClasses:
    """Tests for connection class structure (no hardware required)."""

    def test_base_connection_interface(self):
        """Test that BaseConnection defines required interface."""
        from modules.connection.connection_manager import BaseConnection

        # BaseConnection should have these abstract methods
        base = BaseConnection()

        with pytest.raises(NotImplementedError):
            base.send("test")

        with pytest.raises(NotImplementedError):
            base.flush()

        with pytest.raises(NotImplementedError):
            base.readline()

        with pytest.raises(NotImplementedError):
            base.in_waiting()

        with pytest.raises(NotImplementedError):
            base.is_connected()

        with pytest.raises(NotImplementedError):
            base.close()

    def test_serial_connection_inherits_base(self):
        """Test SerialConnection inherits from BaseConnection."""
        from modules.connection.connection_manager import SerialConnection, BaseConnection

        assert issubclass(SerialConnection, BaseConnection)

    def test_websocket_connection_inherits_base(self):
        """Test WebSocketConnection inherits from BaseConnection."""
        from modules.connection.connection_manager import WebSocketConnection, BaseConnection

        assert issubclass(WebSocketConnection, BaseConnection)


class TestIgnorePorts:
    """Tests for IGNORE_PORTS and DEPRIORITIZED_PORTS constants."""

    def test_ignore_ports_defined(self):
        """Test that IGNORE_PORTS constant is defined."""
        from modules.connection.connection_manager import IGNORE_PORTS

        assert isinstance(IGNORE_PORTS, list)
        assert "/dev/cu.debug-console" in IGNORE_PORTS
        assert "/dev/cu.Bluetooth-Incoming-Port" in IGNORE_PORTS

    def test_deprioritized_ports_defined(self):
        """Test that DEPRIORITIZED_PORTS constant is defined."""
        from modules.connection.connection_manager import DEPRIORITIZED_PORTS

        assert isinstance(DEPRIORITIZED_PORTS, list)
        # ttyS0 is typically the Pi hardware UART - should be deprioritized
        assert "/dev/ttyS0" in DEPRIORITIZED_PORTS


class TestIsMachineIdle:
    """Tests for is_machine_idle function."""

    def test_is_machine_idle_no_connection(self, mock_state):
        """Test is_machine_idle returns False when no connection."""
        mock_state.conn = None

        with patch("modules.connection.connection_manager.state", mock_state):
            from modules.connection.connection_manager import is_machine_idle

            result = is_machine_idle()

        assert result is False

    def test_is_machine_idle_disconnected(self, mock_state):
        """Test is_machine_idle returns False when disconnected."""
        mock_state.conn.is_connected.return_value = False

        with patch("modules.connection.connection_manager.state", mock_state):
            from modules.connection.connection_manager import is_machine_idle

            result = is_machine_idle()

        assert result is False

    def test_is_machine_idle_when_idle(self, mock_state):
        """Test is_machine_idle returns True when machine is idle."""
        mock_state.conn.is_connected.return_value = True
        mock_state.conn.send = MagicMock()
        mock_state.conn.readline.return_value = "<Idle|MPos:0,0,0|Bf:15,128>"

        with patch("modules.connection.connection_manager.state", mock_state):
            from modules.connection.connection_manager import is_machine_idle

            result = is_machine_idle()

        assert result is True
        mock_state.conn.send.assert_called_with('?')

    def test_is_machine_idle_when_running(self, mock_state):
        """Test is_machine_idle returns False when machine is running."""
        mock_state.conn.is_connected.return_value = True
        mock_state.conn.send = MagicMock()
        mock_state.conn.readline.return_value = "<Run|MPos:0,0,0|Bf:15,128>"

        with patch("modules.connection.connection_manager.state", mock_state):
            from modules.connection.connection_manager import is_machine_idle

            result = is_machine_idle()

        assert result is False
