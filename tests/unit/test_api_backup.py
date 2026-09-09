"""
Unit tests for the backup API endpoints.

Tests the following endpoints:
- GET /api/backup/settings
- GET /api/backup/custom_patterns
"""
import io
import json
import os
import zipfile

import pytest


class TestBackupSettings:
    """Tests for /api/backup/settings endpoint."""

    @pytest.mark.asyncio
    async def test_backup_settings_returns_zip(self, async_client, tmp_path, monkeypatch):
        """Returns a zip that contains settings.json and playlists.json."""
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(json.dumps({"speed": 42}))
        playlists_file = tmp_path / "playlists.json"
        playlists_file.write_text(json.dumps({"My Playlist": ["a.thr"]}))

        import main

        monkeypatch.setattr(main.state, "SETTINGS_FILE", str(settings_file))
        monkeypatch.setattr(main.state, "custom_logo", None)
        monkeypatch.setattr(main.state, "save", lambda: None)
        monkeypatch.setattr(main.playlist_manager, "PLAYLISTS_FILE", str(playlists_file))

        response = await async_client.get("/api/backup/settings")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert "attachment" in response.headers["content-disposition"]

        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            names = zf.namelist()
            assert "settings.json" in names
            assert "playlists.json" in names
            assert json.loads(zf.read("settings.json")) == {"speed": 42}
            assert json.loads(zf.read("playlists.json")) == {"My Playlist": ["a.thr"]}

    @pytest.mark.asyncio
    async def test_backup_settings_includes_custom_logo(self, async_client, tmp_path, monkeypatch):
        """Includes the custom logo file in the archive when set."""
        settings_file = tmp_path / "settings.json"
        settings_file.write_text("{}")
        playlists_file = tmp_path / "playlists.json"
        playlists_file.write_text("{}")

        branding_dir = tmp_path / "branding"
        branding_dir.mkdir()
        logo_file = branding_dir / "logo-xyz.png"
        logo_file.write_bytes(b"\x89PNG\r\n\x1a\nfake")

        import main

        monkeypatch.setattr(main.state, "SETTINGS_FILE", str(settings_file))
        monkeypatch.setattr(main.state, "custom_logo", "logo-xyz.png")
        monkeypatch.setattr(main.state, "save", lambda: None)
        monkeypatch.setattr(main.playlist_manager, "PLAYLISTS_FILE", str(playlists_file))
        monkeypatch.setattr(main, "CUSTOM_BRANDING_DIR", str(branding_dir))

        response = await async_client.get("/api/backup/settings")

        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            assert "custom/logo-xyz.png" in zf.namelist()
            assert zf.read("custom/logo-xyz.png") == b"\x89PNG\r\n\x1a\nfake"


class TestBackupCustomPatterns:
    """Tests for /api/backup/custom_patterns endpoint."""

    @pytest.mark.asyncio
    async def test_backup_custom_patterns_returns_zip(self, async_client, tmp_path, monkeypatch):
        """Zips every file under patterns/custom_patterns/."""
        theta_rho_dir = tmp_path / "patterns"
        custom = theta_rho_dir / "custom_patterns"
        custom.mkdir(parents=True)
        (custom / "one.thr").write_text("0 0\n1 1\n")
        (custom / "two.thr").write_text("2 2\n")

        import main

        monkeypatch.setattr(main.pattern_manager, "THETA_RHO_DIR", str(theta_rho_dir))

        response = await async_client.get("/api/backup/custom_patterns")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            names = sorted(zf.namelist())
            assert names == ["one.thr", "two.thr"]
            assert zf.read("one.thr").decode() == "0 0\n1 1\n"

    @pytest.mark.asyncio
    async def test_backup_custom_patterns_skips_hidden_files(self, async_client, tmp_path, monkeypatch):
        """The archive omits dotfiles like .gitignore."""
        theta_rho_dir = tmp_path / "patterns"
        custom = theta_rho_dir / "custom_patterns"
        custom.mkdir(parents=True)
        (custom / ".gitignore").write_text("*\n")
        (custom / "keep.thr").write_text("0 0\n")

        import main

        monkeypatch.setattr(main.pattern_manager, "THETA_RHO_DIR", str(theta_rho_dir))

        response = await async_client.get("/api/backup/custom_patterns")

        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            names = zf.namelist()
            assert names == ["keep.thr"]

    @pytest.mark.asyncio
    async def test_backup_custom_patterns_empty_when_directory_missing(
        self, async_client, tmp_path, monkeypatch
    ):
        """Returns an empty zip (not a 500) when the directory does not exist."""
        theta_rho_dir = tmp_path / "patterns"
        theta_rho_dir.mkdir()

        import main

        monkeypatch.setattr(main.pattern_manager, "THETA_RHO_DIR", str(theta_rho_dir))
        assert not os.path.isdir(os.path.join(str(theta_rho_dir), "custom_patterns"))

        response = await async_client.get("/api/backup/custom_patterns")

        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            assert zf.namelist() == []
