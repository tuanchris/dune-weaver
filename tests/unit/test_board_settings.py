"""
Unit tests for board_settings — the host<->board settings sync layer.

Covers:
- Still Sands slot conversion (host dicts <-> $Sands/Slots spec string)
- POSIX timezone derivation from TZif files
- Adopting board $Sands/* values into host state
- Autostart mapping to $Playlist/Autostart* commands
- Playlist mirroring content
"""
import pytest
from unittest.mock import MagicMock, patch

from modules.core import board_settings
from modules.core.state import state


class TestSlotConversion:
    """Host slot dicts <-> firmware '$Sands/Slots' spec string."""

    def test_daily_slot_round_trip(self):
        slots = [{"start_time": "22:00", "end_time": "06:00", "days": "daily", "custom_days": []}]
        spec = board_settings.slots_to_board(slots)
        assert spec == "22:00-06:00@daily"
        assert board_settings.board_to_slots(spec) == slots

    def test_weekdays_and_weekends(self):
        slots = [
            {"start_time": "21:00", "end_time": "08:00", "days": "weekdays", "custom_days": []},
            {"start_time": "23:30", "end_time": "09:00", "days": "weekends", "custom_days": []},
        ]
        spec = board_settings.slots_to_board(slots)
        assert spec == "21:00-08:00@weekdays,23:30-09:00@weekends"
        assert board_settings.board_to_slots(spec) == slots

    def test_custom_days_round_trip(self):
        slots = [{
            "start_time": "13:00", "end_time": "14:00", "days": "custom",
            "custom_days": ["monday", "friday"],
        }]
        spec = board_settings.slots_to_board(slots)
        assert spec == "13:00-14:00@mon+fri"
        assert board_settings.board_to_slots(spec) == slots

    def test_custom_days_sorted_in_firmware_order(self):
        slots = [{
            "start_time": "10:00", "end_time": "11:00", "days": "custom",
            "custom_days": ["saturday", "sunday", "wednesday"],
        }]
        # bit 0 = Sunday in the firmware's day order
        assert board_settings.slots_to_board(slots) == "10:00-11:00@sun+wed+sat"

    def test_empty_custom_days_falls_back_to_daily(self):
        slots = [{"start_time": "10:00", "end_time": "11:00", "days": "custom", "custom_days": []}]
        assert board_settings.slots_to_board(slots) == "10:00-11:00@daily"

    def test_parse_ignores_malformed_entries(self):
        parsed = board_settings.board_to_slots("garbage,22:00-06:00@daily,also-bad@")
        assert len(parsed) == 1
        assert parsed[0]["start_time"] == "22:00"

    def test_parse_bare_times_defaults_daily(self):
        parsed = board_settings.board_to_slots("22:00-06:00")
        assert parsed == [{"start_time": "22:00", "end_time": "06:00", "days": "daily", "custom_days": []}]

    def test_empty_specs(self):
        assert board_settings.slots_to_board([]) == ""
        assert board_settings.board_to_slots("") == []


class TestPosixTz:
    def test_known_iana_zone(self):
        # Skip if the zoneinfo database isn't at the standard path.
        import os
        if not os.path.exists("/usr/share/zoneinfo/America/Toronto"):
            pytest.skip("no system zoneinfo db")
        tz = board_settings.posix_tz("America/Toronto")
        assert tz is not None and tz.startswith("EST5EDT")

    def test_unknown_zone_returns_none(self):
        assert board_settings.posix_tz("Not/AZone") is None


class TestAdoptStillSands:
    @pytest.fixture(autouse=True)
    def _snapshot_state(self):
        saved = (
            state.scheduled_pause_enabled,
            state.scheduled_pause_time_slots,
            state.scheduled_pause_control_wled,
            state.scheduled_pause_finish_pattern,
        )
        yield
        (
            state.scheduled_pause_enabled,
            state.scheduled_pause_time_slots,
            state.scheduled_pause_control_wled,
            state.scheduled_pause_finish_pattern,
        ) = saved

    def test_adopts_board_values(self):
        state.scheduled_pause_enabled = False
        state.scheduled_pause_time_slots = []
        state.scheduled_pause_control_wled = False
        state.scheduled_pause_finish_pattern = False
        with patch.object(state, "save") as save:
            changed = board_settings.adopt_still_sands({
                "Sands/Enabled": "ON",
                "Sands/Slots": "21:00-08:00@daily",
                "Sands/FinishPattern": "OFF",
                "Sands/LedOff": "ON",
            })
        assert changed is True
        save.assert_called_once()
        assert state.scheduled_pause_enabled is True
        assert state.scheduled_pause_finish_pattern is False
        assert state.scheduled_pause_control_wled is True
        assert state.scheduled_pause_time_slots[0]["start_time"] == "21:00"

    def test_no_change_no_save(self):
        state.scheduled_pause_enabled = True
        state.scheduled_pause_finish_pattern = True
        state.scheduled_pause_control_wled = False
        state.scheduled_pause_time_slots = board_settings.board_to_slots("21:00-08:00@daily")
        with patch.object(state, "save") as save:
            changed = board_settings.adopt_still_sands({
                "Sands/Enabled": "ON",
                "Sands/Slots": "21:00-08:00@daily",
                "Sands/FinishPattern": "ON",
                "Sands/LedOff": "OFF",
            })
        assert changed is False
        save.assert_not_called()


class TestApplyAutostart:
    def test_maps_fields_to_board_settings(self):
        conn = MagicMock()
        board_settings.apply_autostart({
            "playlist": "evening",
            "run_mode": "loop",
            "shuffle": True,
            "pause_seconds": 90,
            "pause_from_start": False,
            "clear_pattern": "adaptive",
        }, conn=conn)
        written = {call.args[0]: call.args[1] for call in conn.set_setting.call_args_list}
        assert written == {
            "Playlist/Autostart": "evening",
            "Playlist/AutostartMode": "loop",
            "Playlist/AutostartShuffle": "ON",
            "Playlist/AutostartPause": 90,
            "Playlist/AutostartPauseFromStart": "OFF",
            "Playlist/AutostartClear": "adaptive",
        }

    def test_empty_playlist_disables(self):
        conn = MagicMock()
        board_settings.apply_autostart({"playlist": ""}, conn=conn)
        conn.set_setting.assert_called_once_with("Playlist/Autostart", "")

    def test_invalid_clear_mode_coerced_to_none(self):
        conn = MagicMock()
        board_settings.apply_autostart({"clear_pattern": "clear_from_in"}, conn=conn)
        conn.set_setting.assert_called_once_with("Playlist/AutostartClear", "none")


class TestPlaylistMirroring:
    def test_playlist_content_uses_sd_paths(self):
        from modules.core.pattern_manager import _to_sd_path
        content = board_settings._playlist_sd_content(
            ["./patterns/star.thr", "patterns/sub/wave.thr"], _to_sd_path
        )
        assert content == "/patterns/star.thr\n/patterns/sub/wave.thr\n"

    def test_mirror_uploads_txt(self):
        conn = MagicMock()
        board_settings.mirror_playlist("evening", ["./patterns/star.thr"], conn=conn)
        conn.upload_file.assert_called_once()
        sd_path, data, directory = conn.upload_file.call_args.args
        assert sd_path == "/playlists/evening.txt"
        assert data == b"/patterns/star.thr\n"
        assert directory == "/playlists"
