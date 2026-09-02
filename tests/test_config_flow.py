"""Tests for Adaptive TTS config and options flows."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_tts.const import (
    CONF_UNDERLYING_TTS_ENTITY,
    DOMAIN,
)

from .test_tts import MockTTS


@pytest.mark.asyncio
async def test_config_flow_succeeds_without_quiet_hours_step(hass) -> None:
    """The UI creates a wrapper after selecting only its name and provider."""
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

    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Bedroom TTS"
    assert result["data"] == {
        CONF_NAME: "Bedroom TTS",
        CONF_UNDERLYING_TTS_ENTITY: "tts.source",
    }


@pytest.mark.asyncio
async def test_config_flow_rejects_missing_provider(hass) -> None:
    """The setup flow does not create a wrapper for a missing TTS entity."""
    hass.states.async_set("tts.source", "unknown")
    with (
        patch(
            "custom_components.adaptive_tts.config_flow.get_tts_entity",
            return_value=None,
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
            {
                CONF_NAME: "Bedroom TTS",
                CONF_UNDERLYING_TTS_ENTITY: "tts.source",
            },
        )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {CONF_UNDERLYING_TTS_ENTITY: "provider_not_found"}


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
async def test_options_flow_updates_only_provider(hass) -> None:
    """Configure changes the wrapped TTS provider without policy settings."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bedroom TTS",
        data={
            CONF_NAME: "Bedroom TTS",
            CONF_UNDERLYING_TTS_ENTITY: "tts.old",
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

    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_UNDERLYING_TTS_ENTITY: "tts.new"}
