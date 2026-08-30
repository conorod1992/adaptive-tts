"""Regression tests for malformed underlying TTS provider responses."""

from unittest.mock import patch

import pytest
from homeassistant.components.tts import TTSAudioRequest, TTSAudioResponse
from homeassistant.exceptions import HomeAssistantError

from custom_components.adaptive_tts.const import (
    CACHE_POLICY_OPTION,
    DURATION_UNTIL_CHANGED,
)
from custom_components.adaptive_tts.tts import AdaptiveTTSEntity

from .test_voice_overrides import OverrideTTS, attach, make_entry


async def _message_gen():
    yield "Provider contract test"


async def _set_persistent_override(entity, hass, source) -> str:
    await entity.async_load_voice_override(hass)
    await entity.async_set_voice_override(
        "en-GB", "cheerful-gb", DURATION_UNTIL_CHANGED
    )
    return entity.default_options[CACHE_POLICY_OPTION]


@pytest.mark.asyncio
async def test_non_bytes_one_shot_audio_is_rejected_and_clears_override(
    hass, tmp_path
) -> None:
    """Truthy non-bytes provider data cannot escape the wrapper as valid audio."""
    hass.config.config_dir = str(tmp_path)
    source = OverrideTTS()
    entity = AdaptiveTTSEntity(make_entry())
    attach(entity, hass, source)

    async def malformed_audio(_message, _language, _options):
        return "mp3", "not-bytes"

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        policy = await _set_persistent_override(entity, hass, source)
        source.async_get_tts_audio = malformed_audio
        with pytest.raises(HomeAssistantError, match="Invalid TTS audio"):
            await entity.async_get_tts_audio(
                "Malformed audio", "en-US", {CACHE_POLICY_OPTION: policy}
            )

    assert entity.persistent_voice_override is None


@pytest.mark.asyncio
async def test_malformed_stream_response_is_rejected_and_clears_override(
    hass, tmp_path
) -> None:
    """A provider returning no TTSAudioResponse fails inside the wrapper."""
    hass.config.config_dir = str(tmp_path)
    source = OverrideTTS()
    entity = AdaptiveTTSEntity(make_entry())
    attach(entity, hass, source)
    source.async_supports_streaming_input = lambda: True

    async def malformed_stream(_request):
        return None

    source.async_stream_tts_audio = malformed_stream
    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        policy = await _set_persistent_override(entity, hass, source)
        with pytest.raises(HomeAssistantError, match="Invalid streaming TTS response"):
            await entity.async_stream_tts_audio(
                TTSAudioRequest(
                    "en-US",
                    {CACHE_POLICY_OPTION: policy},
                    _message_gen(),
                )
            )

    assert entity.persistent_voice_override is None


@pytest.mark.asyncio
async def test_non_bytes_stream_chunk_is_rejected_and_clears_override(
    hass, tmp_path
) -> None:
    """Invalid stream chunks cannot be forwarded as if they were audio bytes."""
    hass.config.config_dir = str(tmp_path)
    source = OverrideTTS()
    entity = AdaptiveTTSEntity(make_entry())
    attach(entity, hass, source)
    source.async_supports_streaming_input = lambda: True

    async def malformed_chunks():
        yield "not-bytes"

    async def malformed_stream(_request):
        return TTSAudioResponse("mp3", malformed_chunks())

    source.async_stream_tts_audio = malformed_stream
    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        policy = await _set_persistent_override(entity, hass, source)
        response = await entity.async_stream_tts_audio(
            TTSAudioRequest(
                "en-US",
                {CACHE_POLICY_OPTION: policy},
                _message_gen(),
            )
        )
        with pytest.raises(HomeAssistantError, match="Invalid TTS audio chunk"):
            _ = [chunk async for chunk in response.data_gen]

    assert entity.persistent_voice_override is None
