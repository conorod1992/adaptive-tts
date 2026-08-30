"""Tests for Adaptive TTS voice override actions."""

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from homeassistant.components.tts import (
    TextToSpeechEntity,
    TTSAudioRequest,
    TTSAudioResponse,
    Voice,
)
from homeassistant.exceptions import HomeAssistantError
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
    DOMAIN,
    DURATION_NEXT_REQUEST,
    DURATION_UNTIL_CHANGED,
    SCOPE_ALL,
)
from custom_components.adaptive_tts.tts import AdaptiveTTSEntity


class OverrideTTS(TextToSpeechEntity):
    """Underlying TTS provider with language-specific voices."""

    _attr_name = "Source TTS"
    _attr_default_language = "en-US"
    _attr_supported_languages: ClassVar = ["en-US", "en-GB", "en-IE"]
    _attr_supported_options: ClassVar = ["voice"]
    _attr_default_options: ClassVar = {"voice": "normal-us"}

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.fail_generation = False

    def async_get_supported_voices(self, language: str) -> list[Voice] | None:
        if language == "en-GB":
            return [
                Voice("normal-gb", "British"),
                Voice("whisper-gb", "British Whisper"),
                Voice("cheerful-gb", "British Cheerful"),
            ]
        if language == "en-IE":
            return [Voice("conor-ie", "Conor")]
        return [
            Voice("normal-us", "American"),
            Voice("whisper-us", "American Whisper"),
        ]

    async def async_get_tts_audio(self, message, language, options):
        if self.fail_generation:
            raise HomeAssistantError("provider rejected request")
        self.calls.append((message, language, dict(options)))
        return "mp3", options["voice"].encode()


def make_entry() -> MockConfigEntry:
    """Create a quiet-enabled wrapper entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Adaptive TTS",
        data={
            CONF_UNDERLYING_TTS_ENTITY: "tts.source",
            CONF_QUIET_MODE: True,
            CONF_QUIET_START: "00:00:00",
            CONF_QUIET_END: "00:00:00",
            CONF_QUIET_OPTION: "voice",
            CONF_QUIET_LANGUAGE: "en-GB",
            CONF_QUIET_VALUE: "whisper-gb",
        },
    )


def attach(entity: AdaptiveTTSEntity, hass, source: OverrideTTS) -> None:
    """Attach test entities to Home Assistant."""
    entity.hass = hass
    source.hass = hass


@pytest.mark.asyncio
async def test_next_request_override_is_consumed_once(hass) -> None:
    """A next-request voice wins once, then quiet policy resumes."""
    source = OverrideTTS()
    entity = AdaptiveTTSEntity(make_entry())
    attach(entity, hass, source)

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        await entity.async_set_voice_override(
            "en-GB", "cheerful-gb", DURATION_NEXT_REQUEST
        )
        first_policy = entity.default_options[CACHE_POLICY_OPTION]
        first = entity.resolve_request("en-US", {CACHE_POLICY_OPTION: first_policy})
        assert first.language == "en-GB"
        assert first.options["voice"] == "cheerful-gb"
        assert entity.next_voice_override is not None

        await entity.async_get_tts_audio(
            "First request", "en-US", {CACHE_POLICY_OPTION: first_policy}
        )
        assert entity.next_voice_override is None

        second_policy = entity.default_options[CACHE_POLICY_OPTION]
        second = entity.resolve_request("en-US", {CACHE_POLICY_OPTION: second_policy})
        assert second.language == "en-GB"
        assert second.options["voice"] == "whisper-gb"


@pytest.mark.asyncio
async def test_next_request_language_survives_preflight_resolution(hass) -> None:
    """Preflight resolution must not consume the voice or its selected language."""
    source = OverrideTTS()
    entity = AdaptiveTTSEntity(make_entry())
    attach(entity, hass, source)

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        await entity.async_set_voice_override(
            "en-IE", "conor-ie", DURATION_NEXT_REQUEST
        )
        policy = entity.default_options[CACHE_POLICY_OPTION]

        preflight = entity.resolve_request("en-GB", {CACHE_POLICY_OPTION: policy})
        assert preflight.language == "en-IE"
        assert preflight.options["voice"] == "conor-ie"
        assert entity.next_voice_override is not None

        second_preflight = entity.resolve_request(
            "en-GB", {CACHE_POLICY_OPTION: policy}
        )
        assert second_preflight.language == "en-IE"
        assert second_preflight.options["voice"] == "conor-ie"
        assert entity.next_voice_override is not None

        await entity.async_get_tts_audio(
            "Use Irish voice", "en-GB", {CACHE_POLICY_OPTION: policy}
        )
        assert source.calls[-1][1] == "en-IE"
        assert source.calls[-1][2]["voice"] == "conor-ie"
        assert entity.next_voice_override is None


@pytest.mark.asyncio
async def test_persistent_override_survives_reload(hass, tmp_path) -> None:
    """Until-changed overrides survive creation of a new entity instance."""
    hass.config.config_dir = str(tmp_path)
    entry = make_entry()
    source = OverrideTTS()
    first = AdaptiveTTSEntity(entry)
    attach(first, hass, source)
    await first.async_load_voice_override(hass)

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        await first.async_set_voice_override(
            "en-GB", "cheerful-gb", DURATION_UNTIL_CHANGED
        )
        assert first.persistent_voice_override is not None

        reloaded = AdaptiveTTSEntity(entry)
        attach(reloaded, hass, source)
        await reloaded.async_load_voice_override(hass)
        assert reloaded.persistent_voice_override is not None
        assert reloaded.persistent_voice_override.voice == "cheerful-gb"
        assert reloaded.persistent_voice_override.language == "en-GB"

        policy = reloaded.default_options[CACHE_POLICY_OPTION]
        resolved = reloaded.resolve_request("en-US", {CACHE_POLICY_OPTION: policy})
        assert resolved.language == "en-GB"
        assert resolved.options["voice"] == "cheerful-gb"

        await reloaded.async_clear_voice_override(SCOPE_ALL)
        assert reloaded.persistent_voice_override is None

        after_clear = AdaptiveTTSEntity(entry)
        attach(after_clear, hass, source)
        await after_clear.async_load_voice_override(hass)
        assert after_clear.persistent_voice_override is None


@pytest.mark.asyncio
async def test_failed_persistent_override_is_cleared(hass, tmp_path) -> None:
    """A failed request clears a persistent override so later speech can recover."""
    hass.config.config_dir = str(tmp_path)
    entry = make_entry()
    source = OverrideTTS()
    entity = AdaptiveTTSEntity(entry)
    attach(entity, hass, source)
    await entity.async_load_voice_override(hass)

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        await entity.async_set_voice_override(
            "en-GB", "cheerful-gb", DURATION_UNTIL_CHANGED
        )
        policy = entity.default_options[CACHE_POLICY_OPTION]
        source.fail_generation = True

        with pytest.raises(HomeAssistantError, match="provider rejected request"):
            await entity.async_get_tts_audio(
                "This fails", "en-US", {CACHE_POLICY_OPTION: policy}
            )

        assert entity.persistent_voice_override is None

        source.fail_generation = False
        resumed_policy = entity.default_options[CACHE_POLICY_OPTION]
        _extension, data = await entity.async_get_tts_audio(
            "This recovers", "en-US", {CACHE_POLICY_OPTION: resumed_policy}
        )
        assert data == b"whisper-gb"

        reloaded = AdaptiveTTSEntity(entry)
        attach(reloaded, hass, source)
        await reloaded.async_load_voice_override(hass)
        assert reloaded.persistent_voice_override is None


@pytest.mark.asyncio
async def test_no_audio_result_clears_persistent_override(hass, tmp_path) -> None:
    """A provider's (None, None) failure cannot leave a bad override active."""
    hass.config.config_dir = str(tmp_path)
    entry = make_entry()
    source = OverrideTTS()
    entity = AdaptiveTTSEntity(entry)
    attach(entity, hass, source)
    await entity.async_load_voice_override(hass)

    async def no_audio(message, language, options):
        return None, None

    source.async_get_tts_audio = no_audio
    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        await entity.async_set_voice_override(
            "en-GB", "cheerful-gb", DURATION_UNTIL_CHANGED
        )
        policy = entity.default_options[CACHE_POLICY_OPTION]
        with pytest.raises(HomeAssistantError, match="No TTS audio"):
            await entity.async_get_tts_audio(
                "Silent failure", "en-US", {CACHE_POLICY_OPTION: policy}
            )

    assert entity.persistent_voice_override is None


@pytest.mark.asyncio
async def test_empty_stream_clears_persistent_override(hass, tmp_path) -> None:
    """A delegated stream ending without audio is treated as a TTS failure."""
    hass.config.config_dir = str(tmp_path)
    entry = make_entry()
    source = OverrideTTS()
    entity = AdaptiveTTSEntity(entry)
    attach(entity, hass, source)
    await entity.async_load_voice_override(hass)

    async def message_gen():
        yield "Silent stream"

    async def empty_audio_gen():
        if False:
            yield b""

    async def empty_stream(_request):
        return TTSAudioResponse("mp3", empty_audio_gen())

    source.async_supports_streaming_input = lambda: True
    source.async_stream_tts_audio = empty_stream

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        await entity.async_set_voice_override(
            "en-GB", "cheerful-gb", DURATION_UNTIL_CHANGED
        )
        policy = entity.default_options[CACHE_POLICY_OPTION]
        response = await entity.async_stream_tts_audio(
            TTSAudioRequest(
                "en-US",
                {CACHE_POLICY_OPTION: policy},
                message_gen(),
            )
        )
        with pytest.raises(HomeAssistantError, match="No TTS audio"):
            _ = b"".join([chunk async for chunk in response.data_gen])

    assert entity.persistent_voice_override is None


@pytest.mark.asyncio
async def test_invalid_persistent_override_is_cleared_during_resolution(
    hass, tmp_path
) -> None:
    """A voice removed by the provider does not poison every later request."""
    hass.config.config_dir = str(tmp_path)
    entry = make_entry()
    source = OverrideTTS()
    entity = AdaptiveTTSEntity(entry)
    attach(entity, hass, source)
    await entity.async_load_voice_override(hass)

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        await entity.async_set_voice_override(
            "en-GB", "cheerful-gb", DURATION_UNTIL_CHANGED
        )
        policy = entity.default_options[CACHE_POLICY_OPTION]
        original_get_voices = source.async_get_supported_voices

        def get_voices_without_override(language: str) -> list[Voice] | None:
            voices = original_get_voices(language)
            if language != "en-GB" or voices is None:
                return voices
            return [voice for voice in voices if voice.voice_id != "cheerful-gb"]

        source.async_get_supported_voices = get_voices_without_override

        with pytest.raises(HomeAssistantError, match="cheerful-gb"):
            await entity.async_get_tts_audio(
                "Removed voice", "en-US", {CACHE_POLICY_OPTION: policy}
            )

        assert entity.persistent_voice_override is None


@pytest.mark.asyncio
async def test_action_override_changes_cache_fingerprint(hass) -> None:
    """One-shot and persistent voice changes are represented in the cache key."""
    source = OverrideTTS()
    entity = AdaptiveTTSEntity(make_entry())
    attach(entity, hass, source)
    await entity.async_load_voice_override(hass)

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        baseline = entity.default_options[CACHE_POLICY_OPTION]
        await entity.async_set_voice_override(
            "en-GB", "cheerful-gb", DURATION_NEXT_REQUEST
        )
        one_shot = entity.default_options[CACHE_POLICY_OPTION]
        assert one_shot != baseline

        await entity.async_get_tts_audio(
            "Consume override", "en-US", {CACHE_POLICY_OPTION: one_shot}
        )
        resumed = entity.default_options[CACHE_POLICY_OPTION]
        assert resumed == baseline

        await entity.async_set_voice_override(
            "en-GB", "cheerful-gb", DURATION_UNTIL_CHANGED
        )
        persistent = entity.default_options[CACHE_POLICY_OPTION]
        assert persistent != baseline
        assert persistent != one_shot
