"""Diagnostics support for Adaptive TTS."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_QUIET_END,
    CONF_QUIET_LANGUAGE,
    CONF_QUIET_MODE,
    CONF_QUIET_OPTION,
    CONF_QUIET_START,
    CONF_QUIET_VALUE,
    CONF_UNDERLYING_TTS_ENTITY,
    DATA_ENTITIES,
    DOMAIN,
    VERSION,
)
from .helpers import entry_config, get_tts_entity


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return non-sensitive diagnostics for a config entry."""
    config = entry_config(entry)
    entity_id = config[CONF_UNDERLYING_TTS_ENTITY]
    underlying = get_tts_entity(hass, entity_id)
    adaptive_entity = (
        hass.data.get(DOMAIN, {}).get(DATA_ENTITIES, {}).get(entry.entry_id)
    )
    persistent = (
        adaptive_entity.persistent_voice_override
        if adaptive_entity is not None
        else None
    )
    pending = (
        adaptive_entity.next_voice_override if adaptive_entity is not None else None
    )
    metadata_errors: dict[str, str] = {}
    underlying_available = False
    supported_languages: list[str] = []
    supported_options: list[str] = []
    if underlying is not None:
        for key, reader, default in (
            ("available", lambda: bool(underlying.available), False),
            ("supported_languages", lambda: list(underlying.supported_languages), []),
            ("supported_options", lambda: list(underlying.supported_options or []), []),
        ):
            try:
                value = reader()
            except Exception as err:
                metadata_errors[key] = type(err).__name__
                value = default
            if key == "available":
                underlying_available = value
            elif key == "supported_languages":
                supported_languages = value
            else:
                supported_options = value
    return {
        "adaptive_tts_version": VERSION,
        "underlying_tts_entity_id": entity_id,
        "underlying_exists": underlying is not None,
        "underlying_available": underlying_available,
        "supported_languages": supported_languages,
        "supported_options": supported_options,
        "provider_metadata_errors": metadata_errors,
        "quiet_hours": {
            "enabled": config[CONF_QUIET_MODE],
            "start": str(config[CONF_QUIET_START]),
            "end": str(config[CONF_QUIET_END]),
            "override_option": config[CONF_QUIET_OPTION],
            "override_language": config.get(CONF_QUIET_LANGUAGE),
            "override_value": config[CONF_QUIET_VALUE],
        },
        "voice_override": {
            "persistent_language": persistent.language if persistent else None,
            "persistent_voice": persistent.voice if persistent else None,
            "next_request_pending": pending is not None,
            "next_request_language": pending.language if pending else None,
            "next_request_voice": pending.voice if pending else None,
        },
    }
