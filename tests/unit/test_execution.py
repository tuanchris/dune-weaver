"""
Unit tests for modules/core/execution.py — the firmware-delegation layer.

Covers:
- translate_status: raw /sand_status fixtures -> the /ws/status contract
- BoardObserver edge detection: history logging, hold accounting,
  clear-speed shim, run-end reset, reboot guard
- start_playlist call order (stop-first, NVS params, mirror, run)
- skip routing (playlist vs single pattern)
"""
import json
import pytest
from unittest.mock import MagicMock, patch

from modules.core import execution
from modules.core.execution import BoardObserver, RunContext, map_clear_mode, _from_sd_path, translate_status
from modules.core.state import state


class FakeConn:
    """Records calls; scriptable status."""

    def __init__(self, statuses=None):
        self.calls = []
        self.statuses = list(statuses or [])
        self._stopped = False

    def is_connected(self):
        return True

    def get_status(self):
        self.calls.append(("get_status",))
        if self._stopped:
            return {"state": "Idle", "running": False, "playlist": {"active": False}}
        if self.statuses:
            return self.statuses.pop(0)
        return {"state": "Idle", "running": False, "playlist": {"active": False}}

    def stop(self):
        self.calls.append(("stop",))
        self._stopped = True

    def skip(self):
        self.calls.append(("skip",))

    def pause(self):
        self.calls.append(("pause",))

    def resume(self):
        self.calls.append(("resume",))

    def set_setting(self, key, value):
        self.calls.append(("set_setting", key, str(value)))

    def set_feed(self, mm=None, **kw):
        self.calls.append(("set_feed", mm))

    def run_command(self, plain):
        self.calls.append(("run_command", plain))
        return "ok"

    def run_pattern(self, sd_path, clear=None):
        self.calls.append(("run_pattern", sd_path, clear))

    def file_exists(self, sd_path):
        return True

    def upload_file(self, sd_path, data, directory):
        self.calls.append(("upload_file", sd_path))
        return {}


@pytest.fixture(autouse=True)
def clean_state():
    saved = (state.conn, state.current_playing_file, state.current_playlist,
             state.current_playlist_name, state.speed, state.clear_pattern_speed,
             execution.current_run)
    state.conn = None
    execution.current_run = None
    with patch.object(state, "save"):
        yield
    (state.conn, state.current_playing_file, state.current_playlist,
     state.current_playlist_name, state.speed, state.clear_pattern_speed,
     execution.current_run) = saved


def _status(**over):
    base = {
        "state": "Run", "running": True, "file": "/patterns/star.thr",
        "progress": 0.5, "theta": 1.0, "rho": 0.5, "feed": 500, "uptime": 1000,
        "fw": "v0.1.3",
        "playlist": {"active": False, "index": 0, "total": 0, "name": "",
                     "clearing": False, "quiet": False,
                     "pause_remaining": -1, "pause_total": -1},
    }
    pl_over = over.pop("playlist", {})
    base.update(over)
    base["playlist"].update(pl_over)
    return base


class TestMapping:
    def test_clear_mode_mapping(self):
        assert map_clear_mode("clear_from_in") == "in"
        assert map_clear_mode("clear_from_out") == "out"
        assert map_clear_mode("clear_sideway") == "sideway"
        assert map_clear_mode("adaptive") == "adaptive"
        assert map_clear_mode(None) == "none"
        assert map_clear_mode("bogus") == "none"

    def test_sd_path_mapping(self):
        assert _from_sd_path("/patterns/a/b.thr") == "./patterns/a/b.thr"
        assert _from_sd_path("/sd/patterns/x.thr") == "./patterns/x.thr"
        assert _from_sd_path("") is None

    def test_sd_path_refinds_relocated_pattern(self, tmp_path, monkeypatch):
        # A host custom pattern uploads to SD as 'patterns/<basename>'; the
        # board reports that SD path, and the mapping must re-find the host
        # copy (custom_patterns/...) rather than a path that doesn't exist.
        from modules.core import execution, pattern_manager
        (tmp_path / "custom_patterns").mkdir()
        (tmp_path / "custom_patterns" / "capybara.thr").write_text("0 0\n")
        monkeypatch.setattr(pattern_manager, "THETA_RHO_DIR", str(tmp_path))
        monkeypatch.setattr(execution, "_sd_path_cache", {})
        assert _from_sd_path("/sd/patterns/capybara.thr") == "./patterns/custom_patterns/capybara.thr"
        # Unknown-everywhere paths keep the literal mapping as fallback
        assert _from_sd_path("/sd/patterns/nope.thr") == "./patterns/nope.thr"


class TestTranslateStatus:
    def test_offline(self):
        out = translate_status(None, BoardObserver())
        assert out["connection_status"] is False
        assert out["is_running"] is False
        assert out["playlist"] is None
        assert out["progress"] is None

    def test_running_pattern(self):
        obs = BoardObserver()
        obs.file_started_at = 90.0
        state.conn = FakeConn()
        out = translate_status(_status(progress=0.425), obs, now=100.0)
        assert out["is_running"] is True
        assert out["current_file"] == "./patterns/star.thr"
        assert out["progress"]["percentage"] == 42.5
        assert out["progress"]["elapsed_time"] == pytest.approx(10.0)
        # remaining = elapsed/fraction - elapsed
        assert out["progress"]["remaining_time"] == pytest.approx(10 / 0.425 - 10)
        assert out["is_paused"] is False

    def test_hold_is_paused(self):
        state.conn = FakeConn()
        out = translate_status(_status(state="Hold"), BoardObserver())
        assert out["is_paused"] is True

    def test_hold_substate_is_paused(self):
        # GRBL reports a substate suffix ("Hold:0") that must still read as paused.
        state.conn = FakeConn()
        out = translate_status(_status(state="Hold:0"), BoardObserver())
        assert out["is_paused"] is True

    def test_playlist_pause_countdown(self):
        state.conn = FakeConn()
        execution.current_run = RunContext(kind="playlist", playlist_name="fav",
                                           run_mode="indefinite")
        state.current_playlist = ["./patterns/a.thr", "./patterns/b.thr"]
        out = translate_status(_status(
            running=False, state="Idle", file="",
            playlist={"active": True, "index": 0, "total": 2, "name": "fav",
                      "pause_remaining": 30, "pause_total": 60},
        ), BoardObserver())
        assert out["is_running"] is False
        assert out["pause_time_remaining"] == 30
        assert out["original_pause_time"] == 60
        assert out["playlist"]["name"] == "fav"
        assert out["playlist"]["mode"] == "indefinite"
        assert out["playlist"]["total_files"] == 2
        assert out["playlist"]["next_file"] == "./patterns/b.thr"
        assert out["playlist"]["shuffled"] is False

    def test_playlist_clearing_next_file(self):
        state.conn = FakeConn()
        execution.current_run = RunContext(kind="playlist", playlist_name="fav")
        state.current_playlist = ["./patterns/a.thr", "./patterns/b.thr"]
        out = translate_status(_status(
            playlist={"active": True, "index": 1, "total": 2, "name": "fav",
                      "clearing": True},
        ), BoardObserver())
        # While clearing, "next" is the pattern the clear precedes.
        assert out["playlist"]["next_file"] == "./patterns/b.thr"
        assert out["is_clearing"] is True

    def test_shuffled_playlist_hides_next(self):
        state.conn = FakeConn()
        execution.current_run = RunContext(kind="playlist", playlist_name="fav",
                                           shuffle=True)
        state.current_playlist = ["./patterns/a.thr", "./patterns/b.thr"]
        out = translate_status(_status(
            playlist={"active": True, "index": 0, "total": 2, "name": "fav"},
        ), BoardObserver())
        assert out["playlist"]["shuffled"] is True
        assert out["playlist"]["next_file"] is None
        assert out["playlist"]["files"]  # still served read-only


class TestObserverEdges:
    @pytest.fixture
    def log_file(self, tmp_path):
        path = tmp_path / "execution_times.jsonl"
        with patch("modules.core.pattern_manager.EXECUTION_LOG_FILE", str(path)):
            yield path

    async def test_file_transition_logs_history(self, log_file):
        state.conn = FakeConn()
        obs = BoardObserver()
        await obs.process(_status(file="/patterns/a.thr", progress=0.2), now=0.0)
        await obs.process(_status(file="/patterns/a.thr", progress=0.99), now=100.0)
        await obs.process(_status(file="/patterns/b.thr", progress=0.0), now=110.0)
        rows = [json.loads(l) for l in log_file.read_text().splitlines()]
        assert len(rows) == 1
        assert rows[0]["pattern_name"] == "a.thr"
        assert rows[0]["completed"] is True
        assert state.current_playing_file == "./patterns/b.thr"

    async def test_aborted_run_not_completed(self, log_file):
        state.conn = FakeConn()
        obs = BoardObserver()
        await obs.process(_status(file="/patterns/a.thr", progress=0.3), now=0.0)
        await obs.process(_status(running=False, state="Idle", file=""), now=50.0)
        rows = [json.loads(l) for l in log_file.read_text().splitlines()]
        assert len(rows) == 1
        assert rows[0]["completed"] is False

    async def test_hold_time_excluded(self, log_file):
        state.conn = FakeConn()
        obs = BoardObserver()
        await obs.process(_status(file="/patterns/a.thr"), now=0.0)
        await obs.process(_status(file="/patterns/a.thr", state="Hold"), now=10.0)
        await obs.process(_status(file="/patterns/a.thr", state="Run", progress=0.99), now=40.0)
        await obs.process(_status(running=False, state="Idle", file=""), now=50.0)
        rows = [json.loads(l) for l in log_file.read_text().splitlines()]
        # 50s wall clock minus 30s hold = 20s
        assert rows[0]["actual_time_seconds"] == pytest.approx(20.0, abs=0.5)

    async def test_clear_files_not_logged(self, log_file):
        state.conn = FakeConn()
        obs = BoardObserver()
        await obs.process(_status(file="/patterns/clear_from_in.thr",
                                  playlist={"active": True, "clearing": True, "total": 2}), now=0.0)
        await obs.process(_status(file="/patterns/a.thr",
                                  playlist={"active": True, "total": 2}), now=30.0)
        assert not log_file.exists()

    async def test_clear_speed_shim(self, log_file):
        conn = FakeConn()
        state.conn = conn
        state.speed = 400
        state.clear_pattern_speed = 150
        obs = BoardObserver()
        await obs.process(_status(file="/patterns/clear_from_in.thr",
                                  playlist={"active": True, "clearing": True, "total": 1}), now=0.0)
        assert ("set_feed", 150) in conn.calls
        conn.calls.clear()
        await obs.process(_status(file="/patterns/a.thr",
                                  playlist={"active": True, "total": 1}), now=30.0)
        assert ("set_feed", 400) in conn.calls

    async def test_run_end_resets_state(self, log_file):
        state.conn = FakeConn()
        execution.current_run = RunContext(kind="playlist", playlist_name="fav")
        state.current_playlist = ["./patterns/a.thr"]
        obs = BoardObserver()
        await obs.process(_status(file="/patterns/a.thr",
                                  playlist={"active": True, "total": 1}), now=0.0)
        await obs.process(_status(running=False, state="Idle", file="",
                                  playlist={"active": False}), now=60.0)
        assert execution.current_run is None
        assert state.current_playlist is None
        assert state.current_playing_file is None

    async def test_reboot_guard(self, log_file):
        state.conn = FakeConn()
        obs = BoardObserver()
        await obs.process(_status(file="/patterns/a.thr", uptime=5000), now=0.0)
        await obs.process(_status(running=False, state="Idle", file="", uptime=10), now=10.0)
        # Reboot detected: context reset, no completion logged
        assert not log_file.exists()
        assert obs.prev is not None  # keeps observing after reset


class TestCommands:
    async def test_start_playlist_call_order(self):
        conn = FakeConn(statuses=[{"state": "Run", "running": True, "playlist": {"active": True}}])
        state.conn = conn
        state.speed = 300
        with patch("modules.core.playlist_manager.get_playlist",
                   return_value={"name": "fav", "files": ["patterns/a.thr", "patterns/b.thr"]}), \
             patch("modules.core.pattern_manager._ensure_on_board"):
            await execution.start_playlist("fav", run_mode="indefinite", pause_time=30,
                                           clear_pattern="clear_from_in", shuffle=True)

        names = [c[0] for c in conn.calls]
        # stop-first (board was running), then NVS params, mirror, run
        assert names.index("stop") < names.index("set_setting")
        settings = [(c[1], c[2]) for c in conn.calls if c[0] == "set_setting"]
        assert ("Playlist/Mode", "loop") in settings
        assert ("Playlist/Shuffle", "ON") in settings
        assert ("Playlist/PauseTime", "30") in settings
        assert ("Playlist/ClearPattern", "in") in settings
        assert ("upload_file", "/playlists/fav.txt") in conn.calls
        assert ("run_command", "$Playlist/Run=fav") in conn.calls
        assert conn.calls.index(("upload_file", "/playlists/fav.txt")) < \
               conn.calls.index(("run_command", "$Playlist/Run=fav"))
        assert execution.current_run.kind == "playlist"
        assert state.current_playlist_name == "fav"

    async def test_start_playlist_empty_raises(self):
        state.conn = FakeConn()
        with patch("modules.core.playlist_manager.get_playlist",
                   return_value={"name": "e", "files": []}):
            with pytest.raises(execution.ExecutionError):
                await execution.start_playlist("e")

    async def test_skip_routes_playlist_vs_single(self):
        conn = FakeConn()
        state.conn = conn
        execution.observer.last_raw = _status(playlist={"active": True, "total": 2})
        assert await execution.skip() is True
        assert ("skip",) in conn.calls
        conn.calls.clear()
        execution.observer.last_raw = _status()  # single pattern running
        assert await execution.skip() is True
        assert ("stop",) in conn.calls
        conn.calls.clear()
        execution.observer.last_raw = _status(running=False, state="Idle")
        assert await execution.skip() is False

    async def test_run_pattern_uses_sand_run(self):
        conn = FakeConn()
        state.conn = conn
        state.speed = 250
        with patch("modules.core.pattern_manager._ensure_on_board"):
            await execution.run_pattern("./patterns/star.thr", "adaptive")
        assert ("run_pattern", "/patterns/star.thr", "adaptive") in conn.calls
        assert execution.current_run.kind == "pattern"

    async def test_force_stop_resets_even_on_error(self):
        conn = FakeConn()
        conn.stop = MagicMock(side_effect=RuntimeError("boom"))
        state.conn = conn
        state.current_playing_file = "./patterns/a.thr"
        execution.current_run = RunContext(kind="pattern")
        assert await execution.stop(force=True) is True
        assert execution.current_run is None
        assert state.current_playing_file is None
