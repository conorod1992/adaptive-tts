"""Regression tests for Adaptive TTS backend robustness."""

import asyncio
from unittest.mock import patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_tts.const import (
    CONF_QUIET_END,
    CONF_QUIET_LANGUAGE,
    CONF_QUIET_MODE,
    CONF_QUIET_OPTION,
    CONF_QUIET_START,
    CONF_QUIET_VALUE,
    CONF_UNDERLYING_TTS_ENTITY,
    DOMAIN,
    DURATION_UNTIL_CHANGED,
    SCOPE_ALL,
)
from custom_components.adaptive_tts.preview import (
    _engine_infos,
    create_preview,
    websocket_engine,
)
from custom_components.adaptive_tts.services import _validate_voice_override_targets
from custom_components.adaptive_tts.tts import (
    AdaptiveTTSEntity,
    async_remove_voice_override_storage,
)

from .test_preview import FakeConnection
from .test_tts import MockTTS


def make_entry(
    provider: str = "tts.source",
    *,
    entry_id: str | None = None,
    quiet: bool = False,
    quiet_option: str = "voice",
    quiet_value: str = "normal",
    quiet_language: str | None = None,
) -> MockConfigEntry:
    """Create an entry suitable for robustness tests."""
    kwargs = {
        "domain": DOMAIN,
        "title": "Adaptive TTS",
        "data": {
            CONF_UNDERLYING_TTS_ENTITY: provider,
            CONF_QUIET_MODE: quiet,
            CONF_QUIET_START: "00:00:00" if quiet else "23:00:00",
            CONF_QUIET_END: "00:00:00" if quiet else "07:00:00",
            CONF_QUIET_OPTION: quiet_option,
            CONF_QUIET_VALUE: quiet_value,
            **(
                {CONF_QUIET_LANGUAGE: quiet_language}
                if quiet_language is not None
                else {}
            ),
        },
    }
    if entry_id is not None:
        kwargs["entry_id"] = entry_id
    return MockConfigEntry(**kwargs)


def attach(entity: AdaptiveTTSEntity, hass, source: MockTTS) -> None:
    """Attach test entities to Home Assistant."""
    entity.hass = hass
    source.hass = hass


def test_empty_enumerated_voice_list_rejects_override(hass) -> None:
    """An empty finite voice list means no arbitrary voice IDs are valid."""
    source = MockTTS()
    source.async_get_supported_voices = lambda language: []
    entity = AdaptiveTTSEntity(make_entry())
    attach(entity, hass, source)

    with (
        patch("custom_components.adaptive_tts.tts.get_tts_entity", return_value=source),
        pytest.raises(HomeAssistantError, match="not supported"),
    ):
        entity.validate_voice_override("en-US", "made-up")


def test_non_enumerable_voice_provider_allows_provider_specific_id(hass) -> None:
    """None still means Adaptive TTS cannot validate the provider's voice IDs."""
    source = MockTTS()
    source.async_get_supported_voices = lambda language: None
    entity = AdaptiveTTSEntity(make_entry())
    attach(entity, hass, source)

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        override = entity.validate_voice_override("en-US", "provider-specific")

    assert override.voice == "provider-specific"


@pytest.mark.asyncio
async def test_persistent_override_is_discarded_after_provider_change(
    hass, tmp_path
) -> None:
    """A stored voice from one provider never transfers to another provider."""
    hass.config.config_dir = str(tmp_path)
    old_entry = make_entry()
    source = MockTTS()
    first = AdaptiveTTSEntity(old_entry)
    attach(first, hass, source)
    await first.async_load_voice_override(hass)

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        await first.async_set_voice_override("en-US", "whisper", DURATION_UNTIL_CHANGED)
    assert first.persistent_voice_override is not None

    changed_entry = make_entry("tts.other", entry_id=old_entry.entry_id)
    changed = AdaptiveTTSEntity(changed_entry)
    changed.hass = hass
    await changed.async_load_voice_override(hass)
    assert changed.persistent_voice_override is None

    original_again = AdaptiveTTSEntity(old_entry)
    original_again.hass = hass
    await original_again.async_load_voice_override(hass)
    assert original_again.persistent_voice_override is None


@pytest.mark.asyncio
async def test_persistent_set_and_clear_are_serialized(hass) -> None:
    """A clear racing a blocked save cannot leave storage resurrected."""
    source = MockTTS()
    entity = AdaptiveTTSEntity(make_entry())
    attach(entity, hass, source)
    save_started = asyncio.Event()
    allow_save = asyncio.Event()

    class BlockingStore:
        data = None

        async def async_save(self, data):
            save_started.set()
            await allow_save.wait()
            self.data = dict(data)

        async def async_remove(self):
            self.data = None

    store = BlockingStore()
    entity._override_store = store

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        set_task = asyncio.create_task(
            entity.async_set_voice_override("en-US", "whisper", DURATION_UNTIL_CHANGED)
        )
        await save_started.wait()
        clear_task = asyncio.create_task(entity.async_clear_voice_override(SCOPE_ALL))
        await asyncio.sleep(0)
        assert not clear_task.done()
        allow_save.set()
        await asyncio.gather(set_task, clear_task)

    assert entity.persistent_voice_override is None
    assert store.data is None


@pytest.mark.asyncio
async def test_remove_entry_storage_cleans_persistent_override(hass, tmp_path) -> None:
    """Permanent config-entry removal deletes its private storage file."""
    hass.config.config_dir = str(tmp_path)
    entry = make_entry()
    source = MockTTS()
    entity = AdaptiveTTSEntity(entry)
    attach(entity, hass, source)
    await entity.async_load_voice_override(hass)

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        await entity.async_set_voice_override(
            "en-US", "whisper", DURATION_UNTIL_CHANGED
        )

    await async_remove_voice_override_storage(hass, entry)
    reloaded = AdaptiveTTSEntity(entry)
    reloaded.hass = hass
    await reloaded.async_load_voice_override(hass)
    assert reloaded.persistent_voice_override is None


def test_multi_target_validation_happens_before_mutation() -> None:
    """A bad later target is detected before callers mutate an earlier target."""
    calls = []

    class Target:
        def __init__(self, *, fail: bool = False) -> None:
            self.fail = fail

        def validate_voice_override(self, language, voice):
            calls.append((self.fail, language, voice))
            if self.fail:
                raise HomeAssistantError("unsupported voice")

    with pytest.raises(HomeAssistantError, match="unsupported voice"):
        _validate_voice_override_targets(
            [Target(), Target(fail=True)], "en-US", "voice-x"
        )

    assert calls == [
        (False, "en-US", "voice-x"),
        (True, "en-US", "voice-x"),
    ]


@pytest.mark.asyncio
async def test_preview_rejects_missing_provider_before_stream_allocation(hass) -> None:
    """Provider preflight fails before a temporary stream is allocated."""
    with (
        patch(
            "custom_components.adaptive_tts.preview.tts.async_create_stream"
        ) as create_stream,
        patch(
            "custom_components.adaptive_tts.preview.get_engine_instance",
            return_value=None,
        ),
        pytest.raises(HomeAssistantError, match="was not found"),
    ):
        await create_preview(
            hass,
            {"engine_id": "tts.missing", "message": "test", "options": {}},
        )

    create_stream.assert_not_called()


def test_websocket_engine_contains_broken_provider_metadata(hass) -> None:
    """A provider metadata exception becomes a WebSocket error, not a crash."""
    connection = FakeConnection()
    with patch(
        "custom_components.adaptive_tts.preview._engine_info",
        side_effect=RuntimeError("broken metadata"),
    ):
        websocket_engine.__wrapped__(
            hass,
            connection,
            {"id": 9, "engine_id": "tts.broken"},
        )

    assert connection.result is None
    assert connection.error is not None
    assert "broken metadata" in connection.error[2]


def test_provider_listing_skips_one_broken_provider(hass) -> None:
    """One broken custom provider does not prevent listing healthy providers."""
    hass.states.async_set("tts.good", "unknown")
    hass.states.async_set("tts.broken", "unknown")

    def info(_hass, engine_id, _language):
        if engine_id == "tts.broken":
            raise RuntimeError("broken metadata")
        return {"engine_id": engine_id}

    with patch("custom_components.adaptive_tts.preview._engine_info", side_effect=info):
        engines = _engine_infos(hass)

    assert engines == [{"engine_id": "tts.good"}]


def test_engine_metadata_distinguishes_none_from_empty_voice_list(hass) -> None:
    """Panel metadata reports whether the provider can enumerate voices."""
    source = MockTTS()
    source.hass = hass
    source.async_get_supported_voices = lambda language: []
    with patch(
        "custom_components.adaptive_tts.preview.get_engine_instance",
        return_value=source,
    ):
        from custom_components.adaptive_tts.preview import _engine_info

        info = _engine_info(hass, "tts.source", "en-US")
    assert info["voices"] == []
    assert info["voices_enumerated"] is True

    source.async_get_supported_voices = lambda language: None
    with patch(
        "custom_components.adaptive_tts.preview.get_engine_instance",
        return_value=source,
    ):
        info = _engine_info(hass, "tts.source", "en-US")
    assert info["voices"] == []
    assert info["voices_enumerated"] is False


def test_quiet_voice_removed_falls_back_to_normal_tts(hass) -> None:
    """A stale optional quiet voice must not take down otherwise-valid TTS."""
    source = MockTTS()
    entity = AdaptiveTTSEntity(
        make_entry(quiet=True, quiet_value="removed", quiet_language="en-GB")
    )
    attach(entity, hass, source)

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        resolved = entity.resolve_request("en-US", {"speed": "fast"})

    assert resolved.language == "en-US"
    assert resolved.options == {
        "voice": "normal",
        "format": "mp3",
        "speed": "fast",
    }
    assert resolved.quiet_mode_active is False


def test_removed_quiet_language_falls_back_to_request_language(hass) -> None:
    """An obsolete quiet-language choice falls back to normal request policy."""
    source = MockTTS()
    source._attr_supported_languages = ["en-US"]
    entity = AdaptiveTTSEntity(
        make_entry(quiet=True, quiet_value="whisper", quiet_language="en-GB")
    )
    attach(entity, hass, source)

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        resolved = entity.resolve_request("en-US", {})

    assert resolved.language == "en-US"
    assert resolved.options["voice"] == "normal"
    assert resolved.quiet_mode_active is False


def test_quiet_voice_metadata_failure_falls_back_to_normal_tts(hass) -> None:
    """A provider voice-catalogue failure cannot make quiet policy fatal."""
    source = MockTTS()
    source.async_get_supported_voices = lambda _language: (_ for _ in ()).throw(
        RuntimeError("voice catalogue offline")
    )
    entity = AdaptiveTTSEntity(
        make_entry(quiet=True, quiet_value="whisper", quiet_language="en-GB")
    )
    attach(entity, hass, source)

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        resolved = entity.resolve_request("en-US", {})

    assert resolved.language == "en-US"
    assert resolved.options["voice"] == "normal"
    assert resolved.quiet_mode_active is False


def test_removed_quiet_option_falls_back_to_normal_tts(hass) -> None:
    """A provider removing an optional quiet option leaves normal TTS usable."""
    source = MockTTS()
    entity = AdaptiveTTSEntity(
        make_entry(quiet=True, quiet_option="style", quiet_value="soft")
    )
    attach(entity, hass, source)

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity", return_value=source
    ):
        resolved = entity.resolve_request("en-US", {"speed": "slow"})

    assert resolved.language == "en-US"
    assert "style" not in resolved.options
    assert resolved.options["speed"] == "slow"
    assert resolved.quiet_mode_active is False


@pytest.mark.asyncio
async def test_malformed_override_storage_is_discarded(hass) -> None:
    """Malformed persisted state cannot block Adaptive TTS entity setup."""
    removed = False

    class MalformedStore:
        async def async_load(self):
            return ["not", "a", "mapping"]

        async def async_remove(self):
            nonlocal removed
            removed = True

    entity = AdaptiveTTSEntity(make_entry())
    entity.hass = hass
    with patch(
        "custom_components.adaptive_tts.tts._voice_override_store",
        return_value=MalformedStore(),
    ):
        await entity.async_load_voice_override(hass)

    assert entity.persistent_voice_override is None
    assert removed is True


@pytest.mark.asyncio
async def test_malformed_override_fields_are_discarded_even_if_cleanup_fails(
    hass,
) -> None:
    """Cleanup failure for corrupt state is logged rather than blocking setup."""

    class MalformedStore:
        async def async_load(self):
            return {"voice": 123, "language": ["en-US"]}

        async def async_remove(self):
            raise OSError("read-only storage")

    entity = AdaptiveTTSEntity(make_entry())
    entity.hass = hass
    with patch(
        "custom_components.adaptive_tts.tts._voice_override_store",
        return_value=MalformedStore(),
    ):
        await entity.async_load_voice_override(hass)

    assert entity.persistent_voice_override is None


@pytest.mark.asyncio
async def test_override_storage_load_failure_does_not_block_setup(hass) -> None:
    """Unreadable private storage degrades to no active persistent override."""

    class FailingStore:
        async def async_load(self):
            raise ValueError("corrupt JSON")

    entity = AdaptiveTTSEntity(make_entry())
    entity.hass = hass
    with patch(
        "custom_components.adaptive_tts.tts._voice_override_store",
        return_value=FailingStore(),
    ):
        await entity.async_load_voice_override(hass)

    assert entity.persistent_voice_override is None
