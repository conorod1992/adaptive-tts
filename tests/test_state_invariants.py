"""Regression tests for override and entity lifecycle invariants."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
import voluptuous as vol
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_tts.const import (
    ATTR_LANGUAGE,
    ATTR_VOICE,
    CONF_QUIET_END,
    CONF_QUIET_LANGUAGE,
    CONF_QUIET_MODE,
    CONF_QUIET_OPTION,
    CONF_QUIET_START,
    CONF_QUIET_VALUE,
    CONF_UNDERLYING_TTS_ENTITY,
    DATA_ENTITIES,
    DOMAIN,
)
from custom_components.adaptive_tts.helpers import entry_config
from custom_components.adaptive_tts.services import _SET_SCHEMA
from custom_components.adaptive_tts.tts import AdaptiveTTSEntity, async_setup_entry

from .test_tts import MockTTS


def make_entry(*, options=None) -> MockConfigEntry:
    """Create an Adaptive TTS entry with a voice quiet policy."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Adaptive TTS",
        data={
            CONF_UNDERLYING_TTS_ENTITY: "tts.source",
            CONF_QUIET_MODE: True,
            CONF_QUIET_START: "23:00:00",
            CONF_QUIET_END: "07:00:00",
            CONF_QUIET_OPTION: "voice",
            CONF_QUIET_LANGUAGE: "en-GB",
            CONF_QUIET_VALUE: "whisper",
        },
        options=options or {},
    )


def test_service_schema_rejects_blank_voice_and_normalizes_text() -> None:
    """Whitespace cannot create an override which snapshots later reject."""
    with pytest.raises(vol.Invalid):
        _SET_SCHEMA(
            {
                ATTR_ENTITY_ID: ["tts.adaptive_tts"],
                ATTR_LANGUAGE: "en-US",
                ATTR_VOICE: "   ",
            }
        )

    validated = _SET_SCHEMA(
        {
            ATTR_ENTITY_ID: ["tts.adaptive_tts"],
            ATTR_LANGUAGE: "  en-US  ",
            ATTR_VOICE: "  provider voice  ",
        }
    )
    assert validated[ATTR_LANGUAGE] == "en-US"
    assert validated[ATTR_VOICE] == "provider voice"


def test_direct_override_validation_rejects_blank_and_normalizes(hass) -> None:
    """Internal callers cannot bypass the same override invariant."""
    source = MockTTS()
    source.async_get_supported_voices = lambda _language: None
    entity = AdaptiveTTSEntity(make_entry())
    entity.hass = hass
    source.hass = hass

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        with pytest.raises(HomeAssistantError, match="must not be empty"):
            entity.validate_voice_override("en-US", "   ")
        override = entity.validate_voice_override("  en-US  ", "  provider-specific  ")

    assert override.language == "en-US"
    assert override.voice == "provider-specific"


@pytest.mark.asyncio
async def test_rejected_entity_is_removed_from_service_lookup(hass) -> None:
    """Home Assistant rejecting a disabled entity cannot leave a ghost target."""
    entry = make_entry()
    hass.data.setdefault(DOMAIN, {})[DATA_ENTITIES] = {}
    captured = {}

    def reject_entity(entities) -> None:
        entity = entities[0]
        captured["entity"] = entity
        entity.add_to_platform_start(hass, Mock(platform_data=None), None)
        entity.add_to_platform_abort()

    with patch.object(AdaptiveTTSEntity, "async_load_voice_override", new=AsyncMock()):
        await async_setup_entry(hass, entry, reject_entity)

    assert captured["entity"].hass is None
    assert entry.entry_id not in hass.data[DOMAIN][DATA_ENTITIES]


@pytest.mark.asyncio
async def test_failed_malformed_store_remove_is_neutralized(hass) -> None:
    """A corrupt override does not recur forever when Store removal fails."""
    entry = make_entry()

    class StoreWithBrokenRemove:
        def __init__(self) -> None:
            self.remove_calls = 0
            self.saved = []

        async def async_load(self):
            return {
                "underlying_entity_id": "tts.source",
                "language": "en-US",
                "voice": "   ",
                "token": "token",
            }

        async def async_remove(self):
            self.remove_calls += 1
            raise OSError("remove failed")

        async def async_save(self, data):
            self.saved.append(dict(data))

    store = StoreWithBrokenRemove()
    entity = AdaptiveTTSEntity(entry)
    with patch(
        "custom_components.adaptive_tts.tts._voice_override_store",
        return_value=store,
    ):
        await entity.async_load_voice_override(hass)

    assert entity.persistent_voice_override is None
    assert store.remove_calls == 1
    assert store.saved == [{}]


@pytest.mark.parametrize(
    "options",
    [
        {CONF_QUIET_MODE: False},
        {CONF_QUIET_OPTION: "style", CONF_QUIET_VALUE: "soft"},
    ],
)
def test_irrelevant_quiet_language_is_removed_from_merged_config(options) -> None:
    """Old voice-language data cannot leak into disabled/non-voice policy."""
    config = entry_config(make_entry(options=options))
    assert CONF_QUIET_LANGUAGE not in config
