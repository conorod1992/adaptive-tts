"""Real Home Assistant acceptance test for live routing condition testing."""

from __future__ import annotations

from typing import ClassVar
from unittest.mock import patch

import pytest
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


class RoutingTestProvider(TextToSpeechEntity):
    """Minimal provider used to load Adaptive TTS for WebSocket testing."""

    _attr_name = "Routing test provider"
    _attr_default_language = "en-US"
    _attr_supported_languages: ClassVar = ["en-US"]
    _attr_supported_options: ClassVar = ["voice"]
    _attr_default_options: ClassVar = {"voice": "normal"}

    async def async_get_tts_audio(self, message, language, options):
        """Return deterministic audio if HA probes the provider."""
        return "mp3", b"routing-test-audio"


@pytest.mark.asyncio
async def test_routing_test_websocket_uses_live_state_without_persisting(
    hass, tmp_path, hass_ws_client
) -> None:
    """Unsaved draft rules are tested through HA's authenticated WebSocket API."""
    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, "homeassistant", {}) is True

    provider_entity_id = "tts.routing_test_provider"
    provider = RoutingTestProvider()
    provider.hass = hass
    hass.states.async_set("binary_sensor.routing_test_selector", "on")

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Routing Test Adaptive TTS",
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

        rules = [
            {
                "id": "disabled-higher-match",
                "name": "Disabled higher match",
                "enabled": False,
                "conditions": [
                    {
                        "condition": "state",
                        "entity_id": "binary_sensor.routing_test_selector",
                        "state": "on",
                    }
                ],
                "voice": "disabled-voice",
            },
            {
                "id": "effective-winner",
                "name": "Effective winner",
                "enabled": True,
                "conditions": [
                    {
                        "condition": "state",
                        "entity_id": "binary_sensor.routing_test_selector",
                        "state": "on",
                    }
                ],
                "voice": "winner-voice",
            },
            {
                "id": "target-also-matches",
                "name": "Target also matches",
                "enabled": True,
                "conditions": [
                    {
                        "condition": "state",
                        "entity_id": "binary_sensor.routing_test_selector",
                        "state": "on",
                    }
                ],
                "voice": "target-voice",
            },
            {
                "id": "unfinished-lower-rule",
                "name": "Unfinished lower rule",
                "enabled": True,
                "conditions": [],
                "voice": "unfinished-voice",
            },
        ]

        client = await hass_ws_client(hass)
        await client.send_json_auto_id(
            {
                "type": "adaptive_tts/routing_test",
                "rules": rules,
                "target_index": 2,
            }
        )
        response = await client.receive_json()

        assert response["success"] is True
        assert response["result"] == {
            "matches": True,
            "enabled": True,
            "would_win": False,
            "winner_index": 1,
            "winner_name": "Effective winner",
        }

        await client.send_json_auto_id(
            {
                "type": "adaptive_tts/routing_test",
                "rules": rules,
                "target_index": 1,
            }
        )
        winning_response = await client.receive_json()

        assert winning_response["success"] is True
        assert winning_response["result"] == {
            "matches": True,
            "enabled": True,
            "would_win": True,
            "winner_index": 1,
            "winner_name": "Effective winner",
        }

        await hass.async_block_till_done()

        assert entry.options == {}
        assert hass.data[DOMAIN][DATA_ENTITIES][entry.entry_id] is entity
