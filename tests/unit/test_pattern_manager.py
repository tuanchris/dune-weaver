"""
Unit tests for pattern_manager parsing logic.

Tests the core pattern file operations:
- Parsing theta-rho files
- Handling comments and empty lines
- Error handling for invalid files
- Listing pattern files
"""
import os
import pytest
from unittest.mock import patch, MagicMock


class TestParseTheTaRhoFile:
    """Tests for parse_theta_rho_file function."""

    def test_parse_theta_rho_file_valid(self, tmp_path):
        """Test parsing a valid theta-rho file."""
        # Create test file
        test_file = tmp_path / "valid.thr"
        test_file.write_text("0.0 0.5\n1.57 0.8\n3.14 0.3\n")

        from modules.core.pattern_manager import parse_theta_rho_file

        coordinates = parse_theta_rho_file(str(test_file))

        assert len(coordinates) == 3
        assert coordinates[0] == (0.0, 0.5)
        assert coordinates[1] == (1.57, 0.8)
        assert coordinates[2] == (3.14, 0.3)

    def test_parse_theta_rho_file_with_comments(self, tmp_path):
        """Test parsing handles # comments correctly."""
        test_file = tmp_path / "commented.thr"
        test_file.write_text("""# This is a header comment
0.0 0.5
# Another comment in the middle
1.0 0.6
# Trailing comment
""")

        from modules.core.pattern_manager import parse_theta_rho_file

        coordinates = parse_theta_rho_file(str(test_file))

        assert len(coordinates) == 2
        assert coordinates[0] == (0.0, 0.5)
        assert coordinates[1] == (1.0, 0.6)

    def test_parse_theta_rho_file_empty_lines(self, tmp_path):
        """Test parsing handles empty lines correctly."""
        test_file = tmp_path / "spaced.thr"
        test_file.write_text("""0.0 0.5

1.0 0.6

2.0 0.7

""")

        from modules.core.pattern_manager import parse_theta_rho_file

        coordinates = parse_theta_rho_file(str(test_file))

        assert len(coordinates) == 3
        assert coordinates[0] == (0.0, 0.5)
        assert coordinates[1] == (1.0, 0.6)
        assert coordinates[2] == (2.0, 0.7)

    def test_parse_theta_rho_file_not_found(self, tmp_path):
        """Test parsing a non-existent file returns empty list."""
        from modules.core.pattern_manager import parse_theta_rho_file

        coordinates = parse_theta_rho_file(str(tmp_path / "nonexistent.thr"))

        assert coordinates == []

    def test_parse_theta_rho_file_invalid_lines(self, tmp_path):
        """Test parsing skips invalid lines (non-numeric values)."""
        test_file = tmp_path / "invalid.thr"
        test_file.write_text("""0.0 0.5
invalid line
1.0 0.6
not a number here
2.0 0.7
""")

        from modules.core.pattern_manager import parse_theta_rho_file

        coordinates = parse_theta_rho_file(str(test_file))

        # Should only get the valid lines
        assert len(coordinates) == 3
        assert coordinates[0] == (0.0, 0.5)
        assert coordinates[1] == (1.0, 0.6)
        assert coordinates[2] == (2.0, 0.7)

    def test_parse_theta_rho_file_whitespace_handling(self, tmp_path):
        """Test parsing handles various whitespace correctly."""
        test_file = tmp_path / "whitespace.thr"
        test_file.write_text("""  0.0 0.5
	1.0 0.6
0.0    0.5
""")

        from modules.core.pattern_manager import parse_theta_rho_file

        coordinates = parse_theta_rho_file(str(test_file))

        assert len(coordinates) == 3

    def test_parse_theta_rho_file_scientific_notation(self, tmp_path):
        """Test parsing handles scientific notation."""
        test_file = tmp_path / "scientific.thr"
        test_file.write_text("""1.5e-3 0.5
3.14159 1.0e0
""")

        from modules.core.pattern_manager import parse_theta_rho_file

        coordinates = parse_theta_rho_file(str(test_file))

        assert len(coordinates) == 2
        assert coordinates[0][0] == pytest.approx(0.0015)
        assert coordinates[1][1] == pytest.approx(1.0)

    def test_parse_theta_rho_file_negative_values(self, tmp_path):
        """Test parsing handles negative values."""
        test_file = tmp_path / "negative.thr"
        test_file.write_text("""-3.14 0.5
0.0 -0.5
-1.0 -0.3
""")

        from modules.core.pattern_manager import parse_theta_rho_file

        coordinates = parse_theta_rho_file(str(test_file))

        assert len(coordinates) == 3
        assert coordinates[0] == (-3.14, 0.5)
        assert coordinates[1] == (0.0, -0.5)
        assert coordinates[2] == (-1.0, -0.3)

    def test_parse_theta_rho_file_only_comments(self, tmp_path):
        """Test parsing a file with only comments returns empty list."""
        test_file = tmp_path / "comments_only.thr"
        test_file.write_text("""# This file only has comments
# No actual coordinates
# Just documentation
""")

        from modules.core.pattern_manager import parse_theta_rho_file

        coordinates = parse_theta_rho_file(str(test_file))

        assert coordinates == []

    def test_parse_theta_rho_file_empty_file(self, tmp_path):
        """Test parsing an empty file returns empty list."""
        test_file = tmp_path / "empty.thr"
        test_file.write_text("")

        from modules.core.pattern_manager import parse_theta_rho_file

        coordinates = parse_theta_rho_file(str(test_file))

        assert coordinates == []


class TestListThetaRhoFiles:
    """Tests for list_theta_rho_files function."""

    def test_list_theta_rho_files_basic(self, tmp_path):
        """Test listing pattern files in directory."""
        # Create test pattern files
        patterns_dir = tmp_path / "patterns"
        patterns_dir.mkdir()
        (patterns_dir / "circle.thr").write_text("0 0.5")
        (patterns_dir / "spiral.thr").write_text("0 0.5")
        (patterns_dir / "readme.txt").write_text("not a pattern")

        with patch("modules.core.pattern_manager.THETA_RHO_DIR", str(patterns_dir)):
            from modules.core.pattern_manager import list_theta_rho_files

            files = list_theta_rho_files()

        # Should only list .thr files
        assert len(files) == 2
        assert "circle.thr" in files
        assert "spiral.thr" in files

    def test_list_theta_rho_files_subdirectories(self, tmp_path):
        """Test listing pattern files in subdirectories."""
        patterns_dir = tmp_path / "patterns"
        patterns_dir.mkdir()

        # Create subdirectory with patterns
        subdir = patterns_dir / "custom"
        subdir.mkdir()
        (subdir / "custom_pattern.thr").write_text("0 0.5")
        (patterns_dir / "root_pattern.thr").write_text("0 0.5")

        with patch("modules.core.pattern_manager.THETA_RHO_DIR", str(patterns_dir)):
            from modules.core.pattern_manager import list_theta_rho_files

            files = list_theta_rho_files()

        assert len(files) == 2
        assert "root_pattern.thr" in files
        # Subdirectory patterns should include relative path
        assert "custom/custom_pattern.thr" in files

    def test_list_theta_rho_files_skips_cached_images(self, tmp_path):
        """Test that cached_images directories are skipped."""
        patterns_dir = tmp_path / "patterns"
        patterns_dir.mkdir()

        # Create cached_images directory with files
        cache_dir = patterns_dir / "cached_images"
        cache_dir.mkdir()
        (cache_dir / "preview.thr").write_text("should be skipped")

        (patterns_dir / "real_pattern.thr").write_text("0 0.5")

        with patch("modules.core.pattern_manager.THETA_RHO_DIR", str(patterns_dir)):
            from modules.core.pattern_manager import list_theta_rho_files

            files = list_theta_rho_files()

        # Should only list the real pattern, not cached files
        assert len(files) == 1
        assert "real_pattern.thr" in files

    def test_list_theta_rho_files_empty_directory(self, tmp_path):
        """Test listing from empty directory returns empty list."""
        patterns_dir = tmp_path / "patterns"
        patterns_dir.mkdir()

        with patch("modules.core.pattern_manager.THETA_RHO_DIR", str(patterns_dir)):
            from modules.core.pattern_manager import list_theta_rho_files

            files = list_theta_rho_files()

        assert files == []


class TestGetStatus:
    """Tests for get_status function."""

    def test_get_status_idle(self, mock_state):
        """Test get_status returns expected fields when idle."""
        with patch("modules.core.pattern_manager.state", mock_state):
            from modules.core.pattern_manager import get_status

            status = get_status()

        assert "current_file" in status
        assert "is_paused" in status
        assert "is_running" in status
        assert "is_homing" in status
        assert "progress" in status
        assert "playlist" in status
        assert "speed" in status
        assert "connection_status" in status
        assert status["is_running"] is False
        assert status["current_file"] is None

    def test_get_status_running_pattern(self, mock_state):
        """Test get_status reflects running pattern."""
        mock_state.current_playing_file = "test_pattern.thr"
        mock_state.stop_requested = False
        mock_state.execution_progress = (50, 100, 30.5, 60.0)

        with patch("modules.core.pattern_manager.state", mock_state):
            from modules.core.pattern_manager import get_status

            status = get_status()

        assert status["is_running"] is True
        assert status["current_file"] == "test_pattern.thr"
        assert status["progress"] is not None
        assert status["progress"]["current"] == 50
        assert status["progress"]["total"] == 100
        assert status["progress"]["percentage"] == 50.0

    def test_get_status_paused(self, mock_state):
        """Test get_status reflects paused state."""
        mock_state.pause_requested = True

        with patch("modules.core.pattern_manager.state", mock_state):
            with patch("modules.core.pattern_manager.is_in_scheduled_pause_period", return_value=False):
                from modules.core.pattern_manager import get_status

                status = get_status()

        assert status["is_paused"] is True
        assert status["manual_pause"] is True

    def test_get_status_with_playlist(self, mock_state):
        """Test get_status includes playlist info when running."""
        mock_state.current_playlist = ["a.thr", "b.thr", "c.thr"]
        mock_state.current_playlist_name = "test_playlist"
        mock_state.current_playlist_index = 1
        mock_state.playlist_mode = "indefinite"

        with patch("modules.core.pattern_manager.state", mock_state):
            from modules.core.pattern_manager import get_status

            status = get_status()

        assert status["playlist"] is not None
        assert status["playlist"]["current_index"] == 1
        assert status["playlist"]["total_files"] == 3
        assert status["playlist"]["mode"] == "indefinite"
        assert status["playlist"]["name"] == "test_playlist"


class TestIsClearPattern:
    """Tests for is_clear_pattern function."""

    def test_is_clear_pattern_matches_standard(self):
        """Test identifying standard clear patterns."""
        from modules.core.pattern_manager import is_clear_pattern

        assert is_clear_pattern("./patterns/clear_from_out.thr") is True
        assert is_clear_pattern("./patterns/clear_from_in.thr") is True
        assert is_clear_pattern("./patterns/clear_sideway.thr") is True

    def test_is_clear_pattern_matches_mini(self):
        """Test identifying mini table clear patterns."""
        from modules.core.pattern_manager import is_clear_pattern

        assert is_clear_pattern("./patterns/clear_from_out_mini.thr") is True
        assert is_clear_pattern("./patterns/clear_from_in_mini.thr") is True
        assert is_clear_pattern("./patterns/clear_sideway_mini.thr") is True

    def test_is_clear_pattern_matches_pro(self):
        """Test identifying pro table clear patterns."""
        from modules.core.pattern_manager import is_clear_pattern

        assert is_clear_pattern("./patterns/clear_from_out_pro.thr") is True
        assert is_clear_pattern("./patterns/clear_from_in_pro.thr") is True
        assert is_clear_pattern("./patterns/clear_sideway_pro.thr") is True

    def test_is_clear_pattern_rejects_regular_patterns(self):
        """Test that regular patterns are not identified as clear patterns."""
        from modules.core.pattern_manager import is_clear_pattern

        assert is_clear_pattern("./patterns/circle.thr") is False
        assert is_clear_pattern("./patterns/spiral.thr") is False
        assert is_clear_pattern("./patterns/custom/my_pattern.thr") is False
