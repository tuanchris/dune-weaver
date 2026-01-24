"""
Unit tests for playlist API endpoints.

Tests the following endpoints:
- GET /list_all_playlists
- GET /get_playlist
- POST /create_playlist
- POST /modify_playlist
- DELETE /delete_playlist
- POST /rename_playlist
- POST /add_to_playlist
- POST /run_playlist (when disconnected)
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestListAllPlaylists:
    """Tests for /list_all_playlists endpoint."""

    @pytest.mark.asyncio
    async def test_list_all_playlists(self, async_client):
        """Test list_all_playlists returns list of playlist names."""
        mock_playlists = ["favorites", "evening", "morning"]

        with patch("main.playlist_manager.list_all_playlists", return_value=mock_playlists):
            response = await async_client.get("/list_all_playlists")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3
        assert "favorites" in data

    @pytest.mark.asyncio
    async def test_list_all_playlists_empty(self, async_client):
        """Test list_all_playlists returns empty list when no playlists."""
        with patch("main.playlist_manager.list_all_playlists", return_value=[]):
            response = await async_client.get("/list_all_playlists")

        assert response.status_code == 200
        data = response.json()
        assert data == []


class TestGetPlaylist:
    """Tests for /get_playlist endpoint."""

    @pytest.mark.asyncio
    async def test_get_playlist_exists(self, async_client):
        """Test get_playlist returns playlist data."""
        mock_playlist = {
            "name": "favorites",
            "files": ["circle.thr", "spiral.thr"]
        }

        with patch("main.playlist_manager.get_playlist", return_value=mock_playlist):
            response = await async_client.get("/get_playlist", params={"name": "favorites"})

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "favorites"
        assert data["files"] == ["circle.thr", "spiral.thr"]

    @pytest.mark.asyncio
    async def test_get_playlist_creates_empty_if_not_found(self, async_client):
        """Test get_playlist auto-creates empty playlist if not found.

        Note: This is the actual behavior - the endpoint auto-creates empty playlists.
        """
        with patch("main.playlist_manager.get_playlist", return_value=None):
            with patch("main.playlist_manager.create_playlist", return_value=True):
                response = await async_client.get("/get_playlist", params={"name": "nonexistent"})

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "nonexistent"
        assert data["files"] == []


class TestCreatePlaylist:
    """Tests for /create_playlist endpoint."""

    @pytest.mark.asyncio
    async def test_create_playlist(self, async_client):
        """Test creating a new playlist."""
        with patch("main.playlist_manager.create_playlist", return_value=True):
            response = await async_client.post(
                "/create_playlist",
                json={
                    "playlist_name": "new_playlist",  # API uses playlist_name, not name
                    "files": ["circle.thr", "spiral.thr"]
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestModifyPlaylist:
    """Tests for /modify_playlist endpoint."""

    @pytest.mark.asyncio
    async def test_modify_playlist(self, async_client):
        """Test modifying an existing playlist."""
        with patch("main.playlist_manager.modify_playlist", return_value=True):
            response = await async_client.post(
                "/modify_playlist",
                json={
                    "playlist_name": "favorites",  # API uses playlist_name
                    "files": ["new_pattern.thr"]
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestDeletePlaylist:
    """Tests for /delete_playlist endpoint."""

    @pytest.mark.asyncio
    async def test_delete_playlist(self, async_client):
        """Test deleting a playlist."""
        with patch("main.playlist_manager.delete_playlist", return_value=True):
            response = await async_client.request(
                "DELETE",
                "/delete_playlist",
                json={"playlist_name": "to_delete"}  # DELETE with body
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_delete_playlist_not_found(self, async_client):
        """Test deleting a non-existent playlist returns 404."""
        with patch("main.playlist_manager.delete_playlist", return_value=False):
            response = await async_client.request(
                "DELETE",
                "/delete_playlist",
                json={"playlist_name": "nonexistent"}
            )

        assert response.status_code == 404


class TestRenamePlaylist:
    """Tests for /rename_playlist endpoint."""

    @pytest.mark.asyncio
    async def test_rename_playlist_success(self, async_client):
        """Test renaming a playlist."""
        with patch("main.playlist_manager.rename_playlist", return_value=(True, "Renamed")):
            response = await async_client.post(
                "/rename_playlist",
                json={
                    "old_name": "old_playlist",
                    "new_name": "new_playlist"
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_rename_playlist_not_found(self, async_client):
        """Test renaming a non-existent playlist fails."""
        with patch("main.playlist_manager.rename_playlist", return_value=(False, "Playlist not found")):
            response = await async_client.post(
                "/rename_playlist",
                json={
                    "old_name": "nonexistent",
                    "new_name": "new_name"
                }
            )

        # Returns 400 with message (not 404)
        assert response.status_code == 400


class TestAddToPlaylist:
    """Tests for /add_to_playlist endpoint."""

    @pytest.mark.asyncio
    async def test_add_to_playlist(self, async_client):
        """Test adding a pattern to a playlist."""
        with patch("main.playlist_manager.add_to_playlist", return_value=True):
            response = await async_client.post(
                "/add_to_playlist",
                json={
                    "playlist_name": "favorites",  # API uses playlist_name
                    "pattern": "new_pattern.thr"   # API uses pattern, not file
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_add_to_playlist_not_found(self, async_client):
        """Test adding to a non-existent playlist fails."""
        with patch("main.playlist_manager.add_to_playlist", return_value=False):
            response = await async_client.post(
                "/add_to_playlist",
                json={
                    "playlist_name": "nonexistent",
                    "pattern": "pattern.thr"
                }
            )

        assert response.status_code == 404


class TestRunPlaylist:
    """Tests for /run_playlist endpoint."""

    @pytest.mark.asyncio
    async def test_run_playlist_when_disconnected(self, async_client, mock_state):
        """Test run_playlist fails when not connected.

        Note: The endpoint catches HTTPException and re-raises as 500.
        """
        mock_state.conn = None
        mock_state.is_homing = False

        with patch("main.state", mock_state):
            response = await async_client.post(
                "/run_playlist",
                json={
                    "playlist_name": "test",
                    "pause_time": 5,
                    "clear_pattern": None,
                    "run_mode": "single"
                }
            )

        # Endpoint wraps in try/except and returns 500
        assert response.status_code == 500
        data = response.json()
        assert "not established" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_run_playlist_during_homing(self, async_client, mock_state):
        """Test run_playlist fails during homing.

        Note: The endpoint catches HTTPException and re-raises as 500.
        """
        mock_state.is_homing = True
        mock_state.conn = MagicMock()
        mock_state.conn.is_connected.return_value = True

        with patch("main.state", mock_state):
            response = await async_client.post(
                "/run_playlist",
                json={
                    "playlist_name": "test",
                    "pause_time": 5,
                    "clear_pattern": None,
                    "run_mode": "single"
                }
            )

        # Endpoint wraps in try/except and returns 500
        assert response.status_code == 500
        data = response.json()
        assert "homing" in data["detail"].lower()


class TestSkipPattern:
    """Tests for /skip_pattern endpoint."""

    @pytest.mark.asyncio
    async def test_skip_pattern(self, async_client, mock_state):
        """Test skip_pattern during playlist execution."""
        mock_state.current_playlist = ["a.thr", "b.thr"]
        mock_state.current_playlist_index = 0
        mock_state.skip_requested = False

        with patch("main.state", mock_state):
            response = await async_client.post("/skip_pattern")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Endpoint sets skip_requested directly
        assert mock_state.skip_requested is True

    @pytest.mark.asyncio
    async def test_skip_pattern_no_playlist(self, async_client, mock_state):
        """Test skip_pattern fails when no playlist is running."""
        mock_state.current_playlist = None

        with patch("main.state", mock_state):
            response = await async_client.post("/skip_pattern")

        assert response.status_code == 400
        data = response.json()
        assert "no playlist" in data["detail"].lower()
