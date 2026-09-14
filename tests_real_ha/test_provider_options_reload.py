"""Real Home Assistant acceptance test for changing TTS providers."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from homeassistant.components import tts as ha_tts
from homeassistant.components.tts import TextToSpeechEntity
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_tts.const import (
    CONF_UNDERLYING_TTS_ENTITY,
    DATA_ENTITIES,
    DOMAIN,
)
from custom_components.adaptive_tts.routing_entity import RoutedAdaptiveTTSEntity


class SwitchingProvider(TextToSpeechEntity):
    """Controllable provider with provider-specific defaults."""

    _attr_supported_options: ClassVar = ["voice"]

    def __init__(self, name: str, language: str, voice: str) -> None:
        self._attr_name = name
        self._attr_default_language = language
        self._attr_supported_languages = [language]
        self._attr_default_options = {"voice": voice}
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def async_get_tts_audio(self, message, language, options):
        """Record requests and return provider-specific audio."""
        self.calls.append((message, language, dict(options)))
        return "mp3", f"{self.name}:{message}".encode()


async def _synthesise(hass, entity_id: str, message: str) -> bytes:
    """Synthesize one request through Home Assistant's real TTS manager."""
    stream = ha_tts.async_create_stream(hass, entity_id)
    stream.async_set_message(message)
    return b"".join([chunk async for chunk in stream.async_stream_result()])


@pytest.mark.asyncio
async def test_options_flow_switches_provider_and_reloads_live_entity(
    hass, tmp_path
) -> None:
    """Changing provider through HA options reloads Adaptive TTS onto provider B."""
    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, "homeassistant", {}) is True

    provider_a_id = "tts.provider_a"
    provider_b_id = "tts.provider_b"
    provider_a = SwitchingProvider("Provider A", "en-US", "voice-a")
    provider_b = SwitchingProvider("Provider B", "en-GB", "voice-b")
    provider_a.hass = hass
    provider_b.hass = hass
    providers = {provider_a_id: provider_a, provider_b_id: provider_b}

    hass.states.async_set(provider_a_id, "idle")
    hass.states.async_set(provider_b_id, "idle")

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Switching Adaptive TTS",
        data={CONF_UNDERLYING_TTS_ENTITY: provider_a_id},
        version=2,
    )
    entry.add_to_hass(hass)

    def provider_lookup(_hass, entity_id):
        return providers.get(entity_id)

    with patch(
        "custom_components.adaptive_tts.helpers.get_engine_instance",
        side_effect=provider_lookup,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id) is True
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        original_entity = hass.data[DOMAIN][DATA_ENTITIES][entry.entry_id]
        assert isinstance(original_entity, RoutedAdaptiveTTSEntity)
        assert original_entity.entity_id is not None
        entity_id = original_entity.entity_id
        assert original_entity.underlying_entity_id == provider_a_id

        first_audio = await _synthesise(hass, entity_id, "Before switch")

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_UNDERLYING_TTS_ENTITY: provider_b_id},
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        assert entry.options[CONF_UNDERLYING_TTS_ENTITY] == provider_b_id
        reloaded_entity = hass.data[DOMAIN][DATA_ENTITIES][entry.entry_id]
        assert isinstance(reloaded_entity, RoutedAdaptiveTTSEntity)
        assert reloaded_entity is not original_entity
        assert reloaded_entity.entity_id == entity_id
        assert reloaded_entity.underlying_entity_id == provider_b_id

        second_audio = await _synthesise(hass, entity_id, "After switch")

    assert first_audio == b"Provider A:Before switch"
    assert second_audio == b"Provider B:After switch"
    assert provider_a.calls == [("Before switch", "en-US", {"voice": "voice-a"})]
    assert provider_b.calls == [("After switch", "en-GB", {"voice": "voice-b"})]
