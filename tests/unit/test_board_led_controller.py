"""
Unit tests for the board (firmware) LED controller — focused on the 'ball'
tracker: param clamping, key mapping, and status readback.
"""
from unittest.mock import patch

from modules.led.board_led_controller import BoardLEDController
from modules.core.state import state


class FakeConn:
    """Records /sand_led calls and serves a scriptable settings map."""

    def __init__(self, settings=None):
        self.led_calls = []
        self._settings = settings or {}

    def is_connected(self):
        return True

    def set_led(self, **keys):
        self.led_calls.append(keys)
        return "ok"

    def get_settings(self):
        return self._settings


def _controller(conn):
    # The controller reaches hardware through state.conn (imported lazily).
    return BoardLEDController(), patch.object(state, "conn", conn)


class TestSetBall:
    def test_maps_and_forwards_keys(self):
        conn = FakeConn()
        c, ctx = _controller(conn)
        with ctx:
            c.set_ball(fgbright=200, bgbright=40, size=8, align=120,
                       direction="ccw", bg="plasma", color="#FF0040", color2="000028")
        assert len(conn.led_calls) == 1
        sent = conn.led_calls[0]
        assert sent == {
            "fgbright": 200, "bgbright": 40, "size": 8, "align": 120,
            "direction": "ccw", "bg": "plasma", "color": "FF0040", "color2": "000028",
        }

    def test_clamps_out_of_range(self):
        conn = FakeConn()
        c, ctx = _controller(conn)
        with ctx:
            c.set_ball(size=999, align=400, fgbright=-5, bgbright=500)
        sent = conn.led_calls[0]
        assert sent["size"] == 200      # 1..200
        assert sent["align"] == 359     # 0..359
        assert sent["fgbright"] == 0    # 0..255
        assert sent["bgbright"] == 255  # 0..255

    def test_ignores_invalid_direction(self):
        conn = FakeConn()
        c, ctx = _controller(conn)
        with ctx:
            c.set_ball(direction="sideways", size=5)
        sent = conn.led_calls[0]
        assert "direction" not in sent
        assert sent["size"] == 5

    def test_empty_params_no_call(self):
        conn = FakeConn()
        c, ctx = _controller(conn)
        with ctx:
            result = c.set_ball()
        assert conn.led_calls == []
        assert result == {"connected": True}


class TestStatusBallReadback:
    def test_check_status_exposes_ball(self):
        conn = FakeConn(settings={
            "LED/Effect": "ball",
            "LED/Brightness": "128",
            "LED/BallBright": "111",
            "LED/BallBgBright": "222",
            "LED/BallSize": "17",
            "LED/BallBg": "fire",
            "LED/Direction": "ccw",
            "LED/Align": "88",
        })
        c, ctx = _controller(conn)
        with ctx:
            status = c.check_status()
        assert status["connected"] is True
        assert status["ball"] == {
            "fgbright": 111, "bgbright": 222, "size": 17,
            "bg": "fire", "direction": "ccw", "align": 88,
        }
