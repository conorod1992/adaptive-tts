"""Real Home Assistant acceptance test for conditional voice routing."""

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


class RoutingTTSProvider(TextToSpeechEntity):
    """Controllable provider behind a fully loaded routed Adaptive TTS entity."""

    _attr_name = "Routing provider"
    _attr_default_language = "en-US"
    _attr_supported_languages: ClassVar = ["en-US", "en-GB"]
    _attr_supported_options: ClassVar = ["voice"]
    _attr_default_options: ClassVar = {"voice": "normal"}

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def async_get_tts_audio(self, message, language, options):
        """Record the provider request and return deterministic audio."""
        self.calls.append((message, language, dict(options)))
        return "mp3", b"real-ha-routed-audio"


@pytest.mark.asyncio
async def test_real_ha_manager_applies_first_matching_conditional_route(
    hass, tmp_path
) -> None:
    """HA-native conditions choose the routed voice through the loaded entity."""
    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, "homeassistant", {}) is True

    provider_entity_id = "tts.routing_provider"
    provider = RoutingTTSProvider()
    provider.hass = hass

    hass.states.async_set("binary_sensor.route_selector", "on")

    routing_rules = [
        {
            "id": "higher-priority-non-match",
            "name": "Higher priority non-match",
            "enabled": True,
            "conditions": [
                {
                    "condition": "state",
                    "entity_id": "binary_sensor.route_selector",
                    "state": "off",
                }
            ],
            "language": "en-US",
            "voice": "wrong-voice",
        },
        {
            "id": "matching-route",
            "name": "Matching route",
            "enabled": True,
            "conditions": [
                {
                    "condition": "state",
                    "entity_id": "binary_sensor.route_selector",
                    "state": "on",
                }
            ],
            "language": "en-GB",
            "voice": "routed-voice",
        },
        {
            "id": "lower-priority-match",
            "name": "Lower priority match",
            "enabled": True,
            "conditions": [
                {
                    "condition": "state",
                    "entity_id": "binary_sensor.route_selector",
                    "state": "on",
                }
            ],
            "language": "en-US",
            "voice": "lower-priority-voice",
        },
    ]

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Routed Adaptive TTS",
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
        entity = hass.data[DOMAIN][DATA_ENTITIES][entry.entry_id]
        assert isinstance(entity, RoutedAdaptiveTTSEntity)
        assert entity.entity_id is not None

        stream = ha_tts.async_create_stream(hass, entity.entity_id)
        stream.async_set_message("Route this request")
        audio = b"".join([chunk async for chunk in stream.async_stream_result()])

    assert stream.extension == "mp3"
    assert audio == b"real-ha-routed-audio"
    assert provider.calls == [("Route this request", "en-GB", {"voice": "routed-voice"})]
