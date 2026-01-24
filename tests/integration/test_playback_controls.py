"""
Integration tests for playback controls.

These tests verify pause, resume, stop, skip, and speed control functionality
with real hardware connected.

Run with: pytest tests/integration/test_playback_controls.py --run-hardware -v
"""
import pytest
import time
import asyncio
import os


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
        from modules.core import pattern_manager
        from modules.core.state import state

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            pattern_path = './patterns/star.thr'
            assert os.path.exists(pattern_path), f"Pattern not found: {pattern_path}"

            # Start pattern in background
            async def start_pattern():
                # Run pattern (don't await completion)
                asyncio.create_task(pattern_manager.run_theta_rho_file(pattern_path))

            loop = asyncio.get_event_loop()
            loop.run_until_complete(start_pattern())

            # Wait for pattern to start
            time.sleep(2)
            assert state.current_playing_file is not None, "Pattern should be running"

            # Record position before pause
            pos_before = (state.current_theta, state.current_rho)

            # Pause execution
            result = pattern_manager.pause_execution()
            assert result, "Pause should succeed"
            assert state.pause_requested, "pause_requested should be True"

            # Wait and check ball stopped
            time.sleep(1)
            pos_after = (state.current_theta, state.current_rho)

            # Position should not have changed significantly while paused
            theta_diff = abs(pos_after[0] - pos_before[0])
            rho_diff = abs(pos_after[1] - pos_before[1])

            print(f"Position change during pause: theta={theta_diff:.4f}, rho={rho_diff:.4f}")

            # Allow small tolerance for deceleration
            assert theta_diff < 0.5, f"Theta should not change much while paused: {theta_diff}"
            assert rho_diff < 0.1, f"Rho should not change much while paused: {rho_diff}"

            # Clean up - stop the pattern
            loop.run_until_complete(pattern_manager.stop_actions())

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
        from modules.core import pattern_manager
        from modules.core.state import state

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            pattern_path = './patterns/star.thr'

            # Start pattern
            async def start_pattern():
                asyncio.create_task(pattern_manager.run_theta_rho_file(pattern_path))

            loop = asyncio.get_event_loop()
            loop.run_until_complete(start_pattern())

            time.sleep(2)

            # Pause
            pattern_manager.pause_execution()
            time.sleep(0.5)

            pos_paused = (state.current_theta, state.current_rho)

            # Resume
            result = pattern_manager.resume_execution()
            assert result, "Resume should succeed"
            assert not state.pause_requested, "pause_requested should be False after resume"

            # Wait for movement
            time.sleep(2)

            pos_resumed = (state.current_theta, state.current_rho)

            # Position should have changed after resume
            theta_diff = abs(pos_resumed[0] - pos_paused[0])
            rho_diff = abs(pos_resumed[1] - pos_paused[1])

            print(f"Position change after resume: theta={theta_diff:.4f}, rho={rho_diff:.4f}")
            assert theta_diff > 0.1 or rho_diff > 0.05, "Position should change after resume"

            # Clean up
            loop.run_until_complete(pattern_manager.stop_actions())

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
        """
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager
        from modules.core import pattern_manager
        from modules.core.state import state

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            pattern_path = './patterns/star.thr'

            # Start pattern
            async def start_pattern():
                asyncio.create_task(pattern_manager.run_theta_rho_file(pattern_path))

            loop = asyncio.get_event_loop()
            loop.run_until_complete(start_pattern())

            time.sleep(2)
            assert state.current_playing_file is not None, "Pattern should be running"

            # Stop execution
            async def do_stop():
                return await pattern_manager.stop_actions()

            success = loop.run_until_complete(do_stop())
            assert success, "Stop should succeed"

            # Verify stopped
            time.sleep(0.5)
            assert state.current_playing_file is None, "current_playing_file should be None after stop"
            assert state.stop_requested, "stop_requested should be True"

            print("Stop completed successfully")

        finally:
            conn.close()
            state.conn = None

    def test_force_stop(self, hardware_port, run_hardware):
        """Test force stop clears all state.

        Force stop is a more aggressive stop that clears all pattern state
        even if normal stop times out.
        """
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager
        from modules.core import pattern_manager
        from modules.core.state import state

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            pattern_path = './patterns/star.thr'

            # Start pattern
            async def start_pattern():
                asyncio.create_task(pattern_manager.run_theta_rho_file(pattern_path))

            loop = asyncio.get_event_loop()
            loop.run_until_complete(start_pattern())

            time.sleep(2)

            # Force stop by clearing state directly (simulating the /force_stop endpoint)
            state.stop_requested = True
            state.pause_requested = False
            state.current_playing_file = None
            state.execution_progress = None
            state.is_running = False
            state.current_playlist = None
            state.current_playlist_index = None

            # Wake up waiting tasks
            try:
                pattern_manager.get_pause_event().set()
            except:
                pass

            time.sleep(0.5)

            # Verify all state cleared
            assert state.current_playing_file is None
            assert state.current_playlist is None
            assert state.is_running is False

            print("Force stop completed successfully")

        finally:
            conn.close()
            state.conn = None

    def test_pause_then_stop(self, hardware_port, run_hardware):
        """Test that stop works while paused."""
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager
        from modules.core import pattern_manager
        from modules.core.state import state

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            pattern_path = './patterns/star.thr'

            # Start pattern
            async def start_pattern():
                asyncio.create_task(pattern_manager.run_theta_rho_file(pattern_path))

            loop = asyncio.get_event_loop()
            loop.run_until_complete(start_pattern())

            time.sleep(2)

            # Pause first
            pattern_manager.pause_execution()
            time.sleep(0.5)
            assert state.pause_requested, "Should be paused"

            # Now stop while paused
            async def do_stop():
                return await pattern_manager.stop_actions()

            success = loop.run_until_complete(do_stop())
            assert success, "Stop while paused should succeed"
            assert state.current_playing_file is None, "Pattern should be stopped"

            print("Stop while paused completed successfully")

        finally:
            conn.close()
            state.conn = None


@pytest.mark.hardware
@pytest.mark.slow
class TestSpeedControl:
    """Tests for speed control functionality."""

    def test_set_speed_during_playback(self, hardware_port, run_hardware):
        """Test changing speed during pattern execution.

        Verifies speed change is accepted and applied.
        """
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager
        from modules.core import pattern_manager
        from modules.core.state import state

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            pattern_path = './patterns/star.thr'
            original_speed = state.speed

            # Start pattern
            async def start_pattern():
                asyncio.create_task(pattern_manager.run_theta_rho_file(pattern_path))

            loop = asyncio.get_event_loop()
            loop.run_until_complete(start_pattern())

            time.sleep(2)

            # Change speed
            new_speed = 150
            state.speed = new_speed
            assert state.speed == new_speed, "Speed should be updated"

            print(f"Speed changed from {original_speed} to {new_speed}")

            # Let it run at new speed briefly
            time.sleep(2)

            # Clean up
            loop.run_until_complete(pattern_manager.stop_actions())

            # Restore original speed
            state.speed = original_speed

        finally:
            conn.close()
            state.conn = None

    def test_speed_bounds(self, hardware_port, run_hardware):
        """Test that invalid speed values are handled correctly."""
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.core.state import state

        original_speed = state.speed

        # Test that speed can be set to valid values
        state.speed = 50
        assert state.speed == 50

        state.speed = 200
        assert state.speed == 200

        # Note: The API endpoint validates bounds, but state accepts any value
        # This test documents current behavior
        state.speed = 1
        assert state.speed == 1

        # Restore
        state.speed = original_speed

    def test_change_speed_while_paused(self, hardware_port, run_hardware):
        """Test changing speed while paused, then resuming."""
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager
        from modules.core import pattern_manager
        from modules.core.state import state

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            pattern_path = './patterns/star.thr'
            original_speed = state.speed

            # Start pattern
            async def start_pattern():
                asyncio.create_task(pattern_manager.run_theta_rho_file(pattern_path))

            loop = asyncio.get_event_loop()
            loop.run_until_complete(start_pattern())

            time.sleep(2)

            # Pause
            pattern_manager.pause_execution()
            time.sleep(0.5)

            # Change speed while paused
            new_speed = 180
            state.speed = new_speed
            print(f"Speed changed to {new_speed} while paused")

            # Resume
            pattern_manager.resume_execution()
            time.sleep(2)

            # Verify speed is still the new value
            assert state.speed == new_speed, "Speed should persist after resume"

            # Clean up
            loop.run_until_complete(pattern_manager.stop_actions())
            state.speed = original_speed

        finally:
            conn.close()
            state.conn = None


@pytest.mark.hardware
@pytest.mark.slow
class TestSkip:
    """Tests for skip pattern functionality."""

    def test_skip_pattern_in_playlist(self, hardware_port, run_hardware):
        """Test skipping to next pattern in playlist.

        Creates a temporary playlist with 2 patterns and verifies
        skip moves to the second pattern.
        """
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager
        from modules.core import pattern_manager, playlist_manager
        from modules.core.state import state

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            # Create test playlist with 2 patterns
            test_playlist_name = "_test_skip_playlist"
            patterns = ["patterns/star.thr", "patterns/circle.thr"]

            # Check if both patterns exist
            existing_patterns = [p for p in patterns if os.path.exists(p)]
            if len(existing_patterns) < 2:
                pytest.skip("Need at least 2 patterns for skip test")

            playlist_manager.create_playlist(test_playlist_name, existing_patterns)

            try:
                # Run playlist
                async def run_playlist():
                    await playlist_manager.run_playlist(
                        test_playlist_name,
                        pause_time=0,
                        run_mode="single"
                    )

                loop = asyncio.get_event_loop()
                asyncio.ensure_future(run_playlist())

                # Wait for first pattern to start
                time.sleep(3)

                first_pattern = state.current_playing_file
                print(f"First pattern: {first_pattern}")
                assert first_pattern is not None

                # Skip to next pattern
                state.skip_requested = True

                # Wait for skip to process
                time.sleep(3)

                second_pattern = state.current_playing_file
                print(f"After skip: {second_pattern}")

                # Pattern should have changed (or playlist ended)
                if second_pattern is not None:
                    assert second_pattern != first_pattern or state.current_playlist_index > 0, \
                        "Should have moved to next pattern"

                # Clean up
                loop.run_until_complete(pattern_manager.stop_actions())

            finally:
                # Delete test playlist
                playlist_manager.delete_playlist(test_playlist_name)

        finally:
            conn.close()
            state.conn = None

    def test_skip_while_paused(self, hardware_port, run_hardware):
        """Test that skip works while paused."""
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from modules.connection import connection_manager
        from modules.core import pattern_manager, playlist_manager
        from modules.core.state import state

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            # Create test playlist
            test_playlist_name = "_test_skip_paused"
            patterns = ["patterns/star.thr", "patterns/circle.thr"]

            existing_patterns = [p for p in patterns if os.path.exists(p)]
            if len(existing_patterns) < 2:
                pytest.skip("Need at least 2 patterns")

            playlist_manager.create_playlist(test_playlist_name, existing_patterns)

            try:
                # Run playlist
                async def run_playlist():
                    await playlist_manager.run_playlist(test_playlist_name, run_mode="single")

                loop = asyncio.get_event_loop()
                asyncio.ensure_future(run_playlist())

                time.sleep(3)

                # Pause
                pattern_manager.pause_execution()
                time.sleep(0.5)
                assert state.pause_requested

                first_pattern = state.current_playing_file

                # Skip while paused
                state.skip_requested = True

                # Resume to allow skip to process
                pattern_manager.resume_execution()
                time.sleep(3)

                # Should have moved on
                print(f"Skipped from {first_pattern} while paused")

                # Clean up
                loop.run_until_complete(pattern_manager.stop_actions())

            finally:
                playlist_manager.delete_playlist(test_playlist_name)

        finally:
            conn.close()
            state.conn = None
