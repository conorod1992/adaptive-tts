"""Tests for the Adaptive TTS entity."""

from datetime import datetime
from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from homeassistant.components import tts as ha_tts
from homeassistant.components.tts import TextToSpeechEntity, TTSAudioRequest, Voice
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_tts.const import (
    CACHE_POLICY_OPTION,
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
    language: str | None = None,
) -> MockConfigEntry:
    """Create an Adaptive TTS config entry."""
    data = {
        CONF_UNDERLYING_TTS_ENTITY: "tts.source",
        CONF_QUIET_MODE: quiet,
        CONF_QUIET_START: start,
        CONF_QUIET_END: end,
        CONF_QUIET_OPTION: option,
        CONF_QUIET_VALUE: value,
    }
    if language is not None:
        data[CONF_QUIET_LANGUAGE] = language
    return MockConfigEntry(domain=DOMAIN, title="Bedroom TTS", data=data)


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


@pytest.mark.asyncio
async def test_quiet_voice_can_override_pipeline_language(hass) -> None:
    """Quiet voice selection can deliberately use another supported language/accent."""
    source = MockTTS()
    source.async_get_supported_voices = lambda language: (
        [Voice("british", "British Whisper")]
        if language == "en-GB"
        else [Voice("american", "American Whisper")]
    )
    entity = AdaptiveTTSEntity(
        make_entry(quiet=True, language="en-GB", value="british")
    )
    attach(entity, hass, source)
    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        await entity.async_get_tts_audio("hello", "en-US", {"voice": "american"})
    assert source.calls[0][1] == "en-GB"
    assert source.calls[0][2]["voice"] == "british"


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
    """A removed optional quiet voice falls back to normal TTS settings."""
    source = MockTTS()
    entity = AdaptiveTTSEntity(make_entry(quiet=True, value="removed-voice"))
    attach(entity, hass, source)
    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        resolved = entity.resolve_request("en-US", {})

    assert resolved.language == "en-US"
    assert resolved.options == {"voice": "normal", "format": "mp3"}
    assert resolved.quiet_mode_active is False


def test_unsupported_quiet_option(hass) -> None:
    """A removed optional quiet option falls back to normal TTS settings."""
    source = MockTTS()
    entry = make_entry(quiet=True, option="emotion")
    entity = AdaptiveTTSEntity(entry)
    attach(entity, hass, source)
    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        resolved = entity.resolve_request("en-US", {})

    assert resolved.language == "en-US"
    assert resolved.options == {"voice": "normal", "format": "mp3"}
    assert resolved.quiet_mode_active is False


def test_runtime_voice_validation_uses_actual_language_for_legacy_entries(hass) -> None:
    """Legacy quiet voices invalid for the request language fall back safely."""
    source = MockTTS()
    source.async_get_supported_voices = lambda language: (
        [Voice("whisper", "Whisper")]
        if language == "en-US"
        else [Voice("british", "British")]
    )
    entity = AdaptiveTTSEntity(make_entry(quiet=True, value="whisper"))
    attach(entity, hass, source)
    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        resolved = entity.resolve_request("en-GB", {})

    assert resolved.language == "en-GB"
    assert resolved.options == {"voice": "normal", "format": "mp3"}
    assert resolved.quiet_mode_active is False


@pytest.mark.asyncio
async def test_provider_home_assistant_error_is_preserved(hass) -> None:
    """Useful Home Assistant provider errors propagate without replacement."""
    source = MockTTS()
    provider_error = HomeAssistantError("provider quota exhausted")

    async def fail(message, language, options):
        raise provider_error

    source.async_get_tts_audio = fail
    entity = AdaptiveTTSEntity(make_entry())
    attach(entity, hass, source)
    with (
        patch("custom_components.adaptive_tts.tts.get_tts_entity", return_value=source),
        pytest.raises(HomeAssistantError) as raised,
    ):
        await entity.async_get_tts_audio("hello", "en-US", {})
    assert raised.value is provider_error


def test_missing_provider_has_no_fake_english_capabilities(hass) -> None:
    """An unavailable wrapper does not advertise invented English support."""
    entity = AdaptiveTTSEntity(make_entry())
    entity.hass = hass
    with patch("custom_components.adaptive_tts.tts.get_tts_entity", return_value=None):
        assert entity.available is False
        assert entity.default_language == ""
        assert entity.supported_languages == []


@pytest.mark.asyncio
async def test_manager_cache_separates_normal_and_quiet_policy(hass, tmp_path) -> None:
    """The real HA manager cache cannot reuse audio across policy boundaries."""
    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, "tts", {"tts": [{"cache": False}]})
    hass.data[ha_tts.DATA_TTS_MANAGER].use_file_cache = False
    source = MockTTS()

    async def audio_for_voice(message, language, options):
        source.calls.append((message, language, dict(options)))
        return "mp3", options["voice"].encode()

    source.async_get_tts_audio = audio_for_voice
    entity = AdaptiveTTSEntity(make_entry(quiet=True, start="23:00:00", end="07:00:00"))
    attach(entity, hass, source)
    now = [datetime(2026, 8, 29, 12, 0)]

    async def internal_get(message, language, options):
        return await entity.async_get_tts_audio(message, language, options)

    async def internal_stream(request):
        return await entity.async_stream_tts_audio(request)

    def engine_for_id(_hass, engine_id):
        return entity if engine_id == "tts.adaptive" else source

    with (
        patch("custom_components.adaptive_tts.tts.get_tts_entity", return_value=source),
        patch(
            "custom_components.adaptive_tts.tts.dt_util.now",
            side_effect=lambda: now[0],
        ),
        patch(
            "homeassistant.components.tts.get_engine_instance",
            side_effect=engine_for_id,
        ),
        patch.object(entity, "async_internal_get_tts_audio", side_effect=internal_get),
        patch.object(
            entity,
            "internal_async_stream_tts_audio",
            side_effect=internal_stream,
        ),
    ):
        normal = ha_tts.async_create_stream(hass, "tts.adaptive", options={})
        now[0] = datetime(2026, 8, 29, 23, 30)
        normal.async_set_message("Good night")
        normal_audio = b"".join([chunk async for chunk in normal.async_stream_result()])

        quiet = ha_tts.async_create_stream(hass, "tts.adaptive", options={})
        quiet.async_set_message("Good night")
        quiet_audio = b"".join([chunk async for chunk in quiet.async_stream_result()])

        now[0] = datetime(2026, 8, 30, 12, 0)
        normal_again = ha_tts.async_create_stream(hass, "tts.adaptive", options={})
        normal_again.async_set_message("Good night")
        normal_again_audio = b"".join(
            [chunk async for chunk in normal_again.async_stream_result()]
        )

    assert normal_audio == b"normal"
    assert quiet_audio == b"whisper"
    assert normal_again_audio == b"normal"
    assert len(source.calls) == 2
    assert all("_adaptive_tts_policy" not in call[2] for call in source.calls)
    assert normal.options != quiet.options


@pytest.mark.asyncio
async def test_quiet_fallback_does_not_poison_recovered_policy_cache(
    hass, tmp_path
) -> None:
    """Fallback audio cannot be reused once the quiet policy recovers."""
    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, "tts", {"tts": [{"cache": False}]})
    hass.data[ha_tts.DATA_TTS_MANAGER].use_file_cache = False
    source = MockTTS()
    quiet_voice_available = [False]

    def supported_voices(_language):
        voices = [Voice("normal", "Normal")]
        if quiet_voice_available[0]:
            voices.append(Voice("whisper", "Whisper"))
        return voices

    async def audio_for_voice(message, language, options):
        source.calls.append((message, language, dict(options)))
        return "mp3", options["voice"].encode()

    source.async_get_supported_voices = supported_voices
    source.async_get_tts_audio = audio_for_voice
    entity = AdaptiveTTSEntity(make_entry(quiet=True))
    attach(entity, hass, source)

    async def internal_stream(request):
        return await entity.async_stream_tts_audio(request)

    def engine_for_id(_hass, engine_id):
        return entity if engine_id == "tts.adaptive" else source

    with (
        patch("custom_components.adaptive_tts.tts.get_tts_entity", return_value=source),
        patch(
            "homeassistant.components.tts.get_engine_instance",
            side_effect=engine_for_id,
        ),
        patch.object(
            entity,
            "internal_async_stream_tts_audio",
            side_effect=internal_stream,
        ),
    ):
        first = ha_tts.async_create_stream(hass, "tts.adaptive", options={})
        first_policy = first.options[CACHE_POLICY_OPTION]
        first.async_set_message("Good night")
        first_audio = b"".join([chunk async for chunk in first.async_stream_result()])

        quiet_voice_available[0] = True
        second = ha_tts.async_create_stream(hass, "tts.adaptive", options={})
        second_policy = second.options[CACHE_POLICY_OPTION]
        second.async_set_message("Good night")
        second_audio = b"".join([chunk async for chunk in second.async_stream_result()])

        third = ha_tts.async_create_stream(hass, "tts.adaptive", options={})
        third_policy = third.options[CACHE_POLICY_OPTION]
        third.async_set_message("Good night")
        third_audio = b"".join([chunk async for chunk in third.async_stream_result()])

    assert first_audio == b"normal"
    assert second_audio == b"whisper"
    assert third_audio == b"whisper"
    assert first_policy != second_policy
    assert second_policy == third_policy
    assert [call[2]["voice"] for call in source.calls] == ["normal", "whisper"]


def test_policy_configuration_change_updates_cache_fingerprint(hass) -> None:
    """Changing quiet policy configuration differentiates future cache entries."""
    source = MockTTS()
    entry = make_entry(quiet=True)
    entry.add_to_hass(hass)
    entity = AdaptiveTTSEntity(entry)
    attach(entity, hass, source)
    with (
        patch("custom_components.adaptive_tts.tts.get_tts_entity", return_value=source),
        patch(
            "custom_components.adaptive_tts.tts.dt_util.now",
            return_value=datetime(2026, 8, 29, 1, 0),
        ),
    ):
        before = entity.default_options[CACHE_POLICY_OPTION]
        hass.config_entries.async_update_entry(
            entry, options={CONF_QUIET_VALUE: "softer-whisper"}
        )
        after = entity.default_options[CACHE_POLICY_OPTION]
    assert before != after


@pytest.mark.asyncio
async def test_cache_fingerprint_does_not_leak_through_stream_fallback(hass) -> None:
    """Wrapper-only metadata is removed before fallback streaming delegation."""
    source = MockTTS()
    entity = AdaptiveTTSEntity(make_entry())
    attach(entity, hass, source)

    async def message_gen():
        yield "hello"

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        response = await entity.async_stream_tts_audio(
            TTSAudioRequest(
                "en-US",
                {CACHE_POLICY_OPTION: "internal", "speed": "slow"},
                message_gen(),
            )
        )
        assert b"".join([chunk async for chunk in response.data_gen]) == b"source-audio"
    assert CACHE_POLICY_OPTION not in source.calls[0][2]
