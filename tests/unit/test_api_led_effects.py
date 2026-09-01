"""
Unit tests for the multi-option LED effect automation endpoints.

Tests the following endpoints:
- POST /api/dw_leds/save_effect_settings
- POST /api/dw_leds/remove_effect_option
- GET  /api/dw_leds/get_effect_settings
- PATCH /api/settings (led.dw_led.*_effect)
"""
import pytest
from unittest.mock import patch, MagicMock


def _payload(effect_type, effect_id, **extra):
    body = {
        "type": effect_type,
        "effect_id": effect_id,
        "palette_id": 3,
        "speed": 100,
        "intensity": 120,
        "color1": "#ff0000",
        "color2": "#000000",
        "color3": "#0000ff",
    }
    body.update(extra)
    return body


@pytest.mark.asyncio
async def test_save_then_append_and_remove(async_client, mock_state):
    mock_state.dw_led_playing_effect = None
    mock_state.save = MagicMock()

    with patch("main.state", mock_state):
        # First save (no append) replaces -> list of one
        r = await async_client.post("/api/dw_leds/save_effect_settings", json=_payload("playing", 1))
        assert r.status_code == 200, r.text
        assert len(mock_state.dw_led_playing_effect) == 1

        # Append two more
        for eid in (2, 3):
            r = await async_client.post("/api/dw_leds/save_effect_settings", json=_payload("playing", eid, append=True))
            assert r.status_code == 200, r.text
        assert [o["effect_id"] for o in mock_state.dw_led_playing_effect] == [1, 2, 3]

        # get_effect_settings returns the list
        r = await async_client.get("/api/dw_leds/get_effect_settings")
        assert len(r.json()["playing_effect"]) == 3

        # Remove the middle one
        r = await async_client.post("/api/dw_leds/remove_effect_option", json={"type": "playing", "index": 1})
        assert r.status_code == 200, r.text
        assert [o["effect_id"] for o in mock_state.dw_led_playing_effect] == [1, 3]

        # Removing the last remaining options clears the config back to None
        await async_client.post("/api/dw_leds/remove_effect_option", json={"type": "playing", "index": 0})
        await async_client.post("/api/dw_leds/remove_effect_option", json={"type": "playing", "index": 0})
        assert mock_state.dw_led_playing_effect is None


@pytest.mark.asyncio
async def test_append_migrates_legacy_single_dict(async_client, mock_state):
    mock_state.dw_led_idle_effect = {"effect_id": 9, "palette_id": 0, "speed": 60,
                                     "intensity": 128, "color1": "#ffffff",
                                     "color2": "#000000", "color3": "#0000ff"}
    mock_state.save = MagicMock()

    with patch("main.state", mock_state):
        r = await async_client.post("/api/dw_leds/save_effect_settings", json=_payload("idle", 4, append=True))
        assert r.status_code == 200, r.text
        assert [o["effect_id"] for o in mock_state.dw_led_idle_effect] == [9, 4]


@pytest.mark.asyncio
async def test_option_cap_and_bad_input(async_client, mock_state):
    from main import MAX_LED_EFFECT_OPTIONS
    mock_state.dw_led_idle_effect = [_payload("idle", i) for i in range(MAX_LED_EFFECT_OPTIONS)]
    mock_state.save = MagicMock()

    with patch("main.state", mock_state):
        r = await async_client.post("/api/dw_leds/save_effect_settings", json=_payload("idle", 999, append=True))
        assert r.status_code == 400
        assert str(MAX_LED_EFFECT_OPTIONS) in r.json()["detail"]

        r = await async_client.post("/api/dw_leds/save_effect_settings", json=_payload("bogus", 1))
        assert r.status_code == 400

        r = await async_client.post("/api/dw_leds/remove_effect_option", json={"type": "idle", "index": 500})
        assert r.status_code == 400

        r = await async_client.post("/api/dw_leds/remove_effect_option", json={"type": "idle", "index": "x"})
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_settings_patch_accepts_list(async_client, mock_state):
    mock_state.save = MagicMock()
    options = [_payload("playing", 1), _payload("playing", 2)]
    for o in options:
        o.pop("type")

    with patch("main.state", mock_state):
        r = await async_client.patch("/api/settings", json={"led": {"dw_led": {"playing_effect": options}}})
        assert r.status_code == 200, r.text
        assert len(mock_state.dw_led_playing_effect) == 2
