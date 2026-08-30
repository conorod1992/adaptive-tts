"""Tests for integration setup safeguards."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import ConfigEntryError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_tts import async_setup_entry
from custom_components.adaptive_tts.const import (
    CONF_QUIET_END,
    CONF_QUIET_MODE,
    CONF_QUIET_OPTION,
    CONF_QUIET_START,
    CONF_QUIET_VALUE,
    CONF_UNDERLYING_TTS_ENTITY,
    DATA_ENTITIES,
    DOMAIN,
)


def _entry(provider: str) -> MockConfigEntry:
    """Create a minimal Adaptive TTS config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_UNDERLYING_TTS_ENTITY: provider,
            CONF_QUIET_MODE: False,
            CONF_QUIET_START: "23:00:00",
            CONF_QUIET_END: "07:00:00",
            CONF_QUIET_OPTION: "voice",
            CONF_QUIET_VALUE: "",
        },
    )


@pytest.mark.asyncio
async def test_runtime_recursive_configuration_is_rejected(hass) -> None:
    """Stored recursive configurations cannot bypass config-flow validation."""
    entry = _entry("tts.other_adaptive_tts")
    with (
        patch("custom_components.adaptive_tts.is_adaptive_entity", return_value=True),
        pytest.raises(ConfigEntryError, match="cannot wrap"),
    ):
        await async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_underlying_state_change_refreshes_wrapper_state(hass) -> None:
    """A provider state change republishes the non-polling wrapper state."""
    entry = _entry("tts.source")
    entry.add_to_hass(hass)
    wrapper = Mock()
    hass.data.setdefault(DOMAIN, {})[DATA_ENTITIES] = {entry.entry_id: wrapper}
    captured = {}
    remove_listener = Mock()

    def track_state_change(_hass, entity_id, action):
        captured["entity_id"] = entity_id
        captured["action"] = action
        return remove_listener

    with (
        patch("custom_components.adaptive_tts.is_adaptive_entity", return_value=False),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.adaptive_tts.async_track_state_change_event",
            side_effect=track_state_change,
        ),
    ):
        assert await async_setup_entry(hass, entry) is True

    assert captured["entity_id"] == "tts.source"
    captured["action"](None)
    wrapper.async_write_ha_state.assert_called_once_with()
