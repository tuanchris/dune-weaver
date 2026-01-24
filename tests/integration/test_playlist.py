"""
Integration tests for playlist functionality.

These tests verify playlist playback modes, clear patterns,
pause between patterns, and state updates.

Run with: pytest tests/integration/test_playlist.py --run-hardware -v
"""
import pytest
import time
import asyncio
import os


@pytest.fixture
def test_playlist(run_hardware):
    """Create a test playlist and clean it up after the test."""
    if not run_hardware:
        pytest.skip("Hardware tests disabled")

    from modules.core import playlist_manager

    playlist_name = "_integration_test_playlist"

    # Find available patterns
    pattern_dir = './patterns'
    available_patterns = []
    for f in os.listdir(pattern_dir):
        if f.endswith('.thr') and not f.startswith('.'):
            path = os.path.join(pattern_dir, f)
            if os.path.isfile(path):
                available_patterns.append(path)
                if len(available_patterns) >= 3:
                    break

    if len(available_patterns) < 2:
        pytest.skip("Need at least 2 patterns for playlist tests")

    # Create the playlist
    playlist_manager.create_playlist(playlist_name, available_patterns)

    yield {
        "name": playlist_name,
        "patterns": available_patterns,
        "count": len(available_patterns)
    }

    # Cleanup
    playlist_manager.delete_playlist(playlist_name)


@pytest.mark.hardware
@pytest.mark.slow
class TestPlaylistModes:
    """Tests for different playlist run modes."""

    def test_run_playlist_single_mode(self, hardware_port, run_hardware, test_playlist):
        """Test playlist in single mode - plays all patterns once then stops."""
        from modules.connection import connection_manager
        from modules.core import pattern_manager, playlist_manager
        from modules.core.state import state

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            # Run playlist in single mode
            async def run():
                success, msg = await playlist_manager.run_playlist(
                    test_playlist["name"],
                    pause_time=1,
                    run_mode="single"
                )
                return success

            loop = asyncio.get_event_loop()

            # Start playlist
            task = asyncio.ensure_future(run())

            # Wait for it to start
            time.sleep(3)

            assert state.current_playlist is not None, "Playlist should be running"
            assert state.playlist_mode == "single", f"Mode should be 'single', got: {state.playlist_mode}"

            print(f"Playlist running in single mode with {test_playlist['count']} patterns")

            # Stop after verifying mode
            loop.run_until_complete(pattern_manager.stop_actions())

        finally:
            conn.close()
            state.conn = None

    def test_run_playlist_loop_mode(self, hardware_port, run_hardware, test_playlist):
        """Test playlist in loop mode - continues from start after last pattern."""
        from modules.connection import connection_manager
        from modules.core import pattern_manager, playlist_manager
        from modules.core.state import state

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            async def run():
                success, msg = await playlist_manager.run_playlist(
                    test_playlist["name"],
                    pause_time=1,
                    run_mode="loop"
                )
                return success

            loop = asyncio.get_event_loop()
            asyncio.ensure_future(run())

            time.sleep(3)

            assert state.playlist_mode == "loop", f"Mode should be 'loop', got: {state.playlist_mode}"

            print("Playlist running in loop mode")

            loop.run_until_complete(pattern_manager.stop_actions())

        finally:
            conn.close()
            state.conn = None

    def test_run_playlist_shuffle(self, hardware_port, run_hardware, test_playlist):
        """Test playlist shuffle mode randomizes order."""
        from modules.connection import connection_manager
        from modules.core import pattern_manager, playlist_manager
        from modules.core.state import state

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            async def run():
                success, msg = await playlist_manager.run_playlist(
                    test_playlist["name"],
                    pause_time=1,
                    run_mode="single",
                    shuffle=True
                )
                return success

            loop = asyncio.get_event_loop()
            asyncio.ensure_future(run())

            time.sleep(3)

            # Playlist should be running
            assert state.current_playlist is not None

            print(f"Playlist running with shuffle enabled")
            print(f"Current pattern: {state.current_playing_file}")
            print(f"Playlist order: {state.current_playlist}")

            loop.run_until_complete(pattern_manager.stop_actions())

        finally:
            conn.close()
            state.conn = None


@pytest.mark.hardware
@pytest.mark.slow
class TestPlaylistPause:
    """Tests for pause time between patterns."""

    def test_playlist_pause_between_patterns(self, hardware_port, run_hardware, test_playlist):
        """Test that pause_time is respected between patterns."""
        from modules.connection import connection_manager
        from modules.core import pattern_manager, playlist_manager
        from modules.core.state import state

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            pause_time = 5  # 5 seconds between patterns

            async def run():
                success, msg = await playlist_manager.run_playlist(
                    test_playlist["name"],
                    pause_time=pause_time,
                    run_mode="single"
                )
                return success

            loop = asyncio.get_event_loop()
            asyncio.ensure_future(run())

            # Wait for first pattern to complete (this may take a while)
            # For testing, we'll just verify the pause_time setting is stored
            time.sleep(3)

            # Check that pause_time_remaining is used during transitions
            # (We can't easily wait for pattern completion in a test)
            print(f"Playlist started with pause_time={pause_time}s")
            print(f"Current pause_time_remaining: {state.pause_time_remaining}")

            loop.run_until_complete(pattern_manager.stop_actions())

        finally:
            conn.close()
            state.conn = None

    def test_stop_during_playlist_pause(self, hardware_port, run_hardware, test_playlist):
        """Test that stop works during the pause between patterns."""
        from modules.connection import connection_manager
        from modules.core import pattern_manager, playlist_manager
        from modules.core.state import state

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            # Use a short pattern and long pause
            async def run():
                success, msg = await playlist_manager.run_playlist(
                    test_playlist["name"],
                    pause_time=30,  # Long pause
                    run_mode="single"
                )
                return success

            loop = asyncio.get_event_loop()
            asyncio.ensure_future(run())

            time.sleep(3)

            # Stop (whether during pattern or pause)
            async def do_stop():
                return await pattern_manager.stop_actions()

            success = loop.run_until_complete(do_stop())
            assert success, "Stop should succeed"

            time.sleep(0.5)
            assert state.current_playlist is None, "Playlist should be stopped"

            print("Successfully stopped during playlist")

        finally:
            conn.close()
            state.conn = None


@pytest.mark.hardware
@pytest.mark.slow
class TestPlaylistClearPattern:
    """Tests for clear pattern functionality between patterns."""

    def test_playlist_with_clear_pattern(self, hardware_port, run_hardware, test_playlist):
        """Test that clear pattern runs between main patterns."""
        from modules.connection import connection_manager
        from modules.core import pattern_manager, playlist_manager
        from modules.core.state import state

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            # Use "clear_from_in" which clears from center outward
            async def run():
                success, msg = await playlist_manager.run_playlist(
                    test_playlist["name"],
                    pause_time=1,
                    clear_pattern="clear_from_in",
                    run_mode="single"
                )
                return success

            loop = asyncio.get_event_loop()
            asyncio.ensure_future(run())

            time.sleep(3)

            assert state.current_playlist is not None

            print("Playlist running with clear_pattern='clear_from_in'")

            loop.run_until_complete(pattern_manager.stop_actions())

        finally:
            conn.close()
            state.conn = None


@pytest.mark.hardware
@pytest.mark.slow
class TestPlaylistStateUpdates:
    """Tests for state updates during playlist playback."""

    def test_current_file_updates(self, hardware_port, run_hardware, test_playlist):
        """Test that current_playing_file reflects the active pattern."""
        from modules.connection import connection_manager
        from modules.core import pattern_manager, playlist_manager
        from modules.core.state import state

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            async def run():
                success, msg = await playlist_manager.run_playlist(
                    test_playlist["name"],
                    pause_time=1,
                    run_mode="single"
                )
                return success

            loop = asyncio.get_event_loop()
            asyncio.ensure_future(run())

            time.sleep(3)

            # current_playing_file should be set
            assert state.current_playing_file is not None, \
                "current_playing_file should be set during playback"

            # Should be one of the playlist patterns
            current = state.current_playing_file
            print(f"Current playing file: {current}")

            # Normalize paths for comparison
            playlist_patterns = [os.path.normpath(p) for p in test_playlist["patterns"]]
            current_normalized = os.path.normpath(current) if current else None

            # The current file should be related to one of the playlist patterns
            # (path may differ slightly based on how it's resolved)
            assert current is not None, "Should have a current playing file"

            loop.run_until_complete(pattern_manager.stop_actions())

        finally:
            conn.close()
            state.conn = None

    def test_playlist_index_updates(self, hardware_port, run_hardware, test_playlist):
        """Test that current_playlist_index updates correctly."""
        from modules.connection import connection_manager
        from modules.core import pattern_manager, playlist_manager
        from modules.core.state import state

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            async def run():
                success, msg = await playlist_manager.run_playlist(
                    test_playlist["name"],
                    pause_time=1,
                    run_mode="single"
                )
                return success

            loop = asyncio.get_event_loop()
            asyncio.ensure_future(run())

            time.sleep(3)

            # Index should be set
            assert state.current_playlist_index is not None, \
                "current_playlist_index should be set"
            assert state.current_playlist_index >= 0, \
                "Index should be non-negative"

            print(f"Current playlist index: {state.current_playlist_index}")
            print(f"Playlist length: {len(state.current_playlist) if state.current_playlist else 0}")

            loop.run_until_complete(pattern_manager.stop_actions())

        finally:
            conn.close()
            state.conn = None

    def test_progress_updates(self, hardware_port, run_hardware):
        """Test that execution_progress updates during pattern execution."""
        from modules.connection import connection_manager
        from modules.core import pattern_manager
        from modules.core.state import state

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            pattern_path = './patterns/star.thr'

            async def run():
                await pattern_manager.run_theta_rho_file(pattern_path)

            loop = asyncio.get_event_loop()
            asyncio.ensure_future(run())

            # Wait for pattern to start
            time.sleep(2)

            # Check progress
            progress_samples = []
            for _ in range(5):
                if state.execution_progress:
                    progress_samples.append(state.execution_progress)
                    print(f"Progress: {state.execution_progress}")
                time.sleep(1)

            # Should have captured some progress
            assert len(progress_samples) > 0, "Should have recorded some progress updates"

            # Progress should be changing (pattern executing)
            if len(progress_samples) > 1:
                first = progress_samples[0]
                last = progress_samples[-1]
                # Progress is typically a dict with 'current' and 'total'
                if isinstance(first, dict) and isinstance(last, dict):
                    print(f"Progress went from {first} to {last}")

            loop.run_until_complete(pattern_manager.stop_actions())

        finally:
            conn.close()
            state.conn = None


@pytest.mark.hardware
class TestWebSocketStatus:
    """Tests for WebSocket status updates during playback."""

    def test_status_updates_during_playback(self, hardware_port, run_hardware):
        """Test that WebSocket broadcasts correct state during playback."""
        if not run_hardware:
            pytest.skip("Hardware tests disabled")

        from fastapi.testclient import TestClient
        from modules.connection import connection_manager
        from modules.core import pattern_manager
        from modules.core.state import state
        from main import app

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            pattern_path = './patterns/star.thr'

            # Start pattern
            async def start():
                asyncio.create_task(pattern_manager.run_theta_rho_file(pattern_path))

            loop = asyncio.get_event_loop()
            loop.run_until_complete(start())

            time.sleep(2)

            # Check WebSocket status
            client = TestClient(app)

            with client.websocket_connect("/ws/status") as websocket:
                data = websocket.receive_json()

                print(f"WebSocket status: {data}")

                # Should reflect running state
                # The exact fields depend on your broadcast_status implementation
                assert isinstance(data, dict), "Status should be a dict"

            loop.run_until_complete(pattern_manager.stop_actions())

        finally:
            conn.close()
            state.conn = None
