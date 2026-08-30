"""Regression tests for Adaptive TTS request policy snapshots."""

from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from homeassistant.components import tts as ha_tts
from homeassistant.components.tts import TextToSpeechEntity, Voice
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_tts.const import (
    CACHE_POLICY_OPTION,
    CONF_QUIET_END,
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


class SnapshotTTS(TextToSpeechEntity):
    """Underlying provider whose audio identifies the effective voice."""

    _attr_name = "Snapshot source"
    _attr_default_language = "en-US"
    _attr_supported_languages: ClassVar = ["en-US"]
    _attr_supported_options: ClassVar = ["voice"]

    def __init__(self, default_voice: str = "normal") -> None:
        self._attr_default_options = {"voice": default_voice}
        self.default_voice = default_voice
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.fail_generation = False

    def async_get_supported_voices(self, language: str) -> list[Voice] | None:
        return [
            Voice(self.default_voice, self.default_voice),
            Voice("voice-a", "Voice A"),
            Voice("voice-b", "Voice B"),
        ]

    async def async_get_tts_audio(self, message, language, options):
        if self.fail_generation:
            raise HomeAssistantError("provider rejected request")
        self.calls.append((message, language, dict(options)))
        return "mp3", options["voice"].encode()


def make_entry(
    *,
    provider: str = "tts.source",
    quiet: bool = False,
    quiet_voice: str = "voice-a",
) -> MockConfigEntry:
    """Create an Adaptive TTS entry for snapshot tests."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Adaptive TTS",
        data={
            CONF_UNDERLYING_TTS_ENTITY: provider,
            CONF_QUIET_MODE: quiet,
            CONF_QUIET_START: "00:00:00",
            CONF_QUIET_END: "00:00:00",
            CONF_QUIET_OPTION: "voice",
            CONF_QUIET_VALUE: quiet_voice,
        },
    )


def attach(entity: AdaptiveTTSEntity, hass, *sources: SnapshotTTS) -> None:
    """Attach entities to the test Home Assistant instance."""
    entity.hass = hass
    for source in sources:
        source.hass = hass


async def setup_tts_manager(hass, tmp_path) -> None:
    """Set up HA's real in-memory TTS manager."""
    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, "tts", {"tts": [{"cache": False}]})
    hass.data[ha_tts.DATA_TTS_MANAGER].use_file_cache = False


@pytest.mark.asyncio
async def test_persistent_snapshot_survives_override_change_and_cache_matches_audio(
    hass, tmp_path
) -> None:
    """An in-flight request keeps the override represented by its cache key."""
    await setup_tts_manager(hass, tmp_path)
    source = SnapshotTTS()
    entity = AdaptiveTTSEntity(make_entry())
    attach(entity, hass, source)
    await entity.async_load_voice_override(hass)

    def engine_for_id(_hass, engine_id):
        return entity if engine_id == "tts.adaptive" else source

    async def internal_get(message, language, options):
        return await entity.async_get_tts_audio(message, language, options)

    async def internal_stream(request):
        return await entity.async_stream_tts_audio(request)

    with (
        patch("custom_components.adaptive_tts.tts.get_tts_entity", return_value=source),
        patch(
            "homeassistant.components.tts.get_engine_instance",
            side_effect=engine_for_id,
        ),
        patch.object(entity, "async_internal_get_tts_audio", side_effect=internal_get),
        patch.object(
            entity,
            "internal_async_stream_tts_audio",
            side_effect=internal_stream,
        ),
    ):
        await entity.async_set_voice_override(
            "en-US", "voice-a", DURATION_UNTIL_CHANGED
        )
        first = ha_tts.async_create_stream(hass, "tts.adaptive", options={})

        await entity.async_set_voice_override(
            "en-US", "voice-b", DURATION_UNTIL_CHANGED
        )
        second = ha_tts.async_create_stream(hass, "tts.adaptive", options={})

        first.async_set_message("Same text")
        first_audio = b"".join([chunk async for chunk in first.async_stream_result()])
        second.async_set_message("Same text")
        second_audio = b"".join([chunk async for chunk in second.async_stream_result()])

        await entity.async_clear_voice_override(SCOPE_ALL)
        normal = ha_tts.async_create_stream(hass, "tts.adaptive", options={})
        normal.async_set_message("Same text")
        normal_audio = b"".join([chunk async for chunk in normal.async_stream_result()])

    assert first_audio == b"voice-a"
    assert second_audio == b"voice-b"
    assert normal_audio == b"normal"
    assert [call[2]["voice"] for call in source.calls] == [
        "voice-a",
        "voice-b",
        "normal",
    ]
    assert first.options[CACHE_POLICY_OPTION] != second.options[CACHE_POLICY_OPTION]
    assert second.options[CACHE_POLICY_OPTION] != normal.options[CACHE_POLICY_OPTION]


@pytest.mark.asyncio
async def test_concurrent_prepared_streams_do_not_share_one_shot_cache_entry(
    hass, tmp_path
) -> None:
    """Only one of two prepared streams may consume a next-request override."""
    await setup_tts_manager(hass, tmp_path)
    source = SnapshotTTS()
    entity = AdaptiveTTSEntity(make_entry())
    attach(entity, hass, source)
    await entity.async_load_voice_override(hass)

    def engine_for_id(_hass, engine_id):
        return entity if engine_id == "tts.adaptive" else source

    async def internal_get(message, language, options):
        return await entity.async_get_tts_audio(message, language, options)

    async def internal_stream(request):
        return await entity.async_stream_tts_audio(request)

    with (
        patch("custom_components.adaptive_tts.tts.get_tts_entity", return_value=source),
        patch(
            "homeassistant.components.tts.get_engine_instance",
            side_effect=engine_for_id,
        ),
        patch.object(entity, "async_internal_get_tts_audio", side_effect=internal_get),
        patch.object(
            entity,
            "internal_async_stream_tts_audio",
            side_effect=internal_stream,
        ),
    ):
        await entity.async_set_voice_override("en-US", "voice-a", DURATION_NEXT_REQUEST)
        first = ha_tts.async_create_stream(hass, "tts.adaptive", options={})
        second = ha_tts.async_create_stream(hass, "tts.adaptive", options={})

        assert first.options[CACHE_POLICY_OPTION] != second.options[CACHE_POLICY_OPTION]

        first.async_set_message("Same text")
        first_audio = b"".join([chunk async for chunk in first.async_stream_result()])
        second.async_set_message("Same text")
        second_audio = b"".join([chunk async for chunk in second.async_stream_result()])

    assert first_audio == b"voice-a"
    assert second_audio == b"normal"
    assert entity.next_voice_override is None
    assert [call[2]["voice"] for call in source.calls] == ["voice-a", "normal"]


@pytest.mark.asyncio
async def test_failed_old_snapshot_does_not_clear_replacement_of_same_voice(
    hass, tmp_path
) -> None:
    """A stale request cannot clear a newer generation of the same override."""
    hass.config.config_dir = str(tmp_path)
    source = SnapshotTTS()
    entity = AdaptiveTTSEntity(make_entry())
    attach(entity, hass, source)
    await entity.async_load_voice_override(hass)

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        await entity.async_set_voice_override(
            "en-US", "voice-a", DURATION_UNTIL_CHANGED
        )
        old_policy = entity.default_options[CACHE_POLICY_OPTION]
        old_token = entity.persistent_voice_override.token

        await entity.async_set_voice_override(
            "en-US", "voice-a", DURATION_UNTIL_CHANGED
        )
        replacement = entity.persistent_voice_override
        assert replacement is not None
        assert replacement.token != old_token

        source.fail_generation = True
        with pytest.raises(HomeAssistantError, match="provider rejected request"):
            await entity.async_get_tts_audio(
                "Old request", "en-US", {CACHE_POLICY_OPTION: old_policy}
            )

    assert entity.persistent_voice_override == replacement


def test_quiet_policy_snapshot_survives_config_change(hass) -> None:
    """An already prepared request keeps the quiet voice in its cache snapshot."""
    source = SnapshotTTS()
    entry = make_entry(quiet=True, quiet_voice="voice-a")
    entry.add_to_hass(hass)
    entity = AdaptiveTTSEntity(entry)
    attach(entity, hass, source)

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        old_policy = entity.default_options[CACHE_POLICY_OPTION]
        hass.config_entries.async_update_entry(
            entry, options={CONF_QUIET_VALUE: "voice-b"}
        )
        new_policy = entity.default_options[CACHE_POLICY_OPTION]

        old_request = entity.resolve_request("en-US", {CACHE_POLICY_OPTION: old_policy})
        new_request = entity.resolve_request("en-US", {CACHE_POLICY_OPTION: new_policy})

    assert old_request.options["voice"] == "voice-a"
    assert new_request.options["voice"] == "voice-b"
    assert old_policy != new_policy


@pytest.mark.asyncio
async def test_provider_snapshot_survives_wrapped_provider_change(hass) -> None:
    """An in-flight request delegates to the provider captured in its cache key."""
    source_a = SnapshotTTS("normal-a")
    source_b = SnapshotTTS("normal-b")
    entry = make_entry(provider="tts.source_a")
    entry.add_to_hass(hass)
    entity = AdaptiveTTSEntity(entry)
    attach(entity, hass, source_a, source_b)

    def source_for_id(_hass, entity_id):
        if entity_id == "tts.source_a":
            return source_a
        if entity_id == "tts.source_b":
            return source_b
        return None

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity",
        side_effect=source_for_id,
    ):
        old_policy = entity.default_options[CACHE_POLICY_OPTION]
        hass.config_entries.async_update_entry(
            entry, options={CONF_UNDERLYING_TTS_ENTITY: "tts.source_b"}
        )
        new_policy = entity.default_options[CACHE_POLICY_OPTION]

        old_request = entity.resolve_request("en-US", {CACHE_POLICY_OPTION: old_policy})
        new_request = entity.resolve_request("en-US", {CACHE_POLICY_OPTION: new_policy})
        _extension, old_audio = await entity.async_get_tts_audio(
            "Old provider", "en-US", {CACHE_POLICY_OPTION: old_policy}
        )
        _extension, new_audio = await entity.async_get_tts_audio(
            "New provider", "en-US", {CACHE_POLICY_OPTION: new_policy}
        )

    assert old_request.underlying_entity_id == "tts.source_a"
    assert new_request.underlying_entity_id == "tts.source_b"
    assert old_audio == b"normal-a"
    assert new_audio == b"normal-b"
    assert len(source_a.calls) == 1
    assert len(source_b.calls) == 1
