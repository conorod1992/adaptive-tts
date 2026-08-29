"""Shared helpers for Adaptive TTS."""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

from homeassistant.components.tts import TextToSpeechEntity
from homeassistant.components.tts.helper import get_engine_instance
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN


def entry_config(entry: ConfigEntry) -> dict[str, Any]:
    """Return config entry data with options applied."""
    return {**entry.data, **entry.options}


def parse_time(value: str | time) -> time:
    """Parse a Home Assistant time selector value."""
    if isinstance(value, time):
        return value
    return time.fromisoformat(value)


def is_time_in_range(now: datetime | time, start: str | time, end: str | time) -> bool:
    """Return whether now is in a time range, including one crossing midnight."""
    current = now.time() if isinstance(now, datetime) else now
    start_time = parse_time(start)
    end_time = parse_time(end)
    if start_time == end_time:
        return True
    if start_time < end_time:
        return start_time <= current < end_time
    return current >= start_time or current < end_time


def get_tts_entity(hass: HomeAssistant, entity_id: str) -> TextToSpeechEntity | None:
    """Get a TTS entity using Home Assistant's supported TTS helper."""
    engine = get_engine_instance(hass, entity_id)
    return engine if isinstance(engine, TextToSpeechEntity) else None


def is_adaptive_entity(hass: HomeAssistant, entity_id: str) -> bool:
    """Return whether an entity belongs to Adaptive TTS."""
    registry_entry = er.async_get(hass).async_get(entity_id)
    if registry_entry is not None and registry_entry.platform == DOMAIN:
        return True
    engine = get_engine_instance(hass, entity_id)
    return bool(getattr(engine, "is_adaptive_tts", False))


def selectable_tts_entities(hass: HomeAssistant) -> list[str]:
    """Return selectable non-Adaptive TTS entity IDs."""
    return sorted(
        entity_id
        for entity_id in hass.states.async_entity_ids("tts")
        if not is_adaptive_entity(hass, entity_id)
        and get_tts_entity(hass, entity_id) is not None
    )


def preferred_quiet_option(supported_options: list[str] | None) -> str:
    """Choose the most useful provider option for a quiet override."""
    options = supported_options or []
    for candidate in ("voice", "style", "emotion"):
        if candidate in options:
            return candidate
    return options[0] if options else "voice"
