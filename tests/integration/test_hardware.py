"""
Integration tests for hardware communication.

These tests require real hardware to be connected and are skipped by default.
Run with: pytest tests/integration/ --run-hardware

All tests in this file are marked with @pytest.mark.hardware and will
be automatically skipped in CI environments (when CI=true).

Test order matters for some tests - they build on each other:
1. test_homing_sequence - Homes the table (required first)
2. test_move_to_perimeter - Moves ball to edge
3. test_move_to_center - Moves ball to center
4. test_execute_star_pattern - Runs a full pattern
"""
import pytest
import time
import os
import json
import asyncio


@pytest.mark.hardware
class TestSerialConnection:
    """Tests for real serial connection to sand table hardware."""

    def test_serial_port_opens(self, serial_connection):
        """Test that we can open a serial connection to the hardware."""
        assert serial_connection.is_open
        assert serial_connection.baudrate == 115200

    def test_grbl_status_query(self, serial_connection):
        """Test querying GRBL status with '?' command.

        GRBL responds with a status string like:
        <Idle|MPos:0.000,0.000,0.000|Bf:15,128>
        <Run|MPos:10.000,5.000,0.000|Bf:15,128>
        <Hold|WPos:0.000,0.000,0.000|Bf:15,128>

        Note: Table may be in any state (Idle, Run, Hold, Alarm, etc.)
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
        # Don't assume Idle - table could be in Run, Hold, Alarm, etc.
        assert response.startswith('<'), f"Expected GRBL status starting with '<', got: {response}"
        assert 'Pos:' in response, f"Expected position data (MPos or WPos) in: {response}"
        assert '>' in response, f"Expected closing '>' in status: {response}"

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

    def test_firmware_detection(self, hardware_port, run_hardware):
        """Test firmware type detection (FluidNC vs GRBL)."""
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection.connection_manager import SerialConnection, _detect_firmware
        from modules.core.state import state

        conn = SerialConnection(hardware_port)
        state.conn = conn
        try:
            firmware_type, version = _detect_firmware()

            # Should detect one of the known firmware types
            assert firmware_type in ['fluidnc', 'grbl', 'unknown'], \
                f"Unexpected firmware type: {firmware_type}"

            print(f"Detected firmware: {firmware_type} {version or ''}")
        finally:
            conn.close()
            state.conn = None


@pytest.mark.hardware
@pytest.mark.slow
class TestSoftReset:
    """Tests for soft reset functionality."""

    def test_soft_reset(self, hardware_port, run_hardware):
        """Test soft reset using firmware-appropriate command.

        FluidNC uses $Bye, GRBL uses Ctrl+X (0x18).
        The test auto-detects firmware type and sends the correct command.
        """
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection.connection_manager import SerialConnection, _detect_firmware
        from modules.core.state import state

        conn = SerialConnection(hardware_port)
        state.conn = conn
        try:
            # Detect firmware to determine reset command
            firmware_type, _ = _detect_firmware()

            # Clear buffer
            conn.ser.reset_input_buffer()

            # Send appropriate reset command
            if firmware_type == 'fluidnc':
                conn.ser.write(b'$Bye\n')
                reset_cmd = '$Bye'
            else:
                conn.ser.write(b'\x18')
                reset_cmd = 'Ctrl+X'

            conn.flush()
            print(f"Sent {reset_cmd} reset command")

            # Wait for reset and startup message
            time.sleep(1.5)

            # Collect responses
            responses = []
            timeout = time.time() + 3

            while time.time() < timeout:
                if conn.ser.in_waiting:
                    line = conn.ser.readline().decode().strip()
                    if line:
                        responses.append(line)
                        print(f"  Response: {line}")
                time.sleep(0.01)

            # Should see GRBL/FluidNC startup message
            all_responses = ' '.join(responses)
            assert 'Grbl' in all_responses or 'grbl' in all_responses.lower() or 'FluidNC' in all_responses, \
                f"Expected GRBL/FluidNC startup message, got: {responses}"

        finally:
            conn.close()
            state.conn = None


@pytest.mark.hardware
@pytest.mark.slow
class TestTableMovement:
    """Tests for table movement operations.

    IMPORTANT: These tests physically move the table!
    Run in order: homing -> perimeter -> center -> pattern
    """

    def test_homing_sequence(self, hardware_port, run_hardware):
        """Test full homing sequence.

        This test:
        1. Connects to hardware
        2. Runs the homing procedure
        3. Verifies position matches the configured homing offset
        """
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        import math
        from modules.connection import connection_manager
        from modules.core.state import state

        # Connect and initialize
        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            # Run homing (timeout 120 seconds for crash homing)
            print("Starting homing sequence...")
            success = connection_manager.home(timeout=120)

            assert success, "Homing sequence failed"

            # After homing, theta should match the configured angular_homing_offset_degrees
            # (converted to radians), and rho should be near 0
            expected_theta = math.radians(state.angular_homing_offset_degrees)
            theta_diff = abs(state.current_theta - expected_theta)

            assert theta_diff < 0.1, \
                f"Expected theta near {expected_theta:.3f} rad ({state.angular_homing_offset_degrees}°), got: {state.current_theta:.3f}"
            assert abs(state.current_rho) < 0.1, \
                f"Expected rho near 0 after homing, got: {state.current_rho}"

            print(f"Homing complete: theta={state.current_theta:.3f} rad (offset={state.angular_homing_offset_degrees}°), rho={state.current_rho:.3f}")

        finally:
            conn.close()
            state.conn = None

    def test_move_to_perimeter(self, hardware_port, run_hardware):
        """Test moving ball to perimeter (rho=1.0).

        Moves the ball from current position to the outer edge of the table.
        """
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager
        from modules.core import pattern_manager
        from modules.core.state import state

        # Connect
        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            # Start motion controller
            if not pattern_manager.motion_controller.running:
                pattern_manager.motion_controller.start()

            # Move to perimeter (theta=0, rho=1.0)
            print("Moving to perimeter (rho=1.0)...")

            async def do_move():
                await pattern_manager.move_polar(theta=0, rho=1.0, speed=200)

            asyncio.get_event_loop().run_until_complete(do_move())

            # Wait for movement to complete
            time.sleep(2)

            # Verify we're near the perimeter
            assert state.current_rho > 0.9, \
                f"Expected rho near 1.0, got: {state.current_rho}"

            print(f"At perimeter: theta={state.current_theta}, rho={state.current_rho}")

        finally:
            pattern_manager.motion_controller.stop()
            conn.close()
            state.conn = None

    def test_move_to_center(self, hardware_port, run_hardware):
        """Test moving ball to center (rho=0.0).

        Moves the ball from current position to the center of the table.
        """
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager
        from modules.core import pattern_manager
        from modules.core.state import state

        # Connect
        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            # Start motion controller
            if not pattern_manager.motion_controller.running:
                pattern_manager.motion_controller.start()

            # Move to center (theta=0, rho=0.0)
            print("Moving to center (rho=0.0)...")

            async def do_move():
                await pattern_manager.move_polar(theta=0, rho=0.0, speed=200)

            asyncio.get_event_loop().run_until_complete(do_move())

            # Wait for movement to complete
            time.sleep(2)

            # Verify we're near the center
            assert state.current_rho < 0.1, \
                f"Expected rho near 0.0, got: {state.current_rho}"

            print(f"At center: theta={state.current_theta}, rho={state.current_rho}")

        finally:
            pattern_manager.motion_controller.stop()
            conn.close()
            state.conn = None

    def test_execute_star_pattern(self, hardware_port, run_hardware):
        """Test executing the star.thr pattern.

        This runs a full pattern execution and verifies it completes successfully.
        The star pattern is relatively quick and good for testing.
        """
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager
        from modules.core import pattern_manager
        from modules.core.state import state

        # Connect
        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            pattern_path = './patterns/star.thr'
            assert os.path.exists(pattern_path), f"Pattern file not found: {pattern_path}"

            print(f"Executing pattern: {pattern_path}")

            async def run_pattern():
                await pattern_manager.run_theta_rho_file(pattern_path)

            asyncio.get_event_loop().run_until_complete(run_pattern())

            # Pattern should have completed
            assert state.current_playing_file is None, \
                "Pattern should have completed (current_playing_file should be None)"

            print("Pattern execution completed successfully")

        finally:
            conn.close()
            state.conn = None


@pytest.mark.hardware
class TestWebSocketConnection:
    """Tests for WebSocket connection to FluidNC."""

    def test_websocket_status_endpoint(self, run_hardware):
        """Test the /ws/status WebSocket endpoint.

        This tests the FastAPI WebSocket endpoint, not direct FluidNC WebSocket.
        """
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)

        # Connect to WebSocket
        with client.websocket_connect("/ws/status") as websocket:
            # Should receive initial status
            data = websocket.receive_json(timeout=5)

            # Verify status structure
            assert "is_running" in data or "current_file" in data, \
                f"Unexpected status format: {data}"

            print(f"Received WebSocket status: {data}")


@pytest.mark.hardware
class TestStatePersistence:
    """Tests for state persistence across connections."""

    def test_position_saved_on_disconnect(self, hardware_port, run_hardware, tmp_path):
        """Test that position is saved to state.json on disconnect.

        This verifies the state persistence mechanism works correctly.
        """
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager
        from modules.core.state import state

        # Connect
        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            # Record current position
            initial_theta = state.current_theta
            initial_rho = state.current_rho

            # The state file path
            state_file = './state.json'

            # Disconnect (this should trigger state save)
            conn.close()
            state.conn = None

            # Give it a moment to save
            time.sleep(0.5)

            # Verify state was saved
            assert os.path.exists(state_file), "state.json should exist"

            with open(state_file, 'r') as f:
                saved_state = json.load(f)

            # Check that position-related fields exist
            # The exact field names depend on your state implementation
            assert 'current_theta' in saved_state or 'theta' in saved_state or 'machine_x' in saved_state, \
                f"Expected position data in state.json, got keys: {list(saved_state.keys())}"

            print(f"State saved successfully. Position before disconnect: theta={initial_theta}, rho={initial_rho}")

        finally:
            if state.conn:
                state.conn.close()
                state.conn = None
