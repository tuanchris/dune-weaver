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


class TestSdPathResolution:
    """_to_sd_path / make_sd_path_resolver: host <-> board SD path mapping."""

    def test_to_sd_path_keeps_custom_patterns_dir(self):
        from modules.core.pattern_manager import _to_sd_path
        # The old find('patterns/') logic matched inside 'custom_patterns/'
        # and dropped that directory from the SD path.
        assert _to_sd_path("custom_patterns/foo.thr") == "/patterns/custom_patterns/foo.thr"
        assert _to_sd_path("./patterns/custom_patterns/foo.thr") == "/patterns/custom_patterns/foo.thr"
        assert _to_sd_path("./patterns/star.thr") == "/patterns/star.thr"
        assert _to_sd_path("patterns/sub/wave.thr") == "/patterns/sub/wave.thr"

    def test_resolver_reuses_existing_board_suffix(self):
        from modules.core import pattern_manager
        conn = MagicMock()
        conn.list_patterns.return_value = [
            "sand-patterns/patterns/alligator.thr",
            "star.thr",
        ]
        resolve = pattern_manager.make_sd_path_resolver(conn)
        # Host copy nested under custom_patterns/ reuses the board's location.
        assert (
            resolve("custom_patterns/sand-patterns/patterns/alligator.thr")
            == "/patterns/sand-patterns/patterns/alligator.thr"
        )
        # Exact board match stays canonical.
        assert resolve("./patterns/star.thr") == "/patterns/star.thr"
        # Not on the board at all: canonical path (will be uploaded there).
        assert resolve("custom_patterns/new.thr") == "/patterns/custom_patterns/new.thr"
        # The listing is fetched once for the whole resolver lifetime.
        conn.list_patterns.assert_called_once()

    def test_resolver_unique_basename_match(self):
        from modules.core import pattern_manager
        conn = MagicMock()
        conn.list_patterns.return_value = ["library/animals/heart.thr"]
        resolve = pattern_manager.make_sd_path_resolver(conn)
        assert resolve("uploads/heart.thr") == "/patterns/library/animals/heart.thr"

    def test_resolver_ambiguous_basename_falls_back(self):
        from modules.core import pattern_manager
        conn = MagicMock()
        conn.list_patterns.return_value = ["a/heart.thr", "b/heart.thr"]
        resolve = pattern_manager.make_sd_path_resolver(conn)
        assert resolve("uploads/heart.thr") == "/patterns/uploads/heart.thr"

    def test_resolver_survives_listing_failure(self):
        from modules.core import pattern_manager
        conn = MagicMock()
        conn.list_patterns.side_effect = RuntimeError("board offline")
        resolve = pattern_manager.make_sd_path_resolver(conn)
        assert resolve("custom_patterns/foo.thr") == "/patterns/custom_patterns/foo.thr"
