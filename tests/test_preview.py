"""Tests for the temporary preview backend."""

from typing import ClassVar
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.adaptive_tts.preview import (
    _engine_info,
    create_preview,
    websocket_generate,
)

from .test_tts import MockTTS


class FakeStream:
    """Minimal native TTS result stream test double."""

    url = "/api/tts_proxy/temporary.mp3"
    extension = "mp3"
    language = "en-US"
    options: ClassVar = {"voice": "normal", "format": "mp3"}

    def __init__(self) -> None:
        self.message_stream = None
        self.permanent_writes = 0

    def async_set_message_stream(self, message_stream) -> None:
        self.message_stream = message_stream

    async def async_stream_result(self):
        """Generate replayable audio as the real result stream does."""
        message = "".join([chunk async for chunk in self.message_stream])
        yield message.encode()

    def delete(self) -> None:
        """Record eager cleanup after a failed preview."""
        self.deleted = True


class FakeConnection:
    """Capture WebSocket handler responses."""

    def __init__(self) -> None:
        self.result = None
        self.error = None

    def send_result(self, message_id, result) -> None:
        self.result = (message_id, result)

    def send_error(self, message_id, code, message) -> None:
        self.error = (message_id, code, message)


@pytest.mark.asyncio
async def test_preview_uses_replayable_memory_only_native_stream(hass) -> None:
    """Preview generation returns an HA proxy URL and uses no permanent files."""
    source = MockTTS()
    source.hass = hass
    stream = FakeStream()
    with (
        patch(
            "custom_components.adaptive_tts.preview.tts.async_create_stream",
            return_value=stream,
        ),
        patch(
            "custom_components.adaptive_tts.preview.get_engine_instance",
            return_value=source,
        ),
    ):
        result = await create_preview(
            hass,
            {
                "engine_id": "tts.source",
                "language": "en-US",
                "options": {"voice": "normal"},
                "message": "Preview text",
            },
        )
    assert result["url"] == "/api/tts_proxy/temporary.mp3"
    assert result["underlying_entity_id"] == "tts.source"
    assert "in-memory" in result["storage"]
    assert stream.permanent_writes == 0
    assert stream.message_stream is not None


@pytest.mark.asyncio
async def test_preview_has_no_integration_owned_audio_store(hass) -> None:
    """Repeated previews are handed to HA and never accumulate in this integration."""
    source = MockTTS()
    source.hass = hass
    streams = [FakeStream(), FakeStream(), FakeStream()]
    with (
        patch(
            "custom_components.adaptive_tts.preview.tts.async_create_stream",
            side_effect=streams,
        ),
        patch(
            "custom_components.adaptive_tts.preview.get_engine_instance",
            return_value=source,
        ),
    ):
        results = [
            await create_preview(
                hass,
                {"engine_id": "tts.source", "message": str(index), "options": {}},
            )
            for index in range(3)
        ]
    assert len(results) == 3
    assert all(stream.message_stream is not None for stream in streams)
    assert not hasattr(hass.data.get("adaptive_tts", {}), "preview_audio")


@pytest.mark.asyncio
async def test_generate_websocket_handler_returns_preview_metadata(hass) -> None:
    """The WebSocket command sends preview metadata to its caller."""
    connection = FakeConnection()
    expected = {"url": "/api/tts_proxy/test.mp3"}
    with patch(
        "custom_components.adaptive_tts.preview.create_preview",
        new=AsyncMock(return_value=expected),
    ):
        await websocket_generate.__wrapped__.__wrapped__(
            hass,
            connection,
            {"id": 7, "engine_id": "tts.adaptive", "message": "test", "options": {}},
        )
    assert connection.result == (7, expected)
    assert connection.error is None


@pytest.mark.asyncio
async def test_preview_reports_provider_failure_during_synthesis(hass) -> None:
    """A provider error raised while loading audio fails the WebSocket request."""
    source = MockTTS()
    source.hass = hass
    stream = FakeStream()

    async def fail_during_synthesis():
        raise RuntimeError("provider quota exhausted")
        yield b""  # pragma: no cover

    stream.async_stream_result = fail_during_synthesis
    connection = FakeConnection()
    with (
        patch(
            "custom_components.adaptive_tts.preview.tts.async_create_stream",
            return_value=stream,
        ),
        patch(
            "custom_components.adaptive_tts.preview.get_engine_instance",
            return_value=source,
        ),
    ):
        await websocket_generate.__wrapped__.__wrapped__(
            hass,
            connection,
            {"id": 8, "engine_id": "tts.source", "message": "test", "options": {}},
        )

    assert connection.result is None
    assert connection.error is not None
    assert "provider quota exhausted" in connection.error[2]
    assert stream.deleted is True


def test_frontend_clears_stale_results_and_handles_audio_errors() -> None:
    """The panel clears old metadata and reports proxy playback failures."""
    from pathlib import Path

    panel = Path(
        "custom_components/adaptive_tts/frontend/adaptive-tts-panel.js"
    ).read_text()
    assert "this._clearResult();" in panel
    assert 'addEventListener("error"' in panel
    assert "Preview audio could not be retrieved" in panel


def test_unavailable_provider_metadata_skips_voice_probe(hass) -> None:
    """Unavailable providers remain visible without probing optional voice metadata."""

    class UnavailableTTS(MockTTS):
        _attr_available = False

        def async_get_supported_voices(self, language):
            raise AssertionError("voice metadata must not be queried while unavailable")

    source = UnavailableTTS()
    source.hass = hass
    with patch(
        "custom_components.adaptive_tts.preview.get_engine_instance",
        return_value=source,
    ):
        info = _engine_info(hass, "tts.source", "en-US")

    assert info["available"] is False
    assert info["voices"] == []
    assert info["voices_enumerated"] is False


def test_voice_metadata_failure_does_not_hide_provider(hass) -> None:
    """A broken optional voice catalogue degrades to free-text voice metadata."""
    source = MockTTS()
    source.hass = hass
    with (
        patch(
            "custom_components.adaptive_tts.preview.get_engine_instance",
            return_value=source,
        ),
        patch.object(
            source,
            "async_get_supported_voices",
            side_effect=RuntimeError("voice catalogue offline"),
        ),
    ):
        info = _engine_info(hass, "tts.source", "en-US")

    assert info["available"] is True
    assert info["voices"] == []
    assert info["voices_enumerated"] is False


@pytest.mark.asyncio
async def test_preview_rejects_unavailable_provider_before_allocating_stream(
    hass,
) -> None:
    """Unavailable providers fail before Home Assistant registers a preview stream."""
    source = MockTTS()
    source._attr_available = False
    source.hass = hass
    with (
        patch(
            "custom_components.adaptive_tts.preview.get_engine_instance",
            return_value=source,
        ),
        patch(
            "custom_components.adaptive_tts.preview.tts.async_create_stream"
        ) as create_stream,
    ):
        with pytest.raises(HomeAssistantError, match="currently unavailable"):
            await create_preview(
                hass,
                {"engine_id": "tts.source", "message": "test", "options": {}},
            )

    create_stream.assert_not_called()
