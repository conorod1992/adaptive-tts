"""Real Home Assistant acceptance test for provider disappearance and recovery."""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from homeassistant.components import tts as ha_tts
from homeassistant.components.tts import TextToSpeechEntity
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_tts.const import (
    CONF_UNDERLYING_TTS_ENTITY,
    DATA_ENTITIES,
    DOMAIN,
)
from custom_components.adaptive_tts.routing_entity import RoutedAdaptiveTTSEntity


class RecoveringProvider(TextToSpeechEntity):
    """Controllable provider that can disappear from Adaptive TTS lookup."""

    _attr_name = "Recovering provider"
    _attr_default_language = "en-US"
    _attr_supported_languages: ClassVar = ["en-US"]
    _attr_supported_options: ClassVar = ["voice"]
    _attr_default_options: ClassVar = {"voice": "normal"}

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def async_get_tts_audio(self, message, language, options):
        """Record successful synthesis calls and return deterministic audio."""
        self.calls.append((message, language, dict(options)))
        return "mp3", f"audio:{message}".encode()


@pytest.mark.asyncio
async def test_provider_disappears_and_recovers_without_adaptive_entry_reload(
    hass, tmp_path
) -> None:
    """Adaptive TTS becomes unavailable, fails cleanly, and recovers in place."""
    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, "homeassistant", {}) is True

    provider_entity_id = "tts.recovering_provider"
    provider = RecoveringProvider()
    provider.hass = hass
    provider_present = True

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Recovering Adaptive TTS",
        data={CONF_UNDERLYING_TTS_ENTITY: provider_entity_id},
        version=2,
    )
    entry.add_to_hass(hass)

    def provider_lookup(_hass, entity_id):
        if entity_id == provider_entity_id and provider_present:
            return provider
        return None

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
        entity_id = entity.entity_id

        initial_stream = ha_tts.async_create_stream(hass, entity_id)
        initial_stream.async_set_message("Before outage")
        initial_audio = b"".join(
            [chunk async for chunk in initial_stream.async_stream_result()]
        )
        assert initial_audio == b"audio:Before outage"

        provider_present = False
        hass.states.async_set(provider_entity_id, STATE_UNAVAILABLE)
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        assert hass.data[DOMAIN][DATA_ENTITIES][entry.entry_id] is entity
        unavailable_state = hass.states.get(entity_id)
        assert unavailable_state is not None
        assert unavailable_state.state == STATE_UNAVAILABLE

        failed_stream = ha_tts.async_create_stream(hass, entity_id)
        failed_stream.async_set_message("During outage")
        with pytest.raises(HomeAssistantError):
            _ = b"".join(
                [chunk async for chunk in failed_stream.async_stream_result()]
            )

        provider_present = True
        hass.states.async_set(provider_entity_id, "idle")
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        assert hass.data[DOMAIN][DATA_ENTITIES][entry.entry_id] is entity
        recovered_state = hass.states.get(entity_id)
        assert recovered_state is not None
        assert recovered_state.state != STATE_UNAVAILABLE

        recovered_stream = ha_tts.async_create_stream(hass, entity_id)
        recovered_stream.async_set_message("After recovery")
        recovered_audio = b"".join(
            [chunk async for chunk in recovered_stream.async_stream_result()]
        )

    assert initial_stream.extension == "mp3"
    assert recovered_stream.extension == "mp3"
    assert recovered_audio == b"audio:After recovery"
    assert provider.calls == [
        ("Before outage", "en-US", {"voice": "normal"}),
        ("After recovery", "en-US", {"voice": "normal"}),
    ]
