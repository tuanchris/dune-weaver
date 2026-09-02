"""
Unit tests for LED effect option resolution.

Covers ``_resolve_effect_settings`` and the no-immediate-repeat rule that keeps
the previously picked option out of the next draw for a given slot.
"""
import pytest
from unittest.mock import MagicMock

from modules.led import dw_led_controller as led


def _opt(effect_id):
    return {
        "effect_id": effect_id,
        "palette_id": 3,
        "speed": 100,
        "intensity": 120,
        "color1": "#ff0000",
        "color2": "#000000",
        "color3": "#0000ff",
    }


@pytest.fixture(autouse=True)
def clear_history():
    """Each test starts with no previous pick recorded."""
    led._reset_effect_choice_history()
    yield
    led._reset_effect_choice_history()


def test_single_dict_is_passed_through():
    settings = _opt(4)
    assert led._resolve_effect_settings(settings, slot="idle") is settings


def test_non_dict_input_resolves_to_none():
    assert led._resolve_effect_settings(None, slot="idle") is None
    assert led._resolve_effect_settings("nonsense", slot="idle") is None
    assert led._resolve_effect_settings([], slot="idle") is None
    assert led._resolve_effect_settings(["nonsense", 7], slot="idle") is None


def test_never_repeats_the_previous_option():
    options = [_opt(1), _opt(2), _opt(3)]

    previous = None
    for _ in range(60):
        choice = led._resolve_effect_settings(options, slot="playing")
        assert choice in options
        assert choice != previous, "the same option came up twice in a row"
        previous = choice


def test_single_option_still_resolves_every_time():
    options = [_opt(5)]

    for _ in range(5):
        assert led._resolve_effect_settings(options, slot="idle") == _opt(5)


def test_identical_options_fall_back_to_the_full_pool():
    """All options equal to the last pick -> pool is reused rather than emptied."""
    options = [_opt(6), _opt(6)]

    for _ in range(5):
        assert led._resolve_effect_settings(options, slot="idle") == _opt(6)


def test_slots_keep_separate_history():
    options = [_opt(1), _opt(2)]

    idle_first = led._resolve_effect_settings(options, slot="idle")
    playing_first = led._resolve_effect_settings(options, slot="playing")

    # "playing" has its own history, so it may legitimately match idle's pick.
    assert playing_first in options

    # Each slot only avoids repeating its own last choice.
    assert led._resolve_effect_settings(options, slot="idle") != idle_first
    assert led._resolve_effect_settings(options, slot="playing") != playing_first


def test_no_slot_records_no_history():
    options = [_opt(1), _opt(2)]

    for _ in range(5):
        assert led._resolve_effect_settings(options) in options

    assert led._last_effect_choice == {}


def test_effect_playing_rerolls_without_repeating():
    controller = MagicMock()
    options = [_opt(1), _opt(2)]

    applied = []
    for _ in range(6):
        controller.set_effect.reset_mock()
        assert led.effect_playing(controller, options) is True
        applied.append(controller.set_effect.call_args.args[0])

    assert set(applied) == {1, 2}
    assert all(a != b for a, b in zip(applied, applied[1:]))


def test_effect_idle_rerolls_without_repeating():
    controller = MagicMock()
    options = [_opt(1), _opt(2)]

    applied = []
    for _ in range(6):
        controller.set_effect.reset_mock()
        assert led.effect_idle(controller, options) is True
        applied.append(controller.set_effect.call_args.args[0])

    assert set(applied) == {1, 2}
    assert all(a != b for a, b in zip(applied, applied[1:]))
