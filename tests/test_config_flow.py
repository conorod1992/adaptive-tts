"""Tests for Adaptive TTS config and options flows."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.components.tts import Voice
from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_tts.config_flow import (
    _override_error,
    _override_selector,
)
from custom_components.adaptive_tts.const import (
    CONF_QUIET_END,
    CONF_QUIET_LANGUAGE,
    CONF_QUIET_MODE,
    CONF_QUIET_OPTION,
    CONF_QUIET_START,
    CONF_QUIET_VALUE,
    CONF_UNDERLYING_TTS_ENTITY,
    DOMAIN,
)

from .test_tts import MockTTS


def test_voice_override_uses_selected_language() -> None:
    """Enumerable voices come from the explicitly selected quiet language."""
    source = MockTTS()
    source.async_get_supported_voices = lambda language: (
        [Voice("british", "British Whisper")]
        if language == "en-GB"
        else [Voice("american", "American Whisper")]
    )
    voice_selector = _override_selector(source, "voice", "en-GB")
    assert isinstance(voice_selector, selector.SelectSelector)
    assert voice_selector.config["options"] == [
        {"value": "british", "label": "British Whisper"}
    ]
    assert voice_selector.config["custom_value"] is False


def test_override_falls_back_to_text_without_enumerated_voices() -> None:
    """Non-enumerable voices and non-voice options remain free text."""
    source = MockTTS()
    source.async_get_supported_voices = lambda language: None
    assert isinstance(
        _override_selector(source, "voice", "en-GB"), selector.TextSelector
    )
    assert _override_error(source, "voice", "en-GB", "provider-specific") is None
    assert isinstance(_override_selector(MockTTS(), "style"), selector.TextSelector)


def test_empty_voice_list_rejects_arbitrary_voice() -> None:
    """An explicit empty voice list means no voice IDs are valid."""
    source = MockTTS()
    source.async_get_supported_voices = lambda language: []
    assert _override_error(source, "voice", "en-GB", "made-up") == "unsupported_voice"


@pytest.mark.asyncio
async def test_config_flow_succeeds(hass) -> None:
    """The UI flow selects quiet language before quiet voice."""
    source = MockTTS()
    source.hass = hass
    source.async_get_supported_voices = lambda language: (
        [Voice("british", "British Whisper")]
        if language == "en-GB"
        else [Voice("normal", "Normal")]
    )
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
        assert result["step_id"] == "language"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_QUIET_LANGUAGE: "en-GB"}
        )
        assert result["step_id"] == "override"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_QUIET_VALUE: "british"}
        )
    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Bedroom TTS"
    assert result["data"][CONF_QUIET_LANGUAGE] == "en-GB"
    assert result["data"][CONF_QUIET_VALUE] == "british"


@pytest.mark.asyncio
async def test_config_flow_rejects_voice_not_in_enumerated_list(hass) -> None:
    """A provider-supplied finite voice list is authoritative."""
    source = MockTTS()
    source.hass = hass
    source.async_get_supported_voices = lambda language: [Voice("valid", "Valid")]
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
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_QUIET_MODE: True,
                CONF_QUIET_START: "23:00:00",
                CONF_QUIET_END: "07:00:00",
                CONF_QUIET_OPTION: "voice",
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_QUIET_LANGUAGE: "en-US"}
        )
        with pytest.raises(data_entry_flow.InvalidData):
            await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_QUIET_VALUE: "stale"}
            )


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
            CONF_QUIET_LANGUAGE: "en-GB",
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
    assert CONF_QUIET_LANGUAGE not in result["data"]