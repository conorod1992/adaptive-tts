"""Tests for the temporary preview backend."""

from typing import ClassVar
from unittest.mock import patch

import pytest

from custom_components.adaptive_tts.preview import create_preview, websocket_generate

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
        result = create_preview(
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
    assert result["quiet_mode_active"] is False
    assert "in-memory" in result["storage"]
    assert stream.permanent_writes == 0
    assert "".join([chunk async for chunk in stream.message_stream]) == "Preview text"


def test_preview_has_no_integration_owned_audio_store(hass) -> None:
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
            create_preview(
                hass,
                {"engine_id": "tts.source", "message": str(index), "options": {}},
            )
            for index in range(3)
        ]
    assert len(results) == 3
    assert all(stream.message_stream is not None for stream in streams)
    assert not hasattr(hass.data.get("adaptive_tts", {}), "preview_audio")


def test_generate_websocket_handler_returns_preview_metadata(hass) -> None:
    """The WebSocket command sends preview metadata to its caller."""
    connection = FakeConnection()
    expected = {"url": "/api/tts_proxy/test.mp3", "quiet_mode_active": True}
    with patch(
        "custom_components.adaptive_tts.preview.create_preview",
        return_value=expected,
    ):
        websocket_generate.__wrapped__(
            hass,
            connection,
            {"id": 7, "engine_id": "tts.adaptive", "message": "test", "options": {}},
        )
    assert connection.result == (7, expected)
    assert connection.error is None
