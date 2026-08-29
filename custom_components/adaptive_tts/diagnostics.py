"""Diagnostics support for Adaptive TTS."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_QUIET_END,
    CONF_QUIET_MODE,
    CONF_QUIET_OPTION,
    CONF_QUIET_START,
    CONF_QUIET_VALUE,
    CONF_UNDERLYING_TTS_ENTITY,
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
    return {
        "adaptive_tts_version": VERSION,
        "underlying_tts_entity_id": entity_id,
        "underlying_exists": underlying is not None,
        "underlying_available": underlying.available if underlying else False,
        "supported_languages": (
            list(underlying.supported_languages) if underlying else []
        ),
        "supported_options": list(underlying.supported_options or [])
        if underlying
        else [],
        "quiet_hours": {
            "enabled": config[CONF_QUIET_MODE],
            "start": str(config[CONF_QUIET_START]),
            "end": str(config[CONF_QUIET_END]),
            "override_option": config[CONF_QUIET_OPTION],
            "override_value": config[CONF_QUIET_VALUE],
        },
    }
