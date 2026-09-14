"""Real Home Assistant acceptance test for multiple Adaptive TTS entries."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from homeassistant.components import tts as ha_tts
from homeassistant.components.tts import TextToSpeechEntity
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_tts.const import (
    ATTR_DURATION,
    ATTR_LANGUAGE,
    ATTR_VOICE,
    CONF_UNDERLYING_TTS_ENTITY,
    DATA_ENTITIES,
    DOMAIN,
    DURATION_UNTIL_CHANGED,
    SERVICE_SET_VOICE_OVERRIDE,
)
from custom_components.adaptive_tts.routing_entity import RoutedAdaptiveTTSEntity


class IsolatedProvider(TextToSpeechEntity):
    """Provider with distinct defaults and call recording."""

    _attr_supported_languages: ClassVar = ["en-US", "en-GB"]
    _attr_supported_options: ClassVar = ["voice"]

    def __init__(self, name: str, language: str, voice: str, marker: bytes) -> None:
        self._attr_name = name
        self._attr_default_language = language
        self._attr_default_options = {"voice": voice}
        self.marker = marker
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def async_get_tts_audio(self, message, language, options):
        """Record requests and return provider-specific deterministic audio."""
        self.calls.append((message, language, dict(options)))
        return "mp3", self.marker + b":" + message.encode()


@pytest.mark.asyncio
async def test_two_loaded_entries_keep_provider_and_override_state_isolated(
    hass, tmp_path
) -> None:
    """Two live Adaptive TTS entries must not leak runtime state across entries."""
    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, "homeassistant", {}) is True

    provider_a_id = "tts.isolated_provider_a"
    provider_b_id = "tts.isolated_provider_b"
    provider_a = IsolatedProvider("Provider A", "en-US", "a-default", b"A")
    provider_b = IsolatedProvider("Provider B", "en-GB", "b-default", b"B")
    provider_a.hass = hass
    provider_b.hass = hass

    entry_a = MockConfigEntry(
        domain=DOMAIN,
        title="Adaptive A",
        data={CONF_UNDERLYING_TTS_ENTITY: provider_a_id},
        version=2,
    )
    entry_b = MockConfigEntry(
        domain=DOMAIN,
        title="Adaptive B",
        data={CONF_UNDERLYING_TTS_ENTITY: provider_b_id},
        version=2,
    )
    entry_a.add_to_hass(hass)
    entry_b.add_to_hass(hass)

    def provider_lookup(_hass, entity_id):
        return {provider_a_id: provider_a, provider_b_id: provider_b}.get(entity_id)

    with patch(
        "custom_components.adaptive_tts.helpers.get_engine_instance",
        side_effect=provider_lookup,
    ):
        assert await hass.config_entries.async_setup(entry_a.entry_id) is True
        await hass.async_block_till_done()
        if entry_b.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(entry_b.entry_id) is True
            await hass.async_block_till_done()

        assert entry_a.state is ConfigEntryState.LOADED
        assert entry_b.state is ConfigEntryState.LOADED
        entity_a = hass.data[DOMAIN][DATA_ENTITIES][entry_a.entry_id]
        entity_b = hass.data[DOMAIN][DATA_ENTITIES][entry_b.entry_id]
        assert isinstance(entity_a, RoutedAdaptiveTTSEntity)
        assert isinstance(entity_b, RoutedAdaptiveTTSEntity)
        assert entity_a is not entity_b
        assert entity_a.entity_id is not None
        assert entity_b.entity_id is not None
        assert entity_a.entity_id != entity_b.entity_id
        assert entity_a.underlying_entity_id == provider_a_id
        assert entity_b.underlying_entity_id == provider_b_id

        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_VOICE_OVERRIDE,
            {
                ATTR_ENTITY_ID: [entity_a.entity_id],
                ATTR_LANGUAGE: "en-US",
                ATTR_VOICE: "a-manual",
                ATTR_DURATION: DURATION_UNTIL_CHANGED,
            },
            blocking=True,
        )

        assert entity_a.persistent_voice_override is not None
        assert entity_a.persistent_voice_override.voice == "a-manual"
        assert entity_b.persistent_voice_override is None

        stream_a = ha_tts.async_create_stream(hass, entity_a.entity_id)
        stream_a.async_set_message("Request A")
        audio_a = b"".join([chunk async for chunk in stream_a.async_stream_result()])

        stream_b = ha_tts.async_create_stream(hass, entity_b.entity_id)
        stream_b.async_set_message("Request B")
        audio_b = b"".join([chunk async for chunk in stream_b.async_stream_result()])

    assert stream_a.extension == "mp3"
    assert stream_b.extension == "mp3"
    assert audio_a == b"A:Request A"
    assert audio_b == b"B:Request B"
    assert provider_a.calls == [("Request A", "en-US", {"voice": "a-manual"})]
    assert provider_b.calls == [("Request B", "en-GB", {"voice": "b-default"})]
