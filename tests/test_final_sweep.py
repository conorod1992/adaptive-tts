"""Regression tests for issues found in the final robustness sweep."""

from unittest.mock import patch

import pytest
from homeassistant.components.tts import TTSAudioRequest
from homeassistant.exceptions import HomeAssistantError

from custom_components.adaptive_tts.const import (
    CACHE_POLICY_OPTION,
    DURATION_UNTIL_CHANGED,
)
from custom_components.adaptive_tts.tts import AdaptiveTTSEntity

from .test_voice_overrides import OverrideTTS, attach, make_entry


def test_malformed_legacy_policy_marker_fails_cleanly(hass) -> None:
    """Malformed private legacy cache metadata raises a HA error, not ValueError."""
    source = OverrideTTS()
    entity = AdaptiveTTSEntity(make_entry())
    attach(entity, hass, source)

    with (
        patch("custom_components.adaptive_tts.tts.get_tts_entity", return_value=source),
        pytest.raises(HomeAssistantError, match="Invalid Adaptive TTS policy snapshot"),
    ):
        entity.resolve_request(
            "en-US",
            {CACHE_POLICY_OPTION: "quiet|incomplete"},
        )


@pytest.mark.asyncio
async def test_streaming_capability_failure_clears_persistent_override(
    hass, tmp_path
) -> None:
    """A provider capability exception is a request failure with normal recovery."""
    hass.config.config_dir = str(tmp_path)
    source = OverrideTTS()
    entity = AdaptiveTTSEntity(make_entry())
    attach(entity, hass, source)
    await entity.async_load_voice_override(hass)

    def fail_capability():
        raise RuntimeError("broken capability")

    async def message_gen():
        yield "Hello"

    source.async_supports_streaming_input = fail_capability
    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        await entity.async_set_voice_override(
            "en-GB", "cheerful-gb", DURATION_UNTIL_CHANGED
        )
        policy = entity.default_options[CACHE_POLICY_OPTION]
        with pytest.raises(HomeAssistantError, match="streaming capability"):
            await entity.async_stream_tts_audio(
                TTSAudioRequest(
                    "en-US",
                    {CACHE_POLICY_OPTION: policy},
                    message_gen(),
                )
            )

    assert entity.persistent_voice_override is None
