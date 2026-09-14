"""Tests for Conditional Voice Routing."""

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_tts.const import (
    CACHE_POLICY_OPTION,
    CONF_ROUTING_RULES,
    DOMAIN,
    DURATION_NEXT_REQUEST,
    SCOPE_NEXT_REQUEST,
    SCOPE_ROUTING,
)
from custom_components.adaptive_tts.routing_entity import RoutedAdaptiveTTSEntity

from .test_tts import MockTTS, attach, make_entry


def _state_condition(entity_id: str, state: str = "on") -> dict:
    return {"condition": "state", "entity_id": entity_id, "state": state}


def _entry(rules: list[dict]) -> MockConfigEntry:
    base = make_entry()
    return MockConfigEntry(
        domain=DOMAIN,
        title="Routed TTS",
        data=dict(base.data),
        options={CONF_ROUTING_RULES: rules},
    )


def _rule(
    rule_id: str,
    name: str,
    entity_id: str,
    voice: str,
    *,
    enabled: bool = True,
    language: str = "en-US",
) -> dict:
    return {
        "id": rule_id,
        "name": name,
        "enabled": enabled,
        "conditions": [_state_condition(entity_id)],
        "language": language,
        "voice": voice,
    }


@pytest.mark.asyncio
async def test_first_matching_enabled_rule_wins(hass, tmp_path) -> None:
    """Rules are evaluated in list order and disabled rules are ignored."""
    hass.config.config_dir = str(tmp_path)
    hass.states.async_set("input_boolean.first", "on")
    hass.states.async_set("input_boolean.second", "on")
    rules = [
        _rule("disabled", "Disabled first", "input_boolean.first", "normal", enabled=False),
        _rule("first", "First enabled", "input_boolean.first", "whisper"),
        _rule("second", "Second enabled", "input_boolean.second", "normal"),
    ]
    source = MockTTS()
    entity = RoutedAdaptiveTTSEntity(_entry(rules))
    attach(entity, hass, source)

    with patch("custom_components.adaptive_tts.tts.get_tts_entity", return_value=source):
        await entity.async_load_voice_override(hass)
        snapshot = entity._current_policy_snapshot()
        resolved = entity.resolve_request("en-US", {})

    assert snapshot.override_scope == SCOPE_ROUTING
    assert snapshot.voice_override is not None
    assert snapshot.voice_override.voice == "whisper"
    assert snapshot.voice_override.token == "first"
    assert resolved.options["voice"] == "whisper"

    entity._conditional_voice_router.async_unload()


@pytest.mark.asyncio
async def test_manual_next_request_override_beats_routing(hass, tmp_path) -> None:
    """An explicit one-shot override always outranks automatic routing."""
    hass.config.config_dir = str(tmp_path)
    hass.states.async_set("input_boolean.route", "on")
    source = MockTTS()
    entity = RoutedAdaptiveTTSEntity(
        _entry([_rule("route", "Automatic route", "input_boolean.route", "whisper")])
    )
    attach(entity, hass, source)

    with patch("custom_components.adaptive_tts.tts.get_tts_entity", return_value=source):
        await entity.async_load_voice_override(hass)
        await entity.async_set_voice_override("en-US", "normal", DURATION_NEXT_REQUEST)
        snapshot = entity._current_policy_snapshot()

    assert snapshot.override_scope == SCOPE_NEXT_REQUEST
    assert snapshot.voice_override is not None
    assert snapshot.voice_override.voice == "normal"

    entity._conditional_voice_router.async_unload()


@pytest.mark.asyncio
async def test_routing_state_is_part_of_cache_policy_snapshot(hass, tmp_path) -> None:
    """Changing condition state changes HA's cache discriminator and routed voice."""
    hass.config.config_dir = str(tmp_path)
    source = MockTTS()
    entity = RoutedAdaptiveTTSEntity(
        _entry([_rule("route", "Conditional", "input_boolean.route", "whisper")])
    )
    attach(entity, hass, source)

    with patch("custom_components.adaptive_tts.tts.get_tts_entity", return_value=source):
        await entity.async_load_voice_override(hass)
        hass.states.async_set("input_boolean.route", "off")
        normal_policy = entity.default_options[CACHE_POLICY_OPTION]
        hass.states.async_set("input_boolean.route", "on")
        routed_policy = entity.default_options[CACHE_POLICY_OPTION]
        resolved = entity.resolve_request(
            "en-US", {CACHE_POLICY_OPTION: routed_policy}
        )

    assert normal_policy != routed_policy
    assert resolved.options["voice"] == "whisper"
    entity._conditional_voice_router.async_unload()


@pytest.mark.asyncio
async def test_invalid_matching_voice_falls_through_to_next_rule(hass, tmp_path) -> None:
    """A stale matching voice does not block a later valid matching rule."""
    hass.config.config_dir = str(tmp_path)
    hass.states.async_set("input_boolean.route", "on")
    rules = [
        _rule("stale", "Stale voice", "input_boolean.route", "removed-voice"),
        _rule("valid", "Valid voice", "input_boolean.route", "whisper"),
    ]
    source = MockTTS()
    entity = RoutedAdaptiveTTSEntity(_entry(rules))
    attach(entity, hass, source)

    with patch("custom_components.adaptive_tts.tts.get_tts_entity", return_value=source):
        await entity.async_load_voice_override(hass)
        snapshot = entity._current_policy_snapshot()

    assert snapshot.override_scope == SCOPE_ROUTING
    assert snapshot.voice_override is not None
    assert snapshot.voice_override.token == "valid"
    assert snapshot.voice_override.voice == "whisper"
    entity._conditional_voice_router.async_unload()
