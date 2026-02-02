"""
Integration tests for playback controls.

These tests verify pause, resume, stop, skip, and speed control functionality
with real hardware connected.

Run with: pytest tests/integration/test_playback_controls.py --run-hardware -v
"""
import pytest
import time
import threading
import os


def start_pattern_async(client, file_name="star.thr"):
    """Helper to start a pattern in a background thread.

    Returns the thread so caller can join() it after stopping.
    """
    def run():
        client.post("/run_theta_rho", json={"file_name": file_name})

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def stop_pattern(client):
    """Helper to stop pattern execution.

    Uses force_stop which doesn't wait for locks (avoids event loop issues in tests).
    """
    response = client.post("/force_stop")
    return response


@pytest.mark.hardware
@pytest.mark.slow
class TestPauseResume:
    """Tests for pause and resume functionality."""

    def test_pause_during_pattern(self, hardware_port, run_hardware):
        """Test pausing execution mid-pattern.

        Verifies:
        1. Pattern starts executing
        2. Pause request is acknowledged
        3. Ball actually stops moving
        """
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager
        from modules.core.state import state
        from fastapi.testclient import TestClient
        from main import app

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            client = TestClient(app)

            # Start pattern in background
            pattern_thread = start_pattern_async(client, "star.thr")

            # Wait for pattern to start
            time.sleep(3)
            assert state.current_playing_file is not None, "Pattern should be running"
            print(f"Pattern running: {state.current_playing_file}")

            # Record position before pause
            pos_before = (state.current_theta, state.current_rho)

            # Pause execution
            response = client.post("/pause_execution")
            assert response.status_code == 200, f"Pause failed: {response.text}"
            assert state.pause_requested, "pause_requested should be True"

            # Wait and check ball stopped
            time.sleep(1)
            pos_after = (state.current_theta, state.current_rho)

            theta_diff = abs(pos_after[0] - pos_before[0])
            rho_diff = abs(pos_after[1] - pos_before[1])

            print(f"Position change during pause: theta={theta_diff:.4f}, rho={rho_diff:.4f}")

            # Allow small tolerance for deceleration
            assert theta_diff < 0.5, f"Theta changed too much while paused: {theta_diff}"
            assert rho_diff < 0.1, f"Rho changed too much while paused: {rho_diff}"

            # Clean up
            stop_pattern(client)
            pattern_thread.join(timeout=5)

        finally:
            conn.close()
            state.conn = None

    def test_resume_after_pause(self, hardware_port, run_hardware):
        """Test resuming execution after pause.

        Verifies:
        1. Pattern can be paused
        2. Resume causes movement to continue
        3. Position changes after resume
        """
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager
        from modules.core.state import state
        from fastapi.testclient import TestClient
        from main import app

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            client = TestClient(app)

            # Start pattern
            pattern_thread = start_pattern_async(client, "star.thr")

            # Wait for pattern to actually start executing (not just queued)
            # Check that position has changed from initial, indicating movement
            initial_pos = (state.current_theta, state.current_rho)
            max_wait = 10  # seconds
            started = False
            for _ in range(max_wait * 2):  # Check every 0.5s
                time.sleep(0.5)
                if state.current_playing_file is not None:
                    current_pos = (state.current_theta, state.current_rho)
                    # Check if position changed (pattern actually moving)
                    if (abs(current_pos[0] - initial_pos[0]) > 0.01 or
                            abs(current_pos[1] - initial_pos[1]) > 0.01):
                        started = True
                        print(f"Pattern started moving: theta={current_pos[0]:.3f}, rho={current_pos[1]:.3f}")
                        break

            assert started, "Pattern should start moving within timeout"

            # Pause
            client.post("/pause_execution")
            time.sleep(1)  # Wait for pause to take effect

            pos_paused = (state.current_theta, state.current_rho)
            print(f"Position when paused: theta={pos_paused[0]:.4f}, rho={pos_paused[1]:.4f}")

            # Resume
            response = client.post("/resume_execution")
            assert response.status_code == 200, f"Resume failed: {response.text}"
            assert not state.pause_requested, "pause_requested should be False after resume"

            # Wait for movement after resume
            time.sleep(3)

            pos_resumed = (state.current_theta, state.current_rho)

            theta_diff = abs(pos_resumed[0] - pos_paused[0])
            rho_diff = abs(pos_resumed[1] - pos_paused[1])

            print(f"Position after resume: theta={pos_resumed[0]:.4f}, rho={pos_resumed[1]:.4f}")
            print(f"Position change after resume: theta={theta_diff:.4f}, rho={rho_diff:.4f}")
            assert theta_diff > 0.1 or rho_diff > 0.05, "Position should change after resume"

            # Clean up
            stop_pattern(client)
            pattern_thread.join(timeout=5)

        finally:
            conn.close()
            state.conn = None


@pytest.mark.hardware
@pytest.mark.slow
class TestStop:
    """Tests for stop functionality."""

    def test_stop_during_pattern(self, hardware_port, run_hardware):
        """Test stopping execution mid-pattern.

        Verifies:
        1. Stop clears current_playing_file
        2. Pattern execution actually stops

        Note: Uses force_stop in test environment because regular stop_execution
        has asyncio lock issues with TestClient's event loop handling.
        """
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager
        from modules.core.state import state
        from fastapi.testclient import TestClient
        from main import app

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            client = TestClient(app)

            # Start pattern
            pattern_thread = start_pattern_async(client, "star.thr")
            time.sleep(3)
            assert state.current_playing_file is not None, "Pattern should be running"

            # Stop execution (use force_stop for test reliability)
            response = stop_pattern(client)
            assert response.status_code == 200, f"Stop failed: {response.text}"

            # Verify stopped
            time.sleep(0.5)
            assert state.current_playing_file is None, "current_playing_file should be None"

            print("Stop completed successfully")
            pattern_thread.join(timeout=5)

        finally:
            conn.close()
            state.conn = None

    def test_force_stop(self, hardware_port, run_hardware):
        """Test force stop clears all state."""
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager
        from modules.core.state import state
        from fastapi.testclient import TestClient
        from main import app

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            client = TestClient(app)

            # Start pattern
            pattern_thread = start_pattern_async(client, "star.thr")
            time.sleep(3)

            # Force stop via API
            response = client.post("/force_stop")
            assert response.status_code == 200, f"Force stop failed: {response.text}"

            time.sleep(0.5)

            # Verify all state cleared
            assert state.current_playing_file is None
            assert state.current_playlist is None

            print("Force stop completed successfully")
            pattern_thread.join(timeout=5)

        finally:
            conn.close()
            state.conn = None

    def test_pause_then_stop(self, hardware_port, run_hardware):
        """Test that stop works while paused."""
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager
        from modules.core.state import state
        from fastapi.testclient import TestClient
        from main import app

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            client = TestClient(app)

            # Start pattern
            pattern_thread = start_pattern_async(client, "star.thr")
            time.sleep(3)

            # Pause first
            client.post("/pause_execution")
            time.sleep(0.5)
            assert state.pause_requested, "Should be paused"

            # Now stop while paused
            response = stop_pattern(client)
            assert response.status_code == 200, f"Stop while paused failed: {response.text}"
            assert state.current_playing_file is None, "Pattern should be stopped"

            print("Stop while paused completed successfully")
            pattern_thread.join(timeout=5)

        finally:
            conn.close()
            state.conn = None


@pytest.mark.hardware
@pytest.mark.slow
class TestSpeedControl:
    """Tests for speed control functionality."""

    def test_set_speed_during_playback(self, hardware_port, run_hardware):
        """Test changing speed during pattern execution."""
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager
        from modules.core.state import state
        from fastapi.testclient import TestClient
        from main import app

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            client = TestClient(app)
            original_speed = state.speed

            # Start pattern
            pattern_thread = start_pattern_async(client, "star.thr")
            time.sleep(3)

            # Change speed via API
            new_speed = 150
            response = client.post("/set_speed", json={"speed": new_speed})
            assert response.status_code == 200, f"Set speed failed: {response.text}"
            assert state.speed == new_speed, "Speed should be updated"

            print(f"Speed changed from {original_speed} to {new_speed}")

            # Let it run at new speed briefly
            time.sleep(2)

            # Clean up
            stop_pattern(client)
            pattern_thread.join(timeout=5)

        finally:
            conn.close()
            state.conn = None

    def test_speed_bounds(self, hardware_port, run_hardware):
        """Test that invalid speed values are rejected."""
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager
        from modules.core.state import state
        from fastapi.testclient import TestClient
        from main import app

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            client = TestClient(app)
            original_speed = state.speed

            # Valid speeds should work
            response = client.post("/set_speed", json={"speed": 50})
            assert response.status_code == 200

            response = client.post("/set_speed", json={"speed": 200})
            assert response.status_code == 200

            # Invalid speed (0 or negative) should fail
            response = client.post("/set_speed", json={"speed": 0})
            assert response.status_code == 400, "Speed 0 should be rejected"

            response = client.post("/set_speed", json={"speed": -10})
            assert response.status_code == 400, "Negative speed should be rejected"

            # Restore
            client.post("/set_speed", json={"speed": original_speed})

        finally:
            conn.close()
            state.conn = None

    def test_change_speed_while_paused(self, hardware_port, run_hardware):
        """Test changing speed while paused, then resuming."""
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager
        from modules.core.state import state
        from fastapi.testclient import TestClient
        from main import app

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            client = TestClient(app)
            original_speed = state.speed

            # Start pattern
            pattern_thread = start_pattern_async(client, "star.thr")
            time.sleep(3)

            # Pause
            client.post("/pause_execution")
            time.sleep(0.5)

            # Change speed while paused
            new_speed = 180
            response = client.post("/set_speed", json={"speed": new_speed})
            assert response.status_code == 200
            print(f"Speed changed to {new_speed} while paused")

            # Resume
            client.post("/resume_execution")
            time.sleep(2)

            # Verify speed persisted
            assert state.speed == new_speed, "Speed should persist after resume"

            # Clean up
            stop_pattern(client)
            pattern_thread.join(timeout=5)

            # Restore original speed
            state.speed = original_speed

        finally:
            conn.close()
            state.conn = None


@pytest.mark.hardware
@pytest.mark.slow
class TestSkip:
    """Tests for skip pattern functionality."""

    def test_skip_pattern_in_playlist(self, hardware_port, run_hardware):
        """Test skipping to next pattern in playlist."""
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager
        from modules.core import playlist_manager
        from modules.core.state import state
        from fastapi.testclient import TestClient
        from main import app

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            client = TestClient(app)

            # Create test playlist with 2 patterns
            test_playlist_name = "_test_skip_playlist"
            patterns = ["star.thr", "circle_normalized.thr"]

            existing_patterns = [p for p in patterns if os.path.exists(f"./patterns/{p}")]
            if len(existing_patterns) < 2:
                pytest.skip("Need at least 2 patterns for skip test")

            playlist_manager.create_playlist(test_playlist_name, existing_patterns)

            try:
                # Run playlist in background
                def run_playlist():
                    client.post("/run_playlist", json={
                        "playlist_name": test_playlist_name,
                        "pause_time": 0,
                        "run_mode": "single"
                    })

                playlist_thread = threading.Thread(target=run_playlist)
                playlist_thread.start()

                # Wait for first pattern to start
                time.sleep(3)

                first_pattern = state.current_playing_file
                print(f"First pattern: {first_pattern}")
                assert first_pattern is not None

                # Skip to next pattern
                response = client.post("/skip_pattern")
                assert response.status_code == 200, f"Skip failed: {response.text}"

                # Wait for skip to process
                time.sleep(3)

                second_pattern = state.current_playing_file
                print(f"After skip: {second_pattern}")

                # Pattern should have changed (or playlist ended)
                if second_pattern is not None:
                    assert second_pattern != first_pattern or state.current_playlist_index > 0

                # Clean up
                stop_pattern(client)
                playlist_thread.join(timeout=5)

            finally:
                playlist_manager.delete_playlist(test_playlist_name)

        finally:
            conn.close()
            state.conn = None

    def test_skip_while_paused(self, hardware_port, run_hardware):
        """Test that skip works while paused."""
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager
        from modules.core import playlist_manager
        from modules.core.state import state
        from fastapi.testclient import TestClient
        from main import app

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            client = TestClient(app)

            # Create test playlist
            test_playlist_name = "_test_skip_paused"
            patterns = ["star.thr", "circle_normalized.thr"]

            existing_patterns = [p for p in patterns if os.path.exists(f"./patterns/{p}")]
            if len(existing_patterns) < 2:
                pytest.skip("Need at least 2 patterns")

            playlist_manager.create_playlist(test_playlist_name, existing_patterns)

            try:
                # Run playlist
                def run_playlist():
                    client.post("/run_playlist", json={
                        "playlist_name": test_playlist_name,
                        "run_mode": "single"
                    })

                playlist_thread = threading.Thread(target=run_playlist)
                playlist_thread.start()

                time.sleep(3)

                # Pause
                client.post("/pause_execution")
                time.sleep(0.5)
                assert state.pause_requested

                first_pattern = state.current_playing_file

                # Skip while paused
                response = client.post("/skip_pattern")
                assert response.status_code == 200

                # Resume to allow skip to process
                client.post("/resume_execution")
                time.sleep(3)

                print(f"Skipped from {first_pattern} while paused")

                # Clean up
                stop_pattern(client)
                playlist_thread.join(timeout=5)

            finally:
                playlist_manager.delete_playlist(test_playlist_name)

        finally:
            conn.close()
            state.conn = None
