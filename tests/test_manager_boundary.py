"""Regression tests for the Home Assistant TTS manager boundary."""

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from homeassistant.components import tts as ha_tts
from homeassistant.components.tts import (
    TextToSpeechEntity,
    TTSAudioRequest,
    TTSAudioResponse,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_tts.const import (
    CONF_QUIET_END,
    CONF_QUIET_MODE,
    CONF_QUIET_OPTION,
    CONF_QUIET_START,
    CONF_QUIET_VALUE,
    CONF_UNDERLYING_TTS_ENTITY,
    DOMAIN,
)
from custom_components.adaptive_tts.tts import AdaptiveTTSEntity


class ManagerTTS(TextToSpeechEntity):
    """Controllable non-streaming provider for manager-boundary tests."""

    _attr_name = "Manager source"
    _attr_default_language = "en-US"
    _attr_supported_languages: ClassVar = ["en-US"]
    _attr_supported_options: ClassVar = ["voice"]
    _attr_default_options: ClassVar = {"voice": "normal"}

    def __init__(self, audio: bytes) -> None:
        self.audio = audio
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def async_get_tts_audio(self, message, language, options):
        self.calls.append((message, language, dict(options)))
        return "mp3", self.audio


class StreamingManagerTTS(ManagerTTS):
    """Streaming-only provider whose one-shot path must never be used."""

    def __init__(self, audio: bytes) -> None:
        super().__init__(audio)
        self.stream_calls: list[tuple[str, str, dict[str, Any]]] = []

    async def async_get_tts_audio(self, message, language, options):
        raise HomeAssistantError("streaming provider used one-shot path")

    async def async_stream_tts_audio(
        self, request: TTSAudioRequest
    ) -> TTSAudioResponse:
        message = "".join([chunk async for chunk in request.message_gen])
        self.stream_calls.append((message, request.language, dict(request.options)))

        async def data_gen():
            yield self.audio

        return TTSAudioResponse("mp3", data_gen())


def make_entry(provider: str = "tts.source_a") -> MockConfigEntry:
    """Create an Adaptive TTS entry for manager-boundary tests."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Adaptive TTS",
        data={
            CONF_UNDERLYING_TTS_ENTITY: provider,
            CONF_QUIET_MODE: False,
            CONF_QUIET_START: "23:00:00",
            CONF_QUIET_END: "07:00:00",
            CONF_QUIET_OPTION: "voice",
            CONF_QUIET_VALUE: "",
        },
    )


async def setup_tts_manager(hass, tmp_path) -> None:
    """Set up Home Assistant's real TTS manager without disk caching."""
    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, "tts", {"tts": [{"cache": False}]})
    hass.data[ha_tts.DATA_TTS_MANAGER].use_file_cache = False


def attach(entity: AdaptiveTTSEntity, hass, *sources: TextToSpeechEntity) -> None:
    """Attach wrapper and providers to the test Home Assistant instance."""
    entity.hass = hass
    for source in sources:
        source.hass = hass


def provider_lookup(source_a, source_b):
    """Build a provider lookup that honors the snapshot's provider ID."""

    def lookup(_hass, entity_id):
        if entity_id == "tts.source_a":
            return source_a
        if entity_id == "tts.source_b":
            return source_b
        return None

    return lookup


def engine_lookup(entity, source_a, source_b):
    """Build Home Assistant's engine lookup for the real TTS manager."""

    def lookup(_hass, entity_id):
        if entity_id == "tts.adaptive":
            return entity
        if entity_id == "tts.source_a":
            return source_a
        if entity_id == "tts.source_b":
            return source_b
        return None

    return lookup


@pytest.mark.asyncio
async def test_prepared_stream_keeps_streaming_provider_after_provider_change(
    hass, tmp_path
) -> None:
    """HA cannot reroute an old streaming request using a newer provider's contract."""
    await setup_tts_manager(hass, tmp_path)
    source_a = StreamingManagerTTS(b"source-a")
    source_b = ManagerTTS(b"source-b")
    entry = make_entry()
    entry.add_to_hass(hass)
    entity = AdaptiveTTSEntity(entry)
    attach(entity, hass, source_a, source_b)

    async def message_gen():
        yield "Prepared"
        yield " request"

    async def internal_get(message, language, options):
        return await entity.async_get_tts_audio(message, language, options)

    async def internal_stream(request):
        return await entity.async_stream_tts_audio(request)

    with (
        patch(
            "custom_components.adaptive_tts.tts.get_tts_entity",
            side_effect=provider_lookup(source_a, source_b),
        ),
        patch(
            "homeassistant.components.tts.get_engine_instance",
            side_effect=engine_lookup(entity, source_a, source_b),
        ),
        patch.object(entity, "async_internal_get_tts_audio", side_effect=internal_get),
        patch.object(
            entity,
            "internal_async_stream_tts_audio",
            side_effect=internal_stream,
        ),
    ):
        prepared = ha_tts.async_create_stream(hass, "tts.adaptive", options={})
        assert prepared.supports_streaming_input is True

        hass.config_entries.async_update_entry(
            entry,
            options={CONF_UNDERLYING_TTS_ENTITY: "tts.source_b"},
        )

        prepared.async_set_message_stream(message_gen())
        audio = b"".join([chunk async for chunk in prepared.async_stream_result()])

    assert audio == b"source-a"
    assert source_a.stream_calls == [("Prepared request", "en-US", {"voice": "normal"})]
    assert source_a.calls == []
    assert source_b.calls == []


@pytest.mark.asyncio
async def test_preferred_output_hint_stays_manager_owned_after_provider_change(
    hass, tmp_path
) -> None:
    """A newer provider cannot make HA leak output hints into an old provider."""
    await setup_tts_manager(hass, tmp_path)
    source_a = ManagerTTS(b"source-a")
    source_b = ManagerTTS(b"source-b")
    source_b._attr_supported_options = ["voice", ha_tts.ATTR_PREFERRED_FORMAT]
    entry = make_entry()
    entry.add_to_hass(hass)
    entity = AdaptiveTTSEntity(entry)
    attach(entity, hass, source_a, source_b)

    async def internal_get(message, language, options):
        return await entity.async_get_tts_audio(message, language, options)

    async def internal_stream(request):
        return await entity.async_stream_tts_audio(request)

    async def passthrough_conversion(_hass, _extension, audio_input, *args, **kwargs):
        async for chunk in audio_input:
            yield chunk

    with (
        patch(
            "custom_components.adaptive_tts.tts.get_tts_entity",
            side_effect=provider_lookup(source_a, source_b),
        ),
        patch(
            "homeassistant.components.tts.get_engine_instance",
            side_effect=engine_lookup(entity, source_a, source_b),
        ),
        patch.object(entity, "async_internal_get_tts_audio", side_effect=internal_get),
        patch.object(
            entity,
            "internal_async_stream_tts_audio",
            side_effect=internal_stream,
        ),
        patch(
            "homeassistant.components.tts._async_convert_audio",
            new=passthrough_conversion,
        ),
    ):
        prepared = ha_tts.async_create_stream(
            hass,
            "tts.adaptive",
            options={ha_tts.ATTR_PREFERRED_FORMAT: "wav"},
        )
        hass.config_entries.async_update_entry(
            entry,
            options={CONF_UNDERLYING_TTS_ENTITY: "tts.source_b"},
        )

        prepared.async_set_message("Format test")
        audio = b"".join([chunk async for chunk in prepared.async_stream_result()])

    assert audio == b"source-a"
    assert len(source_a.calls) == 1
    assert ha_tts.ATTR_PREFERRED_FORMAT not in source_a.calls[0][2]
    assert source_b.calls == []


def test_wrapper_contract_is_stable_across_provider_capabilities(hass) -> None:
    """Wrapper routing and output conversion metadata do not vary by provider."""
    source = ManagerTTS(b"source")
    source._attr_supported_options = [
        "voice",
        ha_tts.ATTR_PREFERRED_FORMAT,
        ha_tts.ATTR_PREFERRED_SAMPLE_RATE,
        ha_tts.ATTR_PREFERRED_SAMPLE_CHANNELS,
        ha_tts.ATTR_PREFERRED_SAMPLE_BYTES,
        "preferred_bitrate",
    ]
    entity = AdaptiveTTSEntity(make_entry())
    attach(entity, hass, source)

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        assert entity.async_supports_streaming_input() is True
        assert entity.supported_options == ["voice"]
