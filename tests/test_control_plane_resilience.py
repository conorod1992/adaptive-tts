"""Regression tests for provider metadata and control-plane resilience."""

from unittest.mock import patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.adaptive_tts.const import DATA_ENTITIES, DOMAIN
from custom_components.adaptive_tts.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.adaptive_tts.tts import AdaptiveTTSEntity

from .test_tts import MockTTS, make_entry


class BrokenDiagnosticsTTS(MockTTS):
    """Provider with independently broken diagnostic metadata."""

    @property
    def supported_languages(self):
        raise RuntimeError("language metadata failed")

    @property
    def supported_options(self):
        raise RuntimeError("option metadata failed")


def test_explicit_override_metadata_failure_becomes_home_assistant_error(hass) -> None:
    """Service validation never leaks a provider's arbitrary metadata exception."""
    source = MockTTS()
    source.hass = hass

    def fail_voices(_language):
        raise RuntimeError("voice metadata failed")

    source.async_get_supported_voices = fail_voices
    entity = AdaptiveTTSEntity(make_entry())
    entity.hass = hass
    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        with pytest.raises(
            HomeAssistantError, match="Could not read TTS provider metadata"
        ):
            entity.validate_voice_override("en-US", "normal")


@pytest.mark.asyncio
async def test_diagnostics_return_partial_data_when_provider_metadata_fails(
    hass,
) -> None:
    """Diagnostics stay available when optional provider metadata is broken."""
    source = BrokenDiagnosticsTTS()
    source.hass = hass
    entry = make_entry()
    hass.data[DOMAIN] = {DATA_ENTITIES: {}}

    with patch(
        "custom_components.adaptive_tts.diagnostics.get_tts_entity",
        return_value=source,
    ):
        result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["underlying_exists"] is True
    assert result["supported_languages"] == []
    assert result["supported_options"] == []
    assert "supported_languages" in result["provider_metadata_errors"]
    assert "supported_options" in result["provider_metadata_errors"]
