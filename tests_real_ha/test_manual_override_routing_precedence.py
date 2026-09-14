"""Real Home Assistant acceptance test for manual override routing precedence."""

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
    ATTR_SCOPE,
    ATTR_VOICE,
    CONF_ROUTING_RULES,
    CONF_UNDERLYING_TTS_ENTITY,
    DATA_ENTITIES,
    DOMAIN,
    DURATION_UNTIL_CHANGED,
    SCOPE_PERSISTENT,
    SERVICE_CLEAR_VOICE_OVERRIDE,
    SERVICE_SET_VOICE_OVERRIDE,
)
from custom_components.adaptive_tts.routing_entity import RoutedAdaptiveTTSEntity


class OverrideRoutingProvider(TextToSpeechEntity):
    """Controllable provider for precedence and reload acceptance coverage."""

    _attr_name = "Override routing provider"
    _attr_default_language = "en-US"
    _attr_supported_languages: ClassVar = ["en-US", "en-GB"]
    _attr_supported_options: ClassVar = ["voice"]
    _attr_default_options: ClassVar = {"voice": "normal"}

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def async_get_tts_audio(self, message, language, options):
        """Record the effective provider request and return deterministic audio."""
        self.calls.append((message, language, dict(options)))
        return "mp3", b"manual-override-precedence-audio"


@pytest.mark.asyncio
async def test_persistent_manual_override_beats_routing_across_reload(
    hass, tmp_path
) -> None:
    """A persisted explicit override wins over matching routing after reload."""
    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, "homeassistant", {}) is True

    provider_entity_id = "tts.override_routing_provider"
    provider = OverrideRoutingProvider()
    provider.hass = hass

    hass.states.async_set("binary_sensor.override_route_selector", "on")
    routing_rules = [
        {
            "id": "matching-route",
            "name": "Matching route",
            "enabled": True,
            "conditions": [
                {
                    "condition": "state",
                    "entity_id": "binary_sensor.override_route_selector",
                    "state": "on",
                }
            ],
            "language": "en-GB",
            "voice": "routed-voice",
        }
    ]

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Override precedence Adaptive TTS",
        data={
            CONF_UNDERLYING_TTS_ENTITY: provider_entity_id,
            CONF_ROUTING_RULES: routing_rules,
        },
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
        original_entity = hass.data[DOMAIN][DATA_ENTITIES][entry.entry_id]
        assert isinstance(original_entity, RoutedAdaptiveTTSEntity)
        assert original_entity.entity_id is not None
        entity_id = original_entity.entity_id

        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_VOICE_OVERRIDE,
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_LANGUAGE: "en-US",
                ATTR_VOICE: "manual-voice",
                ATTR_DURATION: DURATION_UNTIL_CHANGED,
            },
            blocking=True,
        )
        assert original_entity.persistent_voice_override is not None
        assert original_entity.persistent_voice_override.voice == "manual-voice"

        assert await hass.config_entries.async_reload(entry.entry_id) is True
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        reloaded_entity = hass.data[DOMAIN][DATA_ENTITIES][entry.entry_id]
        assert isinstance(reloaded_entity, RoutedAdaptiveTTSEntity)
        assert reloaded_entity is not original_entity
        assert reloaded_entity.entity_id == entity_id
        assert reloaded_entity.persistent_voice_override is not None
        assert reloaded_entity.persistent_voice_override.voice == "manual-voice"

        stream = ha_tts.async_create_stream(hass, entity_id)
        stream.async_set_message("Manual override should win")
        audio = b"".join([chunk async for chunk in stream.async_stream_result()])

        await hass.services.async_call(
            DOMAIN,
            SERVICE_CLEAR_VOICE_OVERRIDE,
            {ATTR_ENTITY_ID: entity_id, ATTR_SCOPE: SCOPE_PERSISTENT},
            blocking=True,
        )

        routed_stream = ha_tts.async_create_stream(hass, entity_id)
        routed_stream.async_set_message("Routing should resume")
        routed_audio = b"".join(
            [chunk async for chunk in routed_stream.async_stream_result()]
        )

    assert stream.extension == "mp3"
    assert routed_stream.extension == "mp3"
    assert audio == b"manual-override-precedence-audio"
    assert routed_audio == b"manual-override-precedence-audio"
    assert provider.calls == [
        ("Manual override should win", "en-US", {"voice": "manual-voice"}),
        ("Routing should resume", "en-GB", {"voice": "routed-voice"}),
    ]
