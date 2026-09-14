"""Tests for live Conditional Voice Routing checks."""

import pytest
import voluptuous as vol

from custom_components.adaptive_tts.routing_test import _test_condition_list


@pytest.mark.asyncio
async def test_live_condition_test_uses_current_ha_state_and_unloads(hass) -> None:
    """Unsaved native conditions are evaluated against current HA state."""
    hass.states.async_set("input_boolean.route", "on")
    matched, checkers = await _test_condition_list(
        hass,
        [
            {
                "condition": "state",
                "entity_id": "input_boolean.route",
                "state": "on",
            }
        ],
    )

    try:
        assert matched is True
    finally:
        for checker in checkers:
            checker.async_unload()


@pytest.mark.asyncio
async def test_live_condition_test_rejects_empty_conditions(hass) -> None:
    """A rule with no conditions gets an actionable validation error."""
    with pytest.raises(vol.Invalid, match="Add at least one condition"):
        await _test_condition_list(hass, [])
