"""Real Home Assistant acceptance coverage for routing lifecycle cleanup."""

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
    CONF_ROUTING_RULES,
    CONF_UNDERLYING_TTS_ENTITY,
    DATA_ENTITIES,
    DOMAIN,
)
from custom_components.adaptive_tts.routing_entity import RoutedAdaptiveTTSEntity


class RoutingLifecycleProvider(TextToSpeechEntity):
    """Provider used while routing entities are repeatedly reloaded."""

    _attr_name = "Routing lifecycle provider"
    _attr_default_language = "en-US"
    _attr_supported_languages: ClassVar = ["en-US", "en-GB"]
    _attr_supported_options: ClassVar = ["voice"]
    _attr_default_options: ClassVar = {"voice": "normal"}

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def async_get_tts_audio(self, message, language, options):
        """Record synthesis and return deterministic audio."""
        self.calls.append((message, language, dict(options)))
        return "mp3", f"audio:{message}".encode()


@pytest.mark.asyncio
async def test_routing_checkers_are_released_across_reloads_and_final_unload(
    hass, tmp_path
) -> None:
    """Old routing runtimes are emptied instead of accumulating across reloads."""
    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, "homeassistant", {}) is True

    provider_entity_id = "tts.routing_lifecycle_provider"
    provider = RoutingLifecycleProvider()
    provider.hass = hass
    hass.states.async_set("binary_sensor.routing_lifecycle", "on")

    rules = [
        {
            "id": "lifecycle-route",
            "name": "Lifecycle route",
            "enabled": True,
            "conditions": [
                {
                    "condition": "state",
                    "entity_id": "binary_sensor.routing_lifecycle",
                    "state": "on",
                }
            ],
            "language": "en-GB",
            "voice": "routed-voice",
        }
    ]
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Routing lifecycle Adaptive TTS",
        data={CONF_UNDERLYING_TTS_ENTITY: provider_entity_id},
        options={CONF_ROUTING_RULES: rules},
        version=2,
    )
    entry.add_to_hass(hass)

    def provider_lookup(_hass, entity_id):
        return provider if entity_id == provider_entity_id else None

    retired_entities: list[RoutedAdaptiveTTSEntity] = []

    with patch(
        "custom_components.adaptive_tts.helpers.get_engine_instance",
        side_effect=provider_lookup,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id) is True
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        entity = hass.data[DOMAIN][DATA_ENTITIES][entry.entry_id]
        assert isinstance(entity, RoutedAdaptiveTTSEntity)
        assert len(entity._conditional_voice_router._rules) == 1
        entity_id = entity.entity_id
        assert entity_id is not None

        for cycle in range(3):
            stream = ha_tts.async_create_stream(hass, entity_id)
            stream.async_set_message(f"Cycle {cycle}")
            audio = b"".join(
                [chunk async for chunk in stream.async_stream_result()]
            )
            assert audio == f"audio:Cycle {cycle}".encode()

            retired_entities.append(entity)
            assert await hass.config_entries.async_reload(entry.entry_id) is True
            await hass.async_block_till_done()

            assert entry.state is ConfigEntryState.LOADED
            assert retired_entities[-1]._conditional_voice_router._rules == []

            entity = hass.data[DOMAIN][DATA_ENTITIES][entry.entry_id]
            assert isinstance(entity, RoutedAdaptiveTTSEntity)
            assert entity is not retired_entities[-1]
            assert entity.entity_id == entity_id
            assert len(entity._conditional_voice_router._rules) == 1

        final_entity = entity
        assert await hass.config_entries.async_unload(entry.entry_id) is True
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert final_entity._conditional_voice_router._rules == []
    assert entry.entry_id not in hass.data[DOMAIN][DATA_ENTITIES]
    assert provider.calls == [
        ("Cycle 0", "en-GB", {"voice": "routed-voice"}),
        ("Cycle 1", "en-GB", {"voice": "routed-voice"}),
        ("Cycle 2", "en-GB", {"voice": "routed-voice"}),
    ]
