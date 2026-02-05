"""
Unit tests for pattern API endpoints.

Tests the following endpoints:
- GET /list_theta_rho_files
- GET /list_theta_rho_files_with_metadata
- POST /get_theta_rho_coordinates
- POST /run_theta_rho (when disconnected)
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestListThetaRhoFiles:
    """Tests for /list_theta_rho_files endpoint."""

    @pytest.mark.asyncio
    async def test_list_theta_rho_files(self, async_client):
        """Test list_theta_rho_files returns list of pattern files."""
        mock_files = ["circle.thr", "spiral.thr", "custom/pattern.thr"]

        with patch("main.pattern_manager.list_theta_rho_files", return_value=mock_files):
            response = await async_client.get("/list_theta_rho_files")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3
        assert "circle.thr" in data
        assert "spiral.thr" in data
        assert "custom/pattern.thr" in data

    @pytest.mark.asyncio
    async def test_list_theta_rho_files_empty(self, async_client):
        """Test list_theta_rho_files returns empty list when no patterns."""
        with patch("main.pattern_manager.list_theta_rho_files", return_value=[]):
            response = await async_client.get("/list_theta_rho_files")

        assert response.status_code == 200
        data = response.json()
        assert data == []


class TestListThetaRhoFilesWithMetadata:
    """Tests for /list_theta_rho_files_with_metadata endpoint."""

    @pytest.mark.asyncio
    async def test_list_theta_rho_files_with_metadata(self, async_client, tmp_path):
        """Test list_theta_rho_files_with_metadata returns files with metadata."""
        mock_files = ["circle.thr"]

        # The endpoint has two paths:
        # 1. If metadata_cache.json exists, use it
        # 2. Otherwise, use ThreadPoolExecutor with process_file
        # We'll test the fallback path by having the cache file not exist

        patterns_dir = tmp_path / "patterns"
        patterns_dir.mkdir()
        (patterns_dir / "circle.thr").write_text("0 0.5\n1 0.6")

        with patch("main.pattern_manager.list_theta_rho_files", return_value=mock_files):
            with patch("main.pattern_manager.THETA_RHO_DIR", str(patterns_dir)):
                # Simulate cache file not existing
                with patch("builtins.open", side_effect=FileNotFoundError):
                    response = await async_client.get("/list_theta_rho_files_with_metadata")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1

        # The response structure has 'path', 'name', 'category', 'date_modified', 'coordinates_count'
        item = data[0]
        assert item["path"] == "circle.thr"
        assert item["name"] == "circle"
        assert "category" in item
        assert "date_modified" in item
        assert "coordinates_count" in item


class TestGetThetaRhoCoordinates:
    """Tests for /get_theta_rho_coordinates endpoint."""

    @pytest.mark.asyncio
    async def test_get_theta_rho_coordinates_valid_file(self, async_client, tmp_path):
        """Test getting coordinates from a valid file."""
        # Create test pattern file
        patterns_dir = tmp_path / "patterns"
        patterns_dir.mkdir()
        test_file = patterns_dir / "test.thr"
        test_file.write_text("0.0 0.5\n1.57 0.8\n3.14 0.3\n")

        mock_coordinates = [(0.0, 0.5), (1.57, 0.8), (3.14, 0.3)]

        with patch("main.THETA_RHO_DIR", str(patterns_dir)):
            with patch("main.parse_theta_rho_file", return_value=mock_coordinates):
                response = await async_client.post(
                    "/get_theta_rho_coordinates",
                    json={"file_name": "test.thr"}
                )

        assert response.status_code == 200
        data = response.json()
        assert "coordinates" in data
        assert len(data["coordinates"]) == 3
        assert data["coordinates"][0] == [0.0, 0.5]
        assert data["coordinates"][1] == [1.57, 0.8]
        assert data["coordinates"][2] == [3.14, 0.3]

    @pytest.mark.asyncio
    async def test_get_theta_rho_coordinates_file_not_found(self, async_client, tmp_path):
        """Test getting coordinates from non-existent file returns error.

        Note: The endpoint returns 500 because it catches the HTTPException and re-raises it.
        """
        patterns_dir = tmp_path / "patterns"
        patterns_dir.mkdir()

        with patch("main.THETA_RHO_DIR", str(patterns_dir)):
            response = await async_client.post(
                "/get_theta_rho_coordinates",
                json={"file_name": "nonexistent.thr"}
            )

        # The endpoint wraps the 404 in a 500 due to exception handling
        assert response.status_code in [404, 500]
        data = response.json()
        assert "not found" in data["detail"].lower()


class TestRunThetaRho:
    """Tests for /run_theta_rho endpoint."""

    @pytest.mark.asyncio
    async def test_run_theta_rho_when_disconnected(self, async_client, mock_state, tmp_path):
        """Test run_theta_rho fails gracefully when disconnected."""
        # The endpoint checks file existence first, then connection
        patterns_dir = tmp_path / "patterns"
        patterns_dir.mkdir()
        test_file = patterns_dir / "circle.thr"
        test_file.write_text("0 0.5")

        mock_state.conn = None
        mock_state.is_homing = False

        with patch("main.state", mock_state):
            with patch("main.pattern_manager.THETA_RHO_DIR", str(patterns_dir)):
                response = await async_client.post(
                    "/run_theta_rho",
                    json={
                        "file_name": "circle.thr",
                        "pre_execution": "none"
                    }
                )

        assert response.status_code == 400
        data = response.json()
        assert "not established" in data["detail"].lower() or "not connected" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_run_theta_rho_during_homing(self, async_client, mock_state, tmp_path):
        """Test run_theta_rho fails when homing is in progress."""
        patterns_dir = tmp_path / "patterns"
        patterns_dir.mkdir()
        test_file = patterns_dir / "circle.thr"
        test_file.write_text("0 0.5")

        mock_state.is_homing = True
        mock_state.conn = MagicMock()
        mock_state.conn.is_connected.return_value = True

        with patch("main.state", mock_state):
            with patch("main.pattern_manager.THETA_RHO_DIR", str(patterns_dir)):
                response = await async_client.post(
                    "/run_theta_rho",
                    json={
                        "file_name": "circle.thr",
                        "pre_execution": "none"
                    }
                )

        assert response.status_code == 409
        data = response.json()
        assert "homing" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_run_theta_rho_file_not_found(self, async_client, mock_state, tmp_path):
        """Test run_theta_rho returns 404 for non-existent file."""
        patterns_dir = tmp_path / "patterns"
        patterns_dir.mkdir()

        mock_state.conn = MagicMock()
        mock_state.conn.is_connected.return_value = True
        mock_state.is_homing = False

        with patch("main.state", mock_state):
            with patch("main.pattern_manager.THETA_RHO_DIR", str(patterns_dir)):
                response = await async_client.post(
                    "/run_theta_rho",
                    json={
                        "file_name": "nonexistent.thr",
                        "pre_execution": "none"
                    }
                )

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()


class TestStopExecution:
    """Tests for /stop_execution endpoint."""

    @pytest.mark.asyncio
    async def test_stop_execution(self, async_client, mock_state):
        """Test stop_execution endpoint."""
        mock_state.is_homing = False
        mock_state.conn = MagicMock()
        mock_state.conn.is_connected.return_value = True

        with patch("main.state", mock_state):
            with patch("main.pattern_manager.stop_actions", new_callable=AsyncMock, return_value=True):
                response = await async_client.post("/stop_execution")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_stop_execution_when_disconnected(self, async_client, mock_state):
        """Test stop_execution fails when not connected."""
        mock_state.conn = None

        with patch("main.state", mock_state):
            response = await async_client.post("/stop_execution")

        assert response.status_code == 400
        data = response.json()
        assert "not established" in data["detail"].lower()


class TestPauseResumeExecution:
    """Tests for /pause_execution and /resume_execution endpoints."""

    @pytest.mark.asyncio
    async def test_pause_execution(self, async_client):
        """Test pause_execution endpoint."""
        # Mock check_table_is_idle to return False (something is playing)
        with patch("main.pattern_manager.check_table_is_idle", return_value=False):
            with patch("main.pattern_manager.pause_execution", return_value=True):
                response = await async_client.post("/pause_execution")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_pause_execution_when_idle(self, async_client):
        """Test pause_execution returns 400 when nothing is playing."""
        # Mock check_table_is_idle to return True (table is idle)
        with patch("main.pattern_manager.check_table_is_idle", return_value=True):
            response = await async_client.post("/pause_execution")

        assert response.status_code == 400
        data = response.json()
        assert "nothing is currently playing" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_resume_execution(self, async_client):
        """Test resume_execution endpoint."""
        # Mock state.pause_requested to True (execution is paused)
        from main import state
        original_value = state.pause_requested
        try:
            state.pause_requested = True
            with patch("main.pattern_manager.resume_execution", return_value=True):
                response = await async_client.post("/resume_execution")
        finally:
            state.pause_requested = original_value

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_resume_execution_when_not_paused(self, async_client):
        """Test resume_execution returns 400 when not paused."""
        # Mock state.pause_requested to False (not paused)
        from main import state
        original_value = state.pause_requested
        try:
            state.pause_requested = False
            response = await async_client.post("/resume_execution")
        finally:
            state.pause_requested = original_value

        assert response.status_code == 400
        data = response.json()
        assert "not paused" in data["detail"].lower()


class TestDeleteThetaRhoFile:
    """Tests for /delete_theta_rho_file endpoint."""

    @pytest.mark.asyncio
    async def test_delete_theta_rho_file_success(self, async_client, tmp_path):
        """Test deleting an existing pattern file."""
        patterns_dir = tmp_path / "patterns"
        patterns_dir.mkdir()
        test_file = patterns_dir / "test.thr"
        test_file.write_text("0 0.5")

        # Must patch pattern_manager.THETA_RHO_DIR which is what the endpoint uses
        with patch("main.pattern_manager.THETA_RHO_DIR", str(patterns_dir)):
            with patch("modules.core.cache_manager.delete_pattern_cache", return_value=True):
                response = await async_client.post(
                    "/delete_theta_rho_file",
                    json={"file_name": "test.thr"}
                )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Verify file was actually deleted
        assert not test_file.exists()

    @pytest.mark.asyncio
    async def test_delete_theta_rho_file_not_found(self, async_client, tmp_path):
        """Test deleting a non-existent file returns error."""
        patterns_dir = tmp_path / "patterns"
        patterns_dir.mkdir()

        with patch("main.pattern_manager.THETA_RHO_DIR", str(patterns_dir)):
            response = await async_client.post(
                "/delete_theta_rho_file",
                json={"file_name": "nonexistent.thr"}
            )

        assert response.status_code == 404
