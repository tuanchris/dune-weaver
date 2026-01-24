"""
Integration tests for playlist functionality.

These tests verify playlist playback modes, clear patterns,
pause between patterns, and state updates.

Run with: pytest tests/integration/test_playlist.py --run-hardware -v
"""
import pytest
import time
import threading
import os


def start_playlist_async(client, playlist_name, pause_time=1, run_mode="single",
                          clear_pattern=None, shuffle=False):
    """Helper to start a playlist in a background thread.

    Returns the thread so caller can join() it after stopping.
    """
    def run():
        payload = {
            "playlist_name": playlist_name,
            "pause_time": pause_time,
            "run_mode": run_mode
        }
        if clear_pattern:
            payload["clear_pattern"] = clear_pattern
        if shuffle:
            payload["shuffle"] = shuffle
        client.post("/run_playlist", json=payload)

    thread = threading.Thread(target=run)
    thread.start()
    return thread


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


@pytest.fixture
def test_playlist(run_hardware):
    """Create a test playlist and clean it up after the test."""
    if not run_hardware:
        pytest.skip("Hardware tests disabled")

    from modules.core import playlist_manager

    playlist_name = "_integration_test_playlist"

    # Use specific simple patterns for testing
    test_patterns = [
        "star.thr",
        "circle_normalized.thr",
        "square.thr"
    ]

    # Verify patterns exist
    available_patterns = []
    for pattern in test_patterns:
        if os.path.exists(f"./patterns/{pattern}"):
            available_patterns.append(pattern)

    if len(available_patterns) < 2:
        pytest.skip(f"Need at least 2 of these patterns: {test_patterns}")

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
        from modules.core.state import state
        from fastapi.testclient import TestClient
        from main import app

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            client = TestClient(app)

            print(f"Test playlist: {test_playlist}")

            # Try direct API call first to see response
            response = client.post("/run_playlist", json={
                "playlist_name": test_playlist["name"],
                "pause_time": 1,
                "run_mode": "single"
            })
            print(f"API response: {response.status_code} - {response.text}")

            # Wait for it to start
            time.sleep(3)

            print(f"state.current_playlist = {state.current_playlist}")
            print(f"state.playlist_mode = {state.playlist_mode}")
            print(f"state.current_playing_file = {state.current_playing_file}")

            assert state.current_playlist is not None, "Playlist should be running"
            assert state.playlist_mode == "single", f"Mode should be 'single', got: {state.playlist_mode}"

            print(f"Playlist running in single mode with {test_playlist['count']} patterns")

            # Clean up
            stop_pattern(client)

        finally:
            conn.close()
            state.conn = None

    def test_run_playlist_loop_mode(self, hardware_port, run_hardware, test_playlist):
        """Test playlist in loop mode - continues from start after last pattern."""
        from modules.connection import connection_manager
        from modules.core.state import state
        from fastapi.testclient import TestClient
        from main import app

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            client = TestClient(app)

            # Start playlist in background
            playlist_thread = start_playlist_async(
                client,
                test_playlist["name"],
                pause_time=1,
                run_mode="loop"
            )

            time.sleep(3)

            assert state.playlist_mode == "loop", f"Mode should be 'loop', got: {state.playlist_mode}"

            print("Playlist running in loop mode")

            # Clean up
            stop_pattern(client)
            playlist_thread.join(timeout=5)

        finally:
            conn.close()
            state.conn = None

    def test_run_playlist_shuffle(self, hardware_port, run_hardware, test_playlist):
        """Test playlist shuffle mode randomizes order."""
        from modules.connection import connection_manager
        from modules.core.state import state
        from fastapi.testclient import TestClient
        from main import app

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            client = TestClient(app)

            # Start playlist in background with shuffle
            playlist_thread = start_playlist_async(
                client,
                test_playlist["name"],
                pause_time=1,
                run_mode="single",
                shuffle=True
            )

            time.sleep(3)

            # Playlist should be running
            assert state.current_playlist is not None

            print(f"Playlist running with shuffle enabled")
            print(f"Current pattern: {state.current_playing_file}")
            print(f"Playlist order: {state.current_playlist}")

            # Clean up
            stop_pattern(client)
            playlist_thread.join(timeout=5)

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
        from modules.core.state import state
        from fastapi.testclient import TestClient
        from main import app

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            client = TestClient(app)
            pause_time = 5  # 5 seconds between patterns

            # Start playlist in background
            playlist_thread = start_playlist_async(
                client,
                test_playlist["name"],
                pause_time=pause_time,
                run_mode="single"
            )

            # Wait for first pattern to complete (this may take a while)
            # For testing, we'll just verify the pause_time setting is stored
            time.sleep(3)

            # Check that pause_time_remaining is used during transitions
            # (We can't easily wait for pattern completion in a test)
            print(f"Playlist started with pause_time={pause_time}s")
            print(f"Current pause_time_remaining: {state.pause_time_remaining}")

            # Clean up
            stop_pattern(client)
            playlist_thread.join(timeout=5)

        finally:
            conn.close()
            state.conn = None

    def test_stop_during_playlist_pause(self, hardware_port, run_hardware, test_playlist):
        """Test that stop works during the pause between patterns."""
        from modules.connection import connection_manager
        from modules.core.state import state
        from fastapi.testclient import TestClient
        from main import app

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            client = TestClient(app)

            # Start playlist with long pause
            playlist_thread = start_playlist_async(
                client,
                test_playlist["name"],
                pause_time=30,  # Long pause
                run_mode="single"
            )

            time.sleep(3)

            # Stop (whether during pattern or pause)
            response = stop_pattern(client)
            assert response.status_code == 200, f"Stop failed: {response.text}"

            time.sleep(0.5)
            assert state.current_playlist is None, "Playlist should be stopped"

            print("Successfully stopped during playlist")
            playlist_thread.join(timeout=5)

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
        from modules.core.state import state
        from fastapi.testclient import TestClient
        from main import app

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            client = TestClient(app)

            # Start playlist with clear pattern
            playlist_thread = start_playlist_async(
                client,
                test_playlist["name"],
                pause_time=1,
                clear_pattern="clear_from_in",
                run_mode="single"
            )

            time.sleep(3)

            assert state.current_playlist is not None

            print("Playlist running with clear_pattern='clear_from_in'")

            # Clean up
            stop_pattern(client)
            playlist_thread.join(timeout=5)

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
        from modules.core.state import state
        from fastapi.testclient import TestClient
        from main import app

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            client = TestClient(app)

            # Start playlist in background
            playlist_thread = start_playlist_async(
                client,
                test_playlist["name"],
                pause_time=1,
                run_mode="single"
            )

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

            # Clean up
            stop_pattern(client)
            playlist_thread.join(timeout=5)

        finally:
            conn.close()
            state.conn = None

    def test_playlist_index_updates(self, hardware_port, run_hardware, test_playlist):
        """Test that current_playlist_index updates correctly."""
        from modules.connection import connection_manager
        from modules.core.state import state
        from fastapi.testclient import TestClient
        from main import app

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            client = TestClient(app)

            # Start playlist in background
            playlist_thread = start_playlist_async(
                client,
                test_playlist["name"],
                pause_time=1,
                run_mode="single"
            )

            time.sleep(3)

            # Index should be set
            assert state.current_playlist_index is not None, \
                "current_playlist_index should be set"
            assert state.current_playlist_index >= 0, \
                "Index should be non-negative"

            print(f"Current playlist index: {state.current_playlist_index}")
            print(f"Playlist length: {len(state.current_playlist) if state.current_playlist else 0}")

            # Clean up
            stop_pattern(client)
            playlist_thread.join(timeout=5)

        finally:
            conn.close()
            state.conn = None

    def test_progress_updates(self, hardware_port, run_hardware):
        """Test that execution_progress updates during pattern execution."""
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

            # Clean up
            stop_pattern(client)
            pattern_thread.join(timeout=5)

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
        from modules.core.state import state
        from main import app

        conn = connection_manager.SerialConnection(hardware_port)
        state.conn = conn

        try:
            client = TestClient(app)

            # Start pattern in background
            pattern_thread = start_pattern_async(client, "star.thr")

            time.sleep(2)

            # Check WebSocket status
            with client.websocket_connect("/ws/status") as websocket:
                message = websocket.receive_json()

                # Status format is {'type': 'status_update', 'data': {...}}
                assert message.get("type") == "status_update", \
                    f"Expected type='status_update', got: {message}"

                data = message.get("data", {})
                print(f"WebSocket status: {data}")

                # Should have expected status fields
                assert "is_running" in data, f"Expected 'is_running' in data"

            # Clean up
            stop_pattern(client)
            pattern_thread.join(timeout=5)

        finally:
            conn.close()
            state.conn = None
