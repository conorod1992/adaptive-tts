"""Service actions for Adaptive TTS."""

from __future__ import annotations

from collections.abc import Iterable

import voluptuous as vol
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import (
    ATTR_DURATION,
    ATTR_LANGUAGE,
    ATTR_SCOPE,
    ATTR_VOICE,
    DATA_ENTITIES,
    DOMAIN,
    DURATION_NEXT_REQUEST,
    DURATION_UNTIL_CHANGED,
    SCOPE_ALL,
    SCOPE_NEXT_REQUEST,
    SCOPE_PERSISTENT,
    SERVICE_CLEAR_VOICE_OVERRIDE,
    SERVICE_SET_VOICE_OVERRIDE,
)

_SET_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required(ATTR_VOICE): cv.string,
        vol.Optional(ATTR_LANGUAGE): cv.string,
        vol.Optional(ATTR_DURATION, default=DURATION_NEXT_REQUEST): vol.In(
            (DURATION_NEXT_REQUEST, DURATION_UNTIL_CHANGED)
        ),
    }
)

_CLEAR_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Optional(ATTR_SCOPE, default=SCOPE_ALL): vol.In(
            (SCOPE_ALL, SCOPE_NEXT_REQUEST, SCOPE_PERSISTENT)
        ),
    }
)


def _resolve_entities(hass: HomeAssistant, entity_ids: Iterable[str]):
    """Resolve targeted Adaptive TTS entities, including renamed entities."""
    registry = er.async_get(hass)
    entities_by_entry = hass.data[DOMAIN][DATA_ENTITIES]
    resolved = []
    missing = []

    for entity_id in entity_ids:
        registry_entry = registry.async_get(entity_id)
        entity = None
        if (
            registry_entry is not None
            and registry_entry.platform == DOMAIN
            and registry_entry.config_entry_id is not None
        ):
            entity = entities_by_entry.get(registry_entry.config_entry_id)
        if entity is None:
            entity = next(
                (
                    candidate
                    for candidate in entities_by_entry.values()
                    if getattr(candidate, "entity_id", None) == entity_id
                ),
                None,
            )
        if entity is None:
            missing.append(entity_id)
        else:
            resolved.append(entity)

    if missing:
        raise ServiceValidationError(
            "Not an available Adaptive TTS entity: " + ", ".join(missing)
        )
    return resolved


def async_register_services(hass: HomeAssistant) -> None:
    """Register Adaptive TTS actions."""

    async def _set_voice_override(call: ServiceCall) -> None:
        entities = _resolve_entities(hass, call.data[ATTR_ENTITY_ID])
        language = call.data.get(ATTR_LANGUAGE)
        voice = call.data[ATTR_VOICE]
        duration = call.data[ATTR_DURATION]
        for entity in entities:
            await entity.async_set_voice_override(language, voice, duration)

    async def _clear_voice_override(call: ServiceCall) -> None:
        entities = _resolve_entities(hass, call.data[ATTR_ENTITY_ID])
        scope = call.data[ATTR_SCOPE]
        for entity in entities:
            await entity.async_clear_voice_override(scope)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_VOICE_OVERRIDE,
        _set_voice_override,
        schema=_SET_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_VOICE_OVERRIDE,
        _clear_voice_override,
        schema=_CLEAR_SCHEMA,
    )
