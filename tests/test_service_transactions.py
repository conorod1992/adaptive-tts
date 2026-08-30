"""Regression tests for atomic multi-target override services."""

from unittest.mock import patch

import pytest

from custom_components.adaptive_tts.const import (
    DURATION_UNTIL_CHANGED,
    SCOPE_ALL,
)
from custom_components.adaptive_tts.services import (
    _async_clear_voice_override_targets,
    _async_set_voice_override_targets,
)
from custom_components.adaptive_tts.tts import (
    AdaptiveTTSEntity,
    VoiceOverride,
)

from .test_backend_robustness import attach, make_entry
from .test_tts import MockTTS


class _TransactionalStore:
    """Store stub that can fail after a partial persistent write."""

    def __init__(self, data, *, fail_save_voice=None, fail_remove=False):
        self.data = dict(data) if data is not None else None
        self.fail_save_voice = fail_save_voice
        self.fail_remove = fail_remove

    async def async_save(self, data):
        self.data = dict(data)
        if self.fail_save_voice == data.get("voice"):
            self.fail_save_voice = None
            raise RuntimeError("simulated save failure")

    async def async_remove(self):
        self.data = None
        if self.fail_remove:
            self.fail_remove = False
            raise RuntimeError("simulated remove failure")


def _stored_override(entity, override):
    return {
        "underlying_entity_id": entity.underlying_entity_id,
        "language": override.language,
        "voice": override.voice,
        "token": override.token,
    }


def _seed_state(entity, persistent, next_request, store):
    entity._persistent_voice_override = persistent
    entity._next_voice_override = next_request
    entity._override_store = store


@pytest.mark.asyncio
async def test_persistent_set_rolls_back_partial_multi_target_write(
    hass,
) -> None:
    """A later Set failure restores every attempted target exactly."""
    source = MockTTS()
    first = AdaptiveTTSEntity(make_entry(entry_id="first"))
    second = AdaptiveTTSEntity(make_entry(entry_id="second"))
    attach(first, hass, source)
    attach(second, hass, source)
    old_first = VoiceOverride("normal", "en-US", "persist-first")
    old_second = VoiceOverride("normal", "en-US", "persist-second")
    next_first = VoiceOverride("whisper", "en-US", "next-first")
    next_second = VoiceOverride("whisper", "en-US", "next-second")
    first_store = _TransactionalStore(_stored_override(first, old_first))
    second_store = _TransactionalStore(
        _stored_override(second, old_second), fail_save_voice="whisper"
    )
    _seed_state(first, old_first, next_first, first_store)
    _seed_state(second, old_second, next_second, second_store)

    with (
        patch(
            "custom_components.adaptive_tts.tts.get_tts_entity",
            return_value=source,
        ),
        pytest.raises(RuntimeError, match="simulated save failure"),
    ):
        await _async_set_voice_override_targets(
            [first, second],
            "en-US",
            "whisper",
            DURATION_UNTIL_CHANGED,
        )

    assert first.persistent_voice_override == old_first
    assert second.persistent_voice_override == old_second
    assert first.next_voice_override == next_first
    assert second.next_voice_override == next_second
    assert first_store.data == _stored_override(first, old_first)
    assert second_store.data == _stored_override(second, old_second)


@pytest.mark.asyncio
async def test_clear_rolls_back_partial_multi_target_write(hass) -> None:
    """A later Clear failure restores persistent and one-shot state exactly."""
    first = AdaptiveTTSEntity(make_entry(entry_id="first"))
    second = AdaptiveTTSEntity(make_entry(entry_id="second"))
    old_first = VoiceOverride("normal", "en-US", "persist-first")
    old_second = VoiceOverride("normal", "en-US", "persist-second")
    next_first = VoiceOverride("whisper", "en-US", "next-first")
    next_second = VoiceOverride("whisper", "en-US", "next-second")
    first_store = _TransactionalStore(_stored_override(first, old_first))
    second_store = _TransactionalStore(
        _stored_override(second, old_second), fail_remove=True
    )
    _seed_state(first, old_first, next_first, first_store)
    _seed_state(second, old_second, next_second, second_store)

    with pytest.raises(RuntimeError, match="simulated remove failure"):
        await _async_clear_voice_override_targets([first, second], SCOPE_ALL)

    assert first.persistent_voice_override == old_first
    assert second.persistent_voice_override == old_second
    assert first.next_voice_override == next_first
    assert second.next_voice_override == next_second
    assert first_store.data == _stored_override(first, old_first)
    assert second_store.data == _stored_override(second, old_second)


@pytest.mark.asyncio
async def test_persistent_set_commits_after_all_storage_succeeds(hass) -> None:
    """Successful multi-target Set publishes every prepared state."""
    source = MockTTS()
    first = AdaptiveTTSEntity(make_entry(entry_id="first"))
    second = AdaptiveTTSEntity(make_entry(entry_id="second"))
    attach(first, hass, source)
    attach(second, hass, source)
    first._override_store = _TransactionalStore(None)
    second._override_store = _TransactionalStore(None)

    with patch(
        "custom_components.adaptive_tts.tts.get_tts_entity",
        return_value=source,
    ):
        await _async_set_voice_override_targets(
            [first, second],
            "en-US",
            "whisper",
            DURATION_UNTIL_CHANGED,
        )

    assert first.persistent_voice_override is not None
    assert second.persistent_voice_override is not None
    assert first.persistent_voice_override.voice == "whisper"
    assert second.persistent_voice_override.voice == "whisper"
    assert first._override_store.data["token"] == first.persistent_voice_override.token
    assert (
        second._override_store.data["token"] == second.persistent_voice_override.token
    )
