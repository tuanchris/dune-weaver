"""
Unit tests for playlist_manager CRUD operations.

Tests the core playlist management functions:
- Loading playlists from file
- Creating playlists
- Getting playlists
- Modifying playlists
- Deleting playlists
- Listing playlists
- Renaming playlists
"""
import json
import pytest
from unittest.mock import patch, MagicMock


class TestPlaylistManagerCRUD:
    """Tests for playlist CRUD operations."""

    @pytest.fixture
    def playlists_file(self, tmp_path):
        """Create a temporary playlists.json file."""
        file_path = tmp_path / "playlists.json"
        file_path.write_text("{}")
        return str(file_path)

    @pytest.fixture
    def playlist_manager_patched(self, playlists_file):
        """Patch PLAYLISTS_FILE to use temporary file."""
        with patch("modules.core.playlist_manager.PLAYLISTS_FILE", playlists_file):
            # Need to re-import to get patched version
            from modules.core import playlist_manager
            yield playlist_manager

    def test_load_playlists_empty_file(self, playlists_file, playlist_manager_patched):
        """Test loading playlists from an empty file returns empty dict."""
        result = playlist_manager_patched.load_playlists()
        assert result == {}

    def test_load_playlists_with_data(self, playlists_file, playlist_manager_patched):
        """Test loading playlists with existing data."""
        # Write some data to the file
        with open(playlists_file, "w") as f:
            json.dump({"my_playlist": ["pattern1.thr", "pattern2.thr"]}, f)

        result = playlist_manager_patched.load_playlists()

        assert "my_playlist" in result
        assert result["my_playlist"] == ["pattern1.thr", "pattern2.thr"]

    def test_create_playlist(self, playlists_file, playlist_manager_patched):
        """Test creating a new playlist."""
        files = ["circle.thr", "spiral.thr"]

        result = playlist_manager_patched.create_playlist("test_playlist", files)

        assert result is True

        # Verify it was saved
        playlists = playlist_manager_patched.load_playlists()
        assert "test_playlist" in playlists
        assert playlists["test_playlist"] == files

    def test_create_playlist_overwrites_existing(self, playlists_file, playlist_manager_patched):
        """Test creating a playlist with existing name overwrites it."""
        # Create initial playlist
        playlist_manager_patched.create_playlist("test_playlist", ["old.thr"])

        # Create again with same name
        playlist_manager_patched.create_playlist("test_playlist", ["new.thr"])

        playlists = playlist_manager_patched.load_playlists()
        assert playlists["test_playlist"] == ["new.thr"]

    def test_get_playlist_exists(self, playlists_file, playlist_manager_patched):
        """Test getting an existing playlist."""
        playlist_manager_patched.create_playlist("my_playlist", ["a.thr", "b.thr"])

        result = playlist_manager_patched.get_playlist("my_playlist")

        assert result is not None
        assert result["name"] == "my_playlist"
        assert result["files"] == ["a.thr", "b.thr"]

    def test_get_playlist_not_found(self, playlists_file, playlist_manager_patched):
        """Test getting a non-existent playlist returns None."""
        result = playlist_manager_patched.get_playlist("nonexistent")

        assert result is None

    def test_modify_playlist(self, playlists_file, playlist_manager_patched):
        """Test modifying an existing playlist."""
        # Create initial playlist
        playlist_manager_patched.create_playlist("my_playlist", ["old.thr"])

        # Modify it
        new_files = ["new1.thr", "new2.thr", "new3.thr"]
        result = playlist_manager_patched.modify_playlist("my_playlist", new_files)

        assert result is True

        # Verify changes
        playlist = playlist_manager_patched.get_playlist("my_playlist")
        assert playlist["files"] == new_files

    def test_delete_playlist(self, playlists_file, playlist_manager_patched):
        """Test deleting a playlist."""
        # Create a playlist
        playlist_manager_patched.create_playlist("to_delete", ["pattern.thr"])

        # Delete it
        result = playlist_manager_patched.delete_playlist("to_delete")

        assert result is True

        # Verify it's gone
        playlist = playlist_manager_patched.get_playlist("to_delete")
        assert playlist is None

    def test_delete_playlist_not_found(self, playlists_file, playlist_manager_patched):
        """Test deleting a non-existent playlist returns False."""
        result = playlist_manager_patched.delete_playlist("nonexistent")

        assert result is False

    def test_list_all_playlists(self, playlists_file, playlist_manager_patched):
        """Test listing all playlist names."""
        # Create multiple playlists
        playlist_manager_patched.create_playlist("playlist1", ["a.thr"])
        playlist_manager_patched.create_playlist("playlist2", ["b.thr"])
        playlist_manager_patched.create_playlist("playlist3", ["c.thr"])

        result = playlist_manager_patched.list_all_playlists()

        assert len(result) == 3
        assert "playlist1" in result
        assert "playlist2" in result
        assert "playlist3" in result

    def test_list_all_playlists_empty(self, playlists_file, playlist_manager_patched):
        """Test listing playlists when none exist."""
        result = playlist_manager_patched.list_all_playlists()

        assert result == []

    def test_add_to_playlist(self, playlists_file, playlist_manager_patched):
        """Test adding a pattern to an existing playlist."""
        # Create playlist
        playlist_manager_patched.create_playlist("my_playlist", ["existing.thr"])

        # Add pattern
        result = playlist_manager_patched.add_to_playlist("my_playlist", "new_pattern.thr")

        assert result is True

        # Verify
        playlist = playlist_manager_patched.get_playlist("my_playlist")
        assert "new_pattern.thr" in playlist["files"]
        assert len(playlist["files"]) == 2

    def test_add_to_playlist_not_found(self, playlists_file, playlist_manager_patched):
        """Test adding to a non-existent playlist returns False."""
        result = playlist_manager_patched.add_to_playlist("nonexistent", "pattern.thr")

        assert result is False


class TestPlaylistRename:
    """Tests for playlist rename functionality."""

    @pytest.fixture
    def playlists_file(self, tmp_path):
        """Create a temporary playlists.json file."""
        file_path = tmp_path / "playlists.json"
        file_path.write_text("{}")
        return str(file_path)

    @pytest.fixture
    def playlist_manager_patched(self, playlists_file):
        """Patch PLAYLISTS_FILE to use temporary file."""
        with patch("modules.core.playlist_manager.PLAYLISTS_FILE", playlists_file):
            from modules.core import playlist_manager
            yield playlist_manager

    def test_rename_playlist_success(self, playlists_file, playlist_manager_patched):
        """Test successfully renaming a playlist."""
        # Create initial playlist
        playlist_manager_patched.create_playlist("old_name", ["a.thr", "b.thr"])

        # Rename it
        success, message = playlist_manager_patched.rename_playlist("old_name", "new_name")

        assert success is True
        assert "new_name" in message

        # Verify old name is gone
        assert playlist_manager_patched.get_playlist("old_name") is None

        # Verify new name exists with same files
        new_playlist = playlist_manager_patched.get_playlist("new_name")
        assert new_playlist is not None
        assert new_playlist["files"] == ["a.thr", "b.thr"]

    def test_rename_playlist_not_found(self, playlists_file, playlist_manager_patched):
        """Test renaming a non-existent playlist."""
        success, message = playlist_manager_patched.rename_playlist("nonexistent", "new_name")

        assert success is False
        assert "not found" in message.lower()

    def test_rename_playlist_empty_name(self, playlists_file, playlist_manager_patched):
        """Test renaming with empty name fails."""
        playlist_manager_patched.create_playlist("my_playlist", ["a.thr"])

        success, message = playlist_manager_patched.rename_playlist("my_playlist", "")

        assert success is False
        assert "empty" in message.lower()

    def test_rename_playlist_whitespace_name(self, playlists_file, playlist_manager_patched):
        """Test renaming with whitespace-only name fails."""
        playlist_manager_patched.create_playlist("my_playlist", ["a.thr"])

        success, message = playlist_manager_patched.rename_playlist("my_playlist", "   ")

        assert success is False
        assert "empty" in message.lower()

    def test_rename_playlist_same_name(self, playlists_file, playlist_manager_patched):
        """Test renaming to the same name succeeds with unchanged message."""
        playlist_manager_patched.create_playlist("my_playlist", ["a.thr"])

        success, message = playlist_manager_patched.rename_playlist("my_playlist", "my_playlist")

        assert success is True
        assert "unchanged" in message.lower()

    def test_rename_playlist_name_exists(self, playlists_file, playlist_manager_patched):
        """Test renaming to an existing playlist name fails."""
        playlist_manager_patched.create_playlist("playlist1", ["a.thr"])
        playlist_manager_patched.create_playlist("playlist2", ["b.thr"])

        success, message = playlist_manager_patched.rename_playlist("playlist1", "playlist2")

        assert success is False
        assert "already exists" in message.lower()

    def test_rename_playlist_trims_whitespace(self, playlists_file, playlist_manager_patched):
        """Test renaming trims whitespace from new name."""
        playlist_manager_patched.create_playlist("old_name", ["a.thr"])

        success, message = playlist_manager_patched.rename_playlist("old_name", "  new_name  ")

        assert success is True

        # Verify trimmed name is used
        assert playlist_manager_patched.get_playlist("new_name") is not None
        assert playlist_manager_patched.get_playlist("  new_name  ") is None
