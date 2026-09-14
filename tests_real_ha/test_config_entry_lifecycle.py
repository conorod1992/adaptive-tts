"""Real Home Assistant acceptance tests for config-entry lifecycle."""

from __future__ import annotations

from typing import ClassVar
from unittest.mock import patch

import pytest
from homeassistant.components.tts import TextToSpeechEntity
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_tts.const import (
    CONF_UNDERLYING_TTS_ENTITY,
    DATA_ENTITIES,
    DOMAIN,
)
from custom_components.adaptive_tts.routing_entity import RoutedAdaptiveTTSEntity


class LifecycleTTSProvider(TextToSpeechEntity):
    """Minimal provider used while HA owns the Adaptive TTS lifecycle."""

    _attr_name = "Lifecycle provider"
    _attr_default_language = "en-US"
    _attr_supported_languages: ClassVar = ["en-US"]
    _attr_supported_options: ClassVar = ["voice"]
    _attr_default_options: ClassVar = {"voice": "normal"}

    async def async_get_tts_audio(self, message, language, options):
        """Return deterministic audio if HA probes the provider."""
        return "mp3", b"lifecycle-audio"


@pytest.mark.asyncio
async def test_config_entry_load_unload_reload_uses_real_ha_platform(hass) -> None:
    """HA creates, removes, and recreates the Adaptive TTS entity itself."""
    provider_entity_id = "tts.lifecycle_provider"
    provider = LifecycleTTSProvider()
    provider.hass = hass

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Lifecycle Adaptive TTS",
        data={CONF_UNDERLYING_TTS_ENTITY: provider_entity_id},
        version=2,
    )
    entry.add_to_hass(hass)

    def get_engine_instance(_hass, entity_id):
        return provider if entity_id == provider_entity_id else None

    with patch(
        "custom_components.adaptive_tts.helpers.get_engine_instance",
        side_effect=get_engine_instance,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id) is True
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        first_entity = hass.data[DOMAIN][DATA_ENTITIES][entry.entry_id]
        assert isinstance(first_entity, RoutedAdaptiveTTSEntity)
        assert first_entity.hass is hass
        assert first_entity.platform is not None
        assert first_entity.entity_id.startswith("tts.")
        assert hass.states.get(first_entity.entity_id) is not None

        registry_entry = er.async_get(hass).async_get(first_entity.entity_id)
        assert registry_entry is not None
        assert registry_entry.platform == DOMAIN
        assert registry_entry.unique_id == entry.entry_id
        entity_id = first_entity.entity_id

        assert await hass.config_entries.async_unload(entry.entry_id) is True
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.NOT_LOADED
        assert entry.entry_id not in hass.data[DOMAIN][DATA_ENTITIES]
        assert hass.states.get(entity_id) is None

        assert await hass.config_entries.async_setup(entry.entry_id) is True
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        reloaded_entity = hass.data[DOMAIN][DATA_ENTITIES][entry.entry_id]
        assert isinstance(reloaded_entity, RoutedAdaptiveTTSEntity)
        assert reloaded_entity is not first_entity
        assert reloaded_entity.entity_id == entity_id
        assert hass.states.get(entity_id) is not None

        reloaded_registry_entry = er.async_get(hass).async_get(entity_id)
        assert reloaded_registry_entry is not None
        assert reloaded_registry_entry.unique_id == entry.entry_id
