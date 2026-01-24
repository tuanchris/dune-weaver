"""
Integration tests for hardware communication.

These tests require real hardware to be connected and are skipped by default.
Run with: pytest tests/integration/ --run-hardware

All tests in this file are marked with @pytest.mark.hardware and will
be automatically skipped in CI environments (when CI=true).
"""
import pytest
import time


@pytest.mark.hardware
class TestSerialConnection:
    """Tests for real serial connection to sand table hardware."""

    def test_serial_port_opens(self, serial_connection):
        """Test that we can open a serial connection to the hardware."""
        assert serial_connection.is_open
        assert serial_connection.baudrate == 115200

    def test_grbl_status_query(self, serial_connection):
        """Test querying GRBL status with '?' command.

        GRBL should respond with a status string like:
        <Idle|MPos:0.000,0.000,0.000|Bf:15,128>
        or
        <Idle|WPos:0.000,0.000,0.000|Bf:15,128>
        """
        # Clear any stale data
        serial_connection.reset_input_buffer()

        # Send status query
        serial_connection.write(b'?')
        serial_connection.flush()

        # Wait for response
        time.sleep(0.1)
        response = serial_connection.readline().decode().strip()

        # GRBL status starts with '<' and contains position info
        assert response.startswith('<'), f"Expected GRBL status, got: {response}"
        assert 'Pos:' in response, f"Expected position data in: {response}"

    def test_grbl_settings_query(self, serial_connection):
        """Test querying GRBL settings with '$$' command.

        GRBL should respond with settings like:
        $0=10
        $1=25
        ...
        ok
        """
        # Clear any stale data
        serial_connection.reset_input_buffer()

        # Send settings query
        serial_connection.write(b'$$\n')
        serial_connection.flush()

        # Collect all response lines
        responses = []
        timeout = time.time() + 2  # 2 second timeout

        while time.time() < timeout:
            if serial_connection.in_waiting:
                line = serial_connection.readline().decode().strip()
                responses.append(line)
                if line == 'ok':
                    break
            time.sleep(0.01)

        # Should have received settings
        assert len(responses) > 1, "Expected GRBL settings response"
        assert responses[-1] == 'ok', f"Expected 'ok' at end, got: {responses[-1]}"

        # At least some settings should start with '$'
        settings = [r for r in responses if r.startswith('$')]
        assert len(settings) > 0, "Expected at least one setting line"


@pytest.mark.hardware
class TestConnectionManager:
    """Integration tests for the connection_manager module with real hardware."""

    def test_list_serial_ports_finds_hardware(self, available_serial_ports, run_hardware):
        """Test that list_serial_ports finds the connected hardware."""
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager

        ports = connection_manager.list_serial_ports()

        # Should find at least one port
        assert len(ports) > 0, "Expected to find at least one serial port"

        # Should match what we found independently
        for port in available_serial_ports:
            if 'usb' in port.lower() or 'tty' in port.lower():
                assert port in ports or any(port in p for p in ports)

    def test_serial_connection_class(self, hardware_port, run_hardware):
        """Test SerialConnection class with real hardware.

        This tests the actual SerialConnection wrapper from connection_manager.
        """
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection.connection_manager import SerialConnection

        conn = SerialConnection(hardware_port)
        try:
            assert conn.is_connected()

            # Send status query
            conn.send('?')
            time.sleep(0.1)

            response = conn.readline()
            assert '<' in response, f"Expected GRBL status, got: {response}"
        finally:
            conn.close()


@pytest.mark.hardware
@pytest.mark.slow
class TestHardwareOperations:
    """Slow integration tests that perform actual hardware operations.

    These tests take longer and may move the hardware.
    Use with caution!
    """

    def test_soft_reset(self, serial_connection):
        """Test GRBL soft reset (Ctrl+X).

        This sends a soft reset command and verifies GRBL responds
        with its startup message.
        """
        # Send soft reset (Ctrl+X = 0x18)
        serial_connection.write(b'\x18')
        serial_connection.flush()

        # Wait for reset and startup message
        time.sleep(1)

        # Collect responses
        responses = []
        timeout = time.time() + 3

        while time.time() < timeout:
            if serial_connection.in_waiting:
                line = serial_connection.readline().decode().strip()
                if line:
                    responses.append(line)
            time.sleep(0.01)

        # GRBL should output startup message containing "Grbl"
        all_responses = ' '.join(responses)
        assert 'Grbl' in all_responses or 'grbl' in all_responses.lower(), \
            f"Expected GRBL startup message, got: {responses}"
