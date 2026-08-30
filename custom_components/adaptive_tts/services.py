"""Service actions for Adaptive TTS."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from contextlib import AsyncExitStack

import voluptuous as vol
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
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

_LOGGER = logging.getLogger(__name__)

_SET_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required(ATTR_LANGUAGE): cv.string,
        vol.Required(ATTR_VOICE): cv.string,
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


def _validate_voice_override_targets(entities, language: str, voice: str) -> None:
    """Validate all targets before mutating any target."""
    for entity in entities:
        entity.validate_voice_override(language, voice)


def _unique_entities(entities):
    """Deduplicate targets by identity while preserving caller order."""
    unique = []
    seen = set()
    for entity in entities:
        identity = id(entity)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(entity)
    return unique


def _entity_label(entity) -> str:
    """Return a stable label for rollback diagnostics."""
    return getattr(entity, "entity_id", None) or getattr(
        getattr(entity, "_entry", None), "entry_id", "unknown"
    )


async def _async_commit_override_states(states) -> None:
    """Persist all targets, roll back on failure, then publish states."""
    attempted = []
    try:
        for entity, original, desired in states:
            if original.persistent == desired.persistent:
                continue
            attempted.append((entity, original))
            await entity._async_write_persistent_voice_override_locked(
                desired.persistent
            )
    except (Exception, asyncio.CancelledError) as err:
        rollback_failures = []
        for entity, original in reversed(attempted):
            try:
                await entity._async_write_persistent_voice_override_locked(
                    original.persistent
                )
            except Exception as rollback_err:
                label = _entity_label(entity)
                rollback_failures.append(label)
                _LOGGER.error(
                    "Failed to roll back voice override storage for %s: %s",
                    label,
                    rollback_err,
                )
        if rollback_failures and isinstance(err, Exception):
            raise HomeAssistantError(
                "Voice override update failed and rollback was incomplete for: "
                + ", ".join(rollback_failures)
            ) from err
        raise

    for entity, _original, desired in states:
        entity._apply_voice_override_state_locked(desired)


async def _async_set_voice_override_targets(
    entities, language: str, voice: str, duration: str
) -> None:
    """Apply one Set override action atomically across all targets."""
    entities = _unique_entities(entities)
    _validate_voice_override_targets(entities, language, voice)
    async with AsyncExitStack() as stack:
        for entity in sorted(entities, key=id):
            await stack.enter_async_context(entity._override_lock)

        validated = [
            entity.validate_voice_override(language, voice) for entity in entities
        ]
        states = []
        for entity, override in zip(entities, validated, strict=True):
            original = entity._voice_override_state()
            desired = entity._voice_override_state_with_set(override, duration)
            states.append((entity, original, desired))
        await _async_commit_override_states(states)


async def _async_clear_voice_override_targets(entities, scope: str) -> None:
    """Apply one Clear override action atomically across all targets."""
    entities = _unique_entities(entities)
    async with AsyncExitStack() as stack:
        for entity in sorted(entities, key=id):
            await stack.enter_async_context(entity._override_lock)

        states = []
        for entity in entities:
            original = entity._voice_override_state()
            desired = entity._voice_override_state_with_clear(scope)
            states.append((entity, original, desired))
        await _async_commit_override_states(states)


def async_register_services(hass: HomeAssistant) -> None:
    """Register Adaptive TTS actions."""

    async def _set_voice_override(call: ServiceCall) -> None:
        entities = _resolve_entities(hass, call.data[ATTR_ENTITY_ID])
        await _async_set_voice_override_targets(
            entities,
            call.data[ATTR_LANGUAGE],
            call.data[ATTR_VOICE],
            call.data[ATTR_DURATION],
        )

    async def _clear_voice_override(call: ServiceCall) -> None:
        entities = _resolve_entities(hass, call.data[ATTR_ENTITY_ID])
        await _async_clear_voice_override_targets(entities, call.data[ATTR_SCOPE])

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
