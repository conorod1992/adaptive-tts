"""Real Home Assistant acceptance test for the TTS request path."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from homeassistant.components import tts as ha_tts
from homeassistant.components.tts import TextToSpeechEntity
from homeassistant.config_entries import ConfigEntryState
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_tts.const import (
    CONF_UNDERLYING_TTS_ENTITY,
    DATA_ENTITIES,
    DOMAIN,
)
from custom_components.adaptive_tts.routing_entity import RoutedAdaptiveTTSEntity


class RequestTTSProvider(TextToSpeechEntity):
    """Controllable provider behind a fully loaded Adaptive TTS entity."""

    _attr_name = "Request provider"
    _attr_default_language = "en-US"
    _attr_supported_languages: ClassVar = ["en-US"]
    _attr_supported_options: ClassVar = ["voice"]
    _attr_default_options: ClassVar = {"voice": "normal"}

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def async_get_tts_audio(self, message, language, options):
        """Record the provider request and return deterministic audio."""
        self.calls.append((message, language, dict(options)))
        return "mp3", b"real-ha-adaptive-audio"


@pytest.mark.asyncio
async def test_real_ha_manager_routes_request_through_loaded_adaptive_entity(
    hass, tmp_path
) -> None:
    """HA's TTS manager reaches the provider through the loaded Adaptive entity."""
    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, "homeassistant", {}) is True

    provider_entity_id = "tts.request_provider"
    provider = RequestTTSProvider()
    provider.hass = hass

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Request Adaptive TTS",
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

        manager_entity = ha_tts.get_engine_instance(hass, entity.entity_id)
        assert manager_entity is entity

        stream = ha_tts.async_create_stream(
            hass,
            entity.entity_id,
            language="en-US",
            options={"voice": "acceptance"},
        )
        stream.async_set_message("Real HA request")
        audio = b"".join([chunk async for chunk in stream.async_stream_result()])

    assert stream.extension == "mp3"
    assert audio == b"real-ha-adaptive-audio"
    assert provider.calls == [
        ("Real HA request", "en-US", {"voice": "acceptance"})
    ]
