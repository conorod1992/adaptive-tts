"""Real Home Assistant acceptance test for one-shot voice overrides."""

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
    DURATION_NEXT_REQUEST,
    SERVICE_SET_VOICE_OVERRIDE,
)
from custom_components.adaptive_tts.routing_entity import RoutedAdaptiveTTSEntity


class NextRequestProvider(TextToSpeechEntity):
    """Controllable provider for next-request override acceptance coverage."""

    _attr_name = "Next-request provider"
    _attr_default_language = "en-US"
    _attr_supported_languages: ClassVar = ["en-US", "en-GB"]
    _attr_supported_options: ClassVar = ["voice"]
    _attr_default_options: ClassVar = {"voice": "normal"}

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def async_get_tts_audio(self, message, language, options):
        """Record provider requests and return deterministic audio."""
        self.calls.append((message, language, dict(options)))
        return "mp3", f"audio:{message}".encode()


@pytest.mark.asyncio
async def test_next_request_override_is_consumed_by_one_real_ha_tts_request(
    hass, tmp_path
) -> None:
    """A one-shot override affects exactly one request through HA's TTS manager."""
    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, "homeassistant", {}) is True

    provider_entity_id = "tts.next_request_provider"
    provider = NextRequestProvider()
    provider.hass = hass

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Next-request Adaptive TTS",
        data={CONF_UNDERLYING_TTS_ENTITY: provider_entity_id},
        version=2,
    )
    entry.add_to_hass(hass)

    def provider_lookup(_hass, entity_id):
        return provider if entity_id == provider_entity_id else None

    with patch(
        "custom_components.adaptive_tts.helpers.get_engine_instance",
        side_effect=provider_lookup,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id) is True
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        entity = hass.data[DOMAIN][DATA_ENTITIES][entry.entry_id]
        assert isinstance(entity, RoutedAdaptiveTTSEntity)
        assert entity.entity_id is not None

        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_VOICE_OVERRIDE,
            {
                ATTR_ENTITY_ID: [entity.entity_id],
                ATTR_LANGUAGE: "en-GB",
                ATTR_VOICE: "one-shot-voice",
                ATTR_DURATION: DURATION_NEXT_REQUEST,
            },
            blocking=True,
        )

        assert entity.next_voice_override is not None
        assert entity.next_voice_override.language == "en-GB"
        assert entity.next_voice_override.voice == "one-shot-voice"

        first_stream = ha_tts.async_create_stream(hass, entity.entity_id)
        first_stream.async_set_message("First request")
        first_audio = b"".join(
            [chunk async for chunk in first_stream.async_stream_result()]
        )

        assert entity.next_voice_override is None

        second_stream = ha_tts.async_create_stream(hass, entity.entity_id)
        second_stream.async_set_message("Second request")
        second_audio = b"".join(
            [chunk async for chunk in second_stream.async_stream_result()]
        )

    assert first_stream.extension == "mp3"
    assert second_stream.extension == "mp3"
    assert first_audio == b"audio:First request"
    assert second_audio == b"audio:Second request"
    assert provider.calls == [
        ("First request", "en-GB", {"voice": "one-shot-voice"}),
        ("Second request", "en-US", {"voice": "normal"}),
    ]
