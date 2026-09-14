"""Real Home Assistant acceptance test for routing save and reload."""

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


class ReloadRoutingProvider(TextToSpeechEntity):
    """Controllable provider used across the Adaptive TTS entry reload."""

    _attr_name = "Reload routing provider"
    _attr_default_language = "en-US"
    _attr_supported_languages: ClassVar = ["en-US", "en-GB"]
    _attr_supported_options: ClassVar = ["voice"]
    _attr_default_options: ClassVar = {"voice": "normal"}

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def async_get_tts_audio(self, message, language, options):
        """Record the provider request and return deterministic audio."""
        self.calls.append((message, language, dict(options)))
        return "mp3", b"routing-save-reload-audio"


@pytest.mark.asyncio
async def test_websocket_routing_save_reloads_entry_and_changes_live_behavior(
    hass, tmp_path, hass_ws_client
) -> None:
    """Saving routing over HA WebSocket reloads the entry and affects TTS."""
    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, "homeassistant", {}) is True

    provider_entity_id = "tts.reload_routing_provider"
    provider = ReloadRoutingProvider()
    provider.hass = hass

    hass.states.async_set("binary_sensor.reload_route_selector", "on")

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Reloaded Routed Adaptive TTS",
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
        original_entity = hass.data[DOMAIN][DATA_ENTITIES][entry.entry_id]
        assert isinstance(original_entity, RoutedAdaptiveTTSEntity)
        assert original_entity.entity_id is not None
        entity_id = original_entity.entity_id

        client = await hass_ws_client(hass)
        rules = [
            {
                "id": "saved-route",
                "name": "Saved route",
                "enabled": True,
                "conditions": [
                    {
                        "condition": "state",
                        "entity_id": "binary_sensor.reload_route_selector",
                        "state": "on",
                    }
                ],
                "language": "en-GB",
                "voice": "saved-routed-voice",
            }
        ]
        await client.send_json_auto_id(
            {
                "type": "adaptive_tts/routing_save",
                "entity_id": entity_id,
                "rules": rules,
            }
        )
        response = await client.receive_json()
        assert response["success"] is True
        assert response["result"] == {"saved": True, "rules": rules}

        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        assert entry.options[CONF_ROUTING_RULES] == rules
        reloaded_entity = hass.data[DOMAIN][DATA_ENTITIES][entry.entry_id]
        assert isinstance(reloaded_entity, RoutedAdaptiveTTSEntity)
        assert reloaded_entity is not original_entity
        assert reloaded_entity.entity_id == entity_id

        stream = ha_tts.async_create_stream(hass, entity_id)
        stream.async_set_message("Use the saved route")
        audio = b"".join([chunk async for chunk in stream.async_stream_result()])

    assert stream.extension == "mp3"
    assert audio == b"routing-save-reload-audio"
    assert provider.calls == [
        ("Use the saved route", "en-GB", {"voice": "saved-routed-voice"})
    ]
