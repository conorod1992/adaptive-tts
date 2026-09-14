"""Real Home Assistant acceptance test for malformed persisted routing."""

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


class MalformedRoutingProvider(TextToSpeechEntity):
    """Provider used to prove malformed routing cannot prevent normal TTS."""

    _attr_name = "Malformed routing provider"
    _attr_default_language = "en-US"
    _attr_supported_languages: ClassVar = ["en-US"]
    _attr_supported_options: ClassVar = ["voice"]
    _attr_default_options: ClassVar = {"voice": "normal"}

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def async_get_tts_audio(self, message, language, options):
        """Record the provider request and return deterministic audio."""
        self.calls.append((message, language, dict(options)))
        return "mp3", b"malformed-routing-fallback-audio"


@pytest.mark.asyncio
async def test_invalid_persisted_routing_does_not_brick_loaded_integration(
    hass, tmp_path
) -> None:
    """Invalid stored routing is ignored while ordinary Adaptive TTS still works."""
    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, "homeassistant", {}) is True

    provider_entity_id = "tts.malformed_routing_provider"
    provider = MalformedRoutingProvider()
    provider.hass = hass

    malformed_rules = [
        {
            "id": "legacy-broken-rule",
            "name": "Legacy broken rule",
            "enabled": True,
            "conditions": [
                {
                    "condition": "state",
                    "entity_id": "binary_sensor.anything",
                    "state": "on",
                }
            ],
            "language": "en-US",
            # Deliberately missing required "voice" key, as could happen after
            # stale/manual storage data or an incompatible schema transition.
        }
    ]

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Malformed Routed Adaptive TTS",
        data={CONF_UNDERLYING_TTS_ENTITY: provider_entity_id},
        options={CONF_ROUTING_RULES: malformed_rules},
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

        # Startup recovery must not silently rewrite the user's stored data.
        assert entry.options[CONF_ROUTING_RULES] == malformed_rules

        stream = ha_tts.async_create_stream(hass, entity.entity_id)
        stream.async_set_message("Fallback after malformed routing")
        audio = b"".join([chunk async for chunk in stream.async_stream_result()])

    assert stream.extension == "mp3"
    assert audio == b"malformed-routing-fallback-audio"
    assert provider.calls == [
        ("Fallback after malformed routing", "en-US", {"voice": "normal"})
    ]
