"""Regression tests for provider metadata and control-plane resilience."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.exceptions import HomeAssistantError

from custom_components.adaptive_tts.config_flow import (
    _override_error,
    _override_selector,
)
from custom_components.adaptive_tts.const import (
    CONF_UNDERLYING_TTS_ENTITY,
    DATA_ENTITIES,
    DOMAIN,
)
from custom_components.adaptive_tts.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.adaptive_tts.tts import AdaptiveTTSEntity

from .test_tts import MockTTS, make_entry


class BrokenOptionsTTS(MockTTS):
    """Provider whose option metadata fails."""

    @property
    def supported_options(self):
        raise RuntimeError("option metadata failed")


class BrokenDiagnosticsTTS(MockTTS):
    """Provider with independently broken diagnostic metadata."""

    @property
    def supported_languages(self):
        raise RuntimeError("language metadata failed")

    @property
    def supported_options(self):
        raise RuntimeError("option metadata failed")


@pytest.mark.asyncio
async def test_config_flow_contains_provider_metadata_failure(hass) -> None:
    """Broken provider metadata produces a form error instead of an unknown error."""
    source = BrokenOptionsTTS()
    source.hass = hass
    hass.states.async_set("tts.source", "unknown")
    with (
        patch(
            "custom_components.adaptive_tts.config_flow.get_tts_entity",
            return_value=source,
        ),
        patch(
            "custom_components.adaptive_tts.config_flow.is_adaptive_entity",
            return_value=False,
        ),
        patch(
            "custom_components.adaptive_tts.config_flow.selectable_tts_entities",
            return_value=["tts.source"],
        ),
        patch(
            "homeassistant.config_entries.async_process_deps_reqs",
            new=AsyncMock(),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"name": "Safe TTS", CONF_UNDERLYING_TTS_ENTITY: "tts.source"},
        )

    assert result["step_id"] == "policy"
    assert result["errors"]["base"] == "provider_details_unavailable"


def test_voice_catalogue_failure_is_bounded_in_config_helpers() -> None:
    """A broken voice catalogue cannot crash selector construction or validation."""
    source = MockTTS()

    def fail_voices(_language):
        raise RuntimeError("voice metadata failed")

    source.async_get_supported_voices = fail_voices
    selector = _override_selector(source, "voice", "en-US")
    assert selector.config["type"] == "text"
    assert (
        _override_error(source, "voice", "en-US", "provider-voice")
        == "provider_details_unavailable"
    )


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
    entry = make_entry(quiet=True)
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
