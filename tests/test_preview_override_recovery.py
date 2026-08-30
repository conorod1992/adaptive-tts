"""Regression tests for Adaptive TTS preview override recovery."""

from unittest.mock import patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.adaptive_tts.const import (
    CACHE_POLICY_OPTION,
    DURATION_NEXT_REQUEST,
    DURATION_UNTIL_CHANGED,
)
from custom_components.adaptive_tts.preview import create_preview
from custom_components.adaptive_tts.tts import AdaptiveTTSEntity

from .test_voice_overrides import OverrideTTS, attach, make_entry


@pytest.mark.asyncio
async def test_successful_preview_preflight_keeps_next_request_override(hass) -> None:
    """A valid preview preflight must not consume a pending one-shot override."""
    source = OverrideTTS()
    entity = AdaptiveTTSEntity(make_entry())
    attach(entity, hass, source)

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        await entity.async_set_voice_override(
            "en-GB", "cheerful-gb", DURATION_NEXT_REQUEST
        )
        policy = entity.default_options[CACHE_POLICY_OPTION]
        resolved = await entity.async_resolve_request_for_preflight(
            "en-US", {CACHE_POLICY_OPTION: policy}
        )

    assert resolved.language == "en-GB"
    assert resolved.options["voice"] == "cheerful-gb"
    assert entity.next_voice_override is not None


@pytest.mark.asyncio
async def test_failed_preflight_clears_invalid_next_request_override(hass) -> None:
    """A one-shot override rejected by preflight must not poison later requests."""
    source = OverrideTTS()
    entity = AdaptiveTTSEntity(make_entry())
    attach(entity, hass, source)

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        await entity.async_set_voice_override(
            "en-GB", "cheerful-gb", DURATION_NEXT_REQUEST
        )
        policy = entity.default_options[CACHE_POLICY_OPTION]

    original_get_voices = source.async_get_supported_voices

    def without_one_shot_voice(language):
        voices = original_get_voices(language)
        if language != "en-GB" or voices is None:
            return voices
        return [voice for voice in voices if voice.voice_id != "cheerful-gb"]

    source.async_get_supported_voices = without_one_shot_voice
    with (
        patch(
            "custom_components.adaptive_tts.tts.get_tts_entity",
            return_value=source,
        ),
        pytest.raises(HomeAssistantError, match="cheerful-gb"),
    ):
        await entity.async_resolve_request_for_preflight(
            "en-US", {CACHE_POLICY_OPTION: policy}
        )

    assert entity.next_voice_override is None


class _PreflightStream:
    """Minimal result stream whose synthesis should never start."""

    url = "/api/tts_proxy/preflight.mp3"
    extension = "mp3"
    language = "en-US"

    def __init__(self, options) -> None:
        self.options = options
        self.deleted = False
        self.message_stream = None

    def async_set_message_stream(self, message_stream) -> None:
        self.message_stream = message_stream

    async def async_stream_result(self):
        raise AssertionError(
            "preview synthesis should not start after failed preflight"
        )
        yield b""  # pragma: no cover

    def delete(self) -> None:
        self.deleted = True


@pytest.mark.asyncio
async def test_preview_preflight_clears_stale_persistent_override(
    hass, tmp_path
) -> None:
    """TTS Test clears a persistent voice rejected during its own preflight."""
    hass.config.config_dir = str(tmp_path)
    source = OverrideTTS()
    entry = make_entry()
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

    def without_persistent_voice(language):
        voices = original_get_voices(language)
        if language != "en-GB" or voices is None:
            return voices
        return [voice for voice in voices if voice.voice_id != "cheerful-gb"]

    source.async_get_supported_voices = without_persistent_voice
    stream = _PreflightStream({CACHE_POLICY_OPTION: policy})

    with (
        patch(
            "custom_components.adaptive_tts.preview.tts.async_create_stream",
            return_value=stream,
        ),
        patch(
            "custom_components.adaptive_tts.preview.get_engine_instance",
            return_value=entity,
        ),
        patch(
            "custom_components.adaptive_tts.tts.get_tts_entity",
            return_value=source,
        ),
        pytest.raises(HomeAssistantError, match="cheerful-gb"),
    ):
        await create_preview(
            hass,
            {
                "engine_id": "tts.adaptive",
                "language": "en-US",
                "options": {},
                "message": "Preview",
            },
        )

    assert stream.deleted is True
    assert entity.persistent_voice_override is None

    reloaded = AdaptiveTTSEntity(entry)
    reloaded.hass = hass
    await reloaded.async_load_voice_override(hass)
    assert reloaded.persistent_voice_override is None
