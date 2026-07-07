"""
Unit tests for the FluidNC HTTP connection layer.

The backend drives the board over HTTP now (no serial/GRBL transport), so these
tests cover the FluidNCClient command/route formatting and the connection_manager
helpers that sit on top of it. HTTP is mocked — no board required.
"""
import pytest
from unittest.mock import patch, MagicMock

from modules.connection.fluidnc_client import FluidNCClient


def _resp(text="ok", json_data=None, status=200):
    r = MagicMock()
    r.text = text
    r.status_code = status
    r.raise_for_status = MagicMock()
    if json_data is not None:
        r.json = MagicMock(return_value=json_data)
    return r


class TestFluidNCClient:
    """Command / route formatting for the board client."""

    def test_run_pattern_uses_sd_run(self):
        client = FluidNCClient("http://board")
        with patch("modules.connection.fluidnc_client.requests") as req:
            req.get.return_value = _resp()
            client.run_pattern("/patterns/star.thr")
        url, kwargs = req.get.call_args[0][0], req.get.call_args[1]
        assert url == "http://board/command"
        assert kwargs["params"] == {"plain": "$SD/Run=/patterns/star.thr"}

    def test_run_pattern_with_clear_uses_sand_run(self):
        client = FluidNCClient("http://board")
        with patch("modules.connection.fluidnc_client.requests") as req:
            req.get.return_value = _resp()
            client.run_pattern("/patterns/star.thr", clear="adaptive")
        assert req.get.call_args[1]["params"] == {
            "plain": "$Sand/Run=/patterns/star.thr clear=adaptive"
        }

    def test_set_feed_mm(self):
        client = FluidNCClient("http://board")
        with patch("modules.connection.fluidnc_client.requests") as req:
            req.get.return_value = _resp()
            client.set_feed(mm=850)
        assert req.get.call_args[0][0] == "http://board/sand_feed"
        assert req.get.call_args[1]["params"] == {"mm": 850}

    def test_goto_includes_only_given_axes(self):
        client = FluidNCClient("http://board")
        with patch("modules.connection.fluidnc_client.requests") as req:
            req.get.return_value = _resp()
            client.goto(rho=0)
        assert req.get.call_args[1]["params"] == {"rho": 0}

    def test_stop_hits_sand_stop(self):
        client = FluidNCClient("http://board")
        with patch("modules.connection.fluidnc_client.requests") as req:
            req.get.return_value = _resp()
            client.stop()
        assert req.get.call_args[0][0] == "http://board/sand_stop"

    def test_get_status_returns_json(self):
        client = FluidNCClient("http://board")
        with patch("modules.connection.fluidnc_client.requests") as req:
            req.get.return_value = _resp(json_data={"state": "Idle", "theta": 1.0})
            st = client.get_status()
        assert st["state"] == "Idle"

    def test_reachable_true_and_false(self):
        client = FluidNCClient("http://board")
        with patch("modules.connection.fluidnc_client.requests") as req:
            req.get.return_value = _resp(json_data={"state": "Idle"})
            assert client.reachable() is True
            assert client.is_connected() is True
            req.get.side_effect = Exception("timeout")
            assert client.reachable() is False
            assert client.is_connected() is False

    def test_upload_file_field_naming(self):
        """The multipart file part is named by the full SD path, plus a '<path>S' size field."""
        client = FluidNCClient("http://board")
        with patch("modules.connection.fluidnc_client.requests") as req:
            req.post.return_value = _resp(text="{}", json_data={})
            client.upload_file("/playlists/a.txt", b"hello", "/playlists")
        kwargs = req.post.call_args[1]
        assert kwargs["params"] == {"path": "/playlists"}
        assert kwargs["data"] == {"/playlists/a.txtS": "5"}
        assert "/playlists/a.txt" in kwargs["files"]

    def test_delete_file_action(self):
        client = FluidNCClient("http://board")
        with patch("modules.connection.fluidnc_client.requests") as req:
            req.get.return_value = _resp(text="{}", json_data={"status": "ok"})
            client.delete_file("patterns", "old.thr")
        assert req.get.call_args[1]["params"]["action"] == "delete"
        assert req.get.call_args[1]["params"]["filename"] == "old.thr"


class TestConnectionManagerHelpers:
    """Helpers in connection_manager that sit on top of the client."""

    def test_normalize_board_url(self):
        from modules.connection import connection_manager as cm
        assert cm._normalize_board_url("192.168.1.5") == "http://192.168.1.5"
        assert cm._normalize_board_url("http://x/") == "http://x"
        assert cm._normalize_board_url("") == ""

    def test_list_serial_ports_returns_board_url(self, mock_state):
        from modules.connection import connection_manager as cm
        mock_state.board_url = "http://192.168.1.9"
        with patch("modules.connection.connection_manager.state", mock_state):
            ports = cm.list_serial_ports()
        assert ports == ["http://192.168.1.9"]

    def test_apply_status_maps_fields(self, mock_state):
        from modules.connection import connection_manager as cm
        with patch("modules.connection.connection_manager.state", mock_state):
            cm.apply_status({"theta": 1.23, "rho": 0.5, "feed": 900})
        assert mock_state.current_theta == 1.23
        assert mock_state.current_rho == 0.5
        assert mock_state.speed == 900

    def test_is_machine_idle_true(self, mock_state):
        from modules.connection import connection_manager as cm
        mock_state.conn.get_status.return_value = {"state": "Idle"}
        with patch("modules.connection.connection_manager.state", mock_state):
            assert cm.is_machine_idle() is True

    def test_is_machine_idle_running(self, mock_state):
        from modules.connection import connection_manager as cm
        mock_state.conn.get_status.return_value = {"state": "Run"}
        with patch("modules.connection.connection_manager.state", mock_state):
            assert cm.is_machine_idle() is False

    def test_is_machine_idle_no_connection(self, mock_state):
        from modules.connection import connection_manager as cm
        mock_state.conn = None
        with patch("modules.connection.connection_manager.state", mock_state):
            assert cm.is_machine_idle() is False
