"""Tests for Adaptive TTS config and options flows."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_tts.const import (
    CONF_QUIET_END,
    CONF_QUIET_MODE,
    CONF_QUIET_OPTION,
    CONF_QUIET_START,
    CONF_QUIET_VALUE,
    CONF_UNDERLYING_TTS_ENTITY,
    DOMAIN,
)

from .test_tts import MockTTS


@pytest.mark.asyncio
async def test_config_flow_succeeds(hass) -> None:
    """The UI flow creates a config entry."""
    source = MockTTS()
    source.hass = hass
    hass.states.async_set("tts.source", "unknown")
    with (
        patch(
            "custom_components.adaptive_tts.config_flow.get_tts_entity",
            return_value=source,
        ),
        patch(
            "custom_components.adaptive_tts.config_flow.is_adaptive_entity",
            return_value=False,
        ),
        patch(
            "custom_components.adaptive_tts.config_flow.selectable_tts_entities",
            return_value=["tts.source"],
        ),
        patch(
            "homeassistant.config_entries.async_process_deps_reqs",
            new=AsyncMock(),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_NAME: "Bedroom TTS", CONF_UNDERLYING_TTS_ENTITY: "tts.source"},
        )
        assert result["step_id"] == "policy"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_QUIET_MODE: True,
                CONF_QUIET_START: "23:00:00",
                CONF_QUIET_END: "07:00:00",
                CONF_QUIET_OPTION: "voice",
            },
        )
        assert result["step_id"] == "override"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_QUIET_VALUE: "whisper"}
        )
    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Bedroom TTS"
    assert result["data"][CONF_QUIET_VALUE] == "whisper"


@pytest.mark.asyncio
async def test_recursive_provider_is_rejected(hass) -> None:
    """Adaptive TTS cannot select another Adaptive TTS entity."""
    hass.states.async_set("tts.adaptive", "unknown")
    with (
        patch(
            "custom_components.adaptive_tts.config_flow.is_adaptive_entity",
            return_value=True,
        ),
        patch(
            "custom_components.adaptive_tts.config_flow.selectable_tts_entities",
            return_value=[],
        ),
        patch(
            "homeassistant.config_entries.async_process_deps_reqs",
            new=AsyncMock(),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        with pytest.raises(data_entry_flow.InvalidData):
            await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_NAME: "Loop", CONF_UNDERLYING_TTS_ENTITY: "tts.adaptive"},
            )


@pytest.mark.asyncio
async def test_options_flow_updates_provider_and_policy(hass) -> None:
    """Options flow updates the provider and quiet settings."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bedroom TTS",
        data={
            CONF_NAME: "Bedroom TTS",
            CONF_UNDERLYING_TTS_ENTITY: "tts.old",
            CONF_QUIET_MODE: True,
            CONF_QUIET_START: "23:00:00",
            CONF_QUIET_END: "07:00:00",
            CONF_QUIET_OPTION: "voice",
            CONF_QUIET_VALUE: "whisper",
        },
    )
    entry.add_to_hass(hass)
    source = MockTTS()
    source.hass = hass
    hass.states.async_set("tts.new", "unknown")
    with (
        patch(
            "custom_components.adaptive_tts.config_flow.get_tts_entity",
            return_value=source,
        ),
        patch(
            "custom_components.adaptive_tts.config_flow.is_adaptive_entity",
            return_value=False,
        ),
        patch(
            "custom_components.adaptive_tts.config_flow.selectable_tts_entities",
            return_value=["tts.new"],
        ),
        patch(
            "homeassistant.config_entries.async_process_deps_reqs",
            new=AsyncMock(),
        ),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_UNDERLYING_TTS_ENTITY: "tts.new"}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_QUIET_MODE: False,
                CONF_QUIET_START: "22:00:00",
                CONF_QUIET_END: "06:00:00",
                CONF_QUIET_OPTION: "voice",
            },
        )
    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_UNDERLYING_TTS_ENTITY] == "tts.new"
    assert result["data"][CONF_QUIET_MODE] is False
