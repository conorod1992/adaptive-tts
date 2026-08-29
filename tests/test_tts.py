"""Tests for the Adaptive TTS entity."""

from datetime import datetime
from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from homeassistant.components.tts import TextToSpeechEntity, Voice
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_tts.const import (
    CONF_QUIET_END,
    CONF_QUIET_MODE,
    CONF_QUIET_OPTION,
    CONF_QUIET_START,
    CONF_QUIET_VALUE,
    CONF_UNDERLYING_TTS_ENTITY,
    DATA_ENTITIES,
    DOMAIN,
)
from custom_components.adaptive_tts.tts import (
    AdaptiveTTSEntity,
    async_setup_entry,
)


class MockTTS(TextToSpeechEntity):
    """Controllable underlying TTS entity."""

    _attr_name = "Source TTS"
    _attr_default_language = "en-US"
    _attr_supported_languages: ClassVar = ["en-US", "en-GB"]
    _attr_supported_options: ClassVar = ["voice", "speed", "format"]
    _attr_default_options: ClassVar = {"voice": "normal", "format": "mp3"}

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def async_get_supported_voices(self, language: str) -> list[Voice] | None:
        return [Voice("normal", "Normal"), Voice("whisper", "Whisper")]

    async def async_get_tts_audio(self, message, language, options):
        self.calls.append((message, language, dict(options)))
        return "mp3", b"source-audio"


def make_entry(
    *,
    quiet: bool = False,
    value: str = "whisper",
    start: str = "00:00:00",
    end: str = "00:00:00",
    option: str = "voice",
) -> MockConfigEntry:
    """Create an Adaptive TTS config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Bedroom TTS",
        data={
            CONF_UNDERLYING_TTS_ENTITY: "tts.source",
            CONF_QUIET_MODE: quiet,
            CONF_QUIET_START: start,
            CONF_QUIET_END: end,
            CONF_QUIET_OPTION: option,
            CONF_QUIET_VALUE: value,
        },
    )


def attach(entity: AdaptiveTTSEntity, hass, source: MockTTS) -> None:
    """Attach an entity and patch its provider lookup through a caller context."""
    entity.hass = hass
    source.hass = hass


@pytest.mark.asyncio
async def test_entity_is_created(hass) -> None:
    """Platform setup creates one Adaptive TTS entity."""
    entry = make_entry()
    hass.data[DOMAIN] = {DATA_ENTITIES: {}}
    added = []
    await async_setup_entry(hass, entry, added.extend)
    assert len(added) == 1
    assert isinstance(added[0], AdaptiveTTSEntity)
    assert hass.data[DOMAIN][DATA_ENTITIES][entry.entry_id] is added[0]


@pytest.mark.asyncio
async def test_normal_audio_is_returned_unchanged_and_options_preserved(hass) -> None:
    """Normal mode delegates bytes unchanged and preserves unrelated options."""
    source = MockTTS()
    entity = AdaptiveTTSEntity(make_entry(quiet=False))
    attach(entity, hass, source)
    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        extension, data = await entity.async_get_tts_audio(
            "hello", "en-US", {"voice": "normal", "speed": "fast"}
        )
    assert (extension, data) == ("mp3", b"source-audio")
    assert source.calls == [
        ("hello", "en-US", {"voice": "normal", "format": "mp3", "speed": "fast"})
    ]


@pytest.mark.asyncio
async def test_quiet_voice_is_applied_without_dropping_options(hass) -> None:
    """Quiet mode changes only the configured option."""
    source = MockTTS()
    entity = AdaptiveTTSEntity(make_entry(quiet=True))
    attach(entity, hass, source)
    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        await entity.async_get_tts_audio(
            "hello", "en-US", {"voice": "normal", "speed": "slow"}
        )
    assert source.calls[0][2] == {
        "voice": "whisper",
        "format": "mp3",
        "speed": "slow",
    }


def test_cross_midnight_entity_policy(hass) -> None:
    """The entity policy evaluates a range crossing midnight."""
    entry = make_entry(quiet=True, start="23:00:00", end="07:00:00")
    entity = AdaptiveTTSEntity(entry)
    entity.hass = hass
    assert entity.is_quiet_mode_active(datetime(2026, 8, 29, 23, 30))
    assert not entity.is_quiet_mode_active(datetime(2026, 8, 29, 12, 0))


def test_missing_underlying_entity(hass) -> None:
    """A missing provider produces a useful Home Assistant error."""
    entity = AdaptiveTTSEntity(make_entry())
    entity.hass = hass
    with (
        patch("custom_components.adaptive_tts.tts.get_tts_entity", return_value=None),
        pytest.raises(HomeAssistantError, match="not available"),
    ):
        entity.resolve_request("en-US", {})


def test_unsupported_quiet_voice(hass) -> None:
    """A removed provider voice fails gracefully before synthesis."""
    source = MockTTS()
    entity = AdaptiveTTSEntity(make_entry(quiet=True, value="removed-voice"))
    attach(entity, hass, source)
    with (
        patch("custom_components.adaptive_tts.tts.get_tts_entity", return_value=source),
        pytest.raises(HomeAssistantError, match="not supported"),
    ):
        entity.resolve_request("en-US", {})


def test_unsupported_quiet_option(hass) -> None:
    """A removed provider option fails gracefully before synthesis."""
    source = MockTTS()
    entry = make_entry(quiet=True, option="emotion")
    entity = AdaptiveTTSEntity(entry)
    attach(entity, hass, source)
    with (
        patch("custom_components.adaptive_tts.tts.get_tts_entity", return_value=source),
        pytest.raises(HomeAssistantError, match="not supported"),
    ):
        entity.resolve_request("en-US", {})
