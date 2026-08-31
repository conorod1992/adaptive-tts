"""Regression tests for the final release-readiness sweep."""

import asyncio
from unittest.mock import patch

import pytest

from custom_components.adaptive_tts.const import (
    DATA_ENTITIES,
    DOMAIN,
    SCOPE_PERSISTENT,
)
from custom_components.adaptive_tts.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.adaptive_tts.preview import _engine_info, create_preview
from custom_components.adaptive_tts.tts import AdaptiveTTSEntity, VoiceOverride

from .test_preview import FakeStream
from .test_tts import MockTTS, make_entry


class _RemoveFailsStore:
    """Storage double whose removal fails but neutralizing save succeeds."""

    def __init__(self) -> None:
        self.data = {"voice": "stale"}

    async def async_remove(self) -> None:
        raise RuntimeError("remove failed")

    async def async_save(self, data) -> None:
        self.data = dict(data)


class _BrokenLanguagesTTS(MockTTS):
    """Provider that exposes availability but fails one metadata property."""

    @property
    def supported_languages(self):
        raise RuntimeError("provider-secret-token")


@pytest.mark.asyncio
async def test_failed_persistent_override_cleanup_neutralizes_storage(hass) -> None:
    """A Store.remove failure cannot resurrect a rejected override on restart."""
    entity = AdaptiveTTSEntity(make_entry())
    entity.hass = hass
    override = VoiceOverride("stale", "en-US", "persistent-token")
    store = _RemoveFailsStore()
    entity._persistent_voice_override = override
    entity._override_store = store

    await entity._async_clear_failed_voice_override(override, SCOPE_PERSISTENT)

    assert entity.persistent_voice_override is None
    assert store.data == {}


def test_panel_engine_metadata_failure_keeps_provider_visible(hass) -> None:
    """One broken metadata field degrades in place instead of hiding the entity."""
    source = _BrokenLanguagesTTS()
    source.hass = hass
    with patch(
        "custom_components.adaptive_tts.preview.get_engine_instance",
        return_value=source,
    ):
        info = _engine_info(hass, "tts.source", None)

    assert info["engine_id"] == "tts.source"
    assert info["available"] is True
    assert info["supported_languages"] == []
    assert info["metadata_errors"]["supported_languages"] == "RuntimeError"
    assert "provider-secret-token" not in str(info["metadata_errors"])


@pytest.mark.asyncio
async def test_cancelled_preview_deletes_temporary_stream(hass) -> None:
    """Cancellation eagerly removes the temporary HA result-stream token."""
    source = MockTTS()
    source.hass = hass
    stream = FakeStream()

    async def cancelled_stream():
        raise asyncio.CancelledError
        yield b""  # pragma: no cover

    stream.async_stream_result = cancelled_stream
    with (
        patch(
            "custom_components.adaptive_tts.preview.tts.async_create_stream",
            return_value=stream,
        ),
        patch(
            "custom_components.adaptive_tts.preview.get_engine_instance",
            return_value=source,
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await create_preview(
            hass,
            {"engine_id": "tts.source", "message": "test", "options": {}},
        )

    assert stream.deleted is True


@pytest.mark.asyncio
async def test_diagnostics_redact_provider_exception_messages(hass) -> None:
    """Shareable diagnostics retain the error type without provider error text."""
    source = _BrokenLanguagesTTS()
    source.hass = hass
    entry = make_entry()
    hass.data[DOMAIN] = {DATA_ENTITIES: {}}

    with patch(
        "custom_components.adaptive_tts.diagnostics.get_tts_entity",
        return_value=source,
    ):
        result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["provider_metadata_errors"]["supported_languages"] == "RuntimeError"
    assert "provider-secret-token" not in str(result)
