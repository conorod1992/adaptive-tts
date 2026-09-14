"""Conditional voice routing for Adaptive TTS."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.condition import (
    ConditionChecker,
    async_from_config as async_condition_from_config,
    async_validate_condition_config,
)

from .const import CONF_ROUTING_RULES, DATA_ENTITIES, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RoutingVoice:
    """Voice selected by a conditional routing rule."""

    rule_id: str
    rule_name: str
    voice: str
    language: str | None = None


@dataclass(slots=True)
class _CompiledRule:
    """A validated rule and its Home Assistant condition checkers."""

    rule_id: str
    name: str
    enabled: bool
    voice: str
    language: str | None
    checkers: list[ConditionChecker]

    def matches(self) -> bool:
        """Return whether every top-level condition currently matches."""
        return all(bool(checker.async_check()) for checker in self.checkers)

    def unload(self) -> None:
        """Release resources owned by Home Assistant condition checkers."""
        for checker in self.checkers:
            checker.async_unload()


class ConditionalVoiceRouter:
    """Compile and evaluate ordered Home Assistant condition rules."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize an empty router for a config entry."""
        self._entry = entry
        self._rules: list[_CompiledRule] = []

    async def async_setup(self, hass: HomeAssistant) -> None:
        """Validate and compile configured rules using HA's native condition engine."""
        self.async_unload()
        raw_rules = {**self._entry.data, **self._entry.options}.get(
            CONF_ROUTING_RULES, []
        )
        if not isinstance(raw_rules, list):
            _LOGGER.warning(
                "Ignoring malformed conditional voice routing rules for %s",
                self._entry.entry_id,
            )
            return

        compiled: list[_CompiledRule] = []
        try:
            for raw_rule in raw_rules:
                rule = _validate_rule_shape(raw_rule)
                checkers: list[ConditionChecker] = []
                for condition_config in rule["conditions"]:
                    validated = await async_validate_condition_config(
                        hass, condition_config
                    )
                    checker = await async_condition_from_config(hass, validated)
                    checkers.append(checker)
                compiled.append(
                    _CompiledRule(
                        rule_id=rule["id"],
                        name=rule["name"],
                        enabled=rule["enabled"],
                        voice=rule["voice"],
                        language=rule.get("language") or None,
                        checkers=checkers,
                    )
                )
        except Exception:
            for rule in compiled:
                rule.unload()
            raise

        self._rules = compiled

    def async_unload(self) -> None:
        """Unload all compiled conditions."""
        rules, self._rules = self._rules, []
        for rule in rules:
            rule.unload()

    def matching_voices(self) -> list[RoutingVoice]:
        """Return matching enabled rules in configured priority order."""
        matches: list[RoutingVoice] = []
        for rule in self._rules:
            if not rule.enabled:
                continue
            try:
                matched = rule.matches()
            except Exception as err:
                _LOGGER.warning(
                    "Conditional voice routing rule %s (%s) could not be evaluated: %s",
                    rule.name,
                    rule.rule_id,
                    err,
                )
                continue
            if matched:
                matches.append(
                    RoutingVoice(
                        rule_id=rule.rule_id,
                        rule_name=rule.name,
                        voice=rule.voice,
                        language=rule.language,
                    )
                )
        return matches


_RULE_SHAPE = vol.Schema(
    {
        vol.Required("id"): vol.All(str, vol.Length(min=1, max=100)),
        vol.Required("name"): vol.All(str, vol.Length(min=1, max=100)),
        vol.Optional("enabled", default=True): bool,
        vol.Required("conditions"): vol.All(list, vol.Length(min=1)),
        vol.Optional("language"): vol.Any(None, str),
        vol.Required("voice"): vol.All(str, vol.Length(min=1, max=255)),
    },
    extra=vol.PREVENT_EXTRA,
)


def _validate_rule_shape(rule: Any) -> dict[str, Any]:
    """Validate JSON-safe rule structure and normalize whitespace."""
    if not isinstance(rule, dict):
        raise vol.Invalid("Routing rule must be an object")
    validated = dict(_RULE_SHAPE(rule))
    validated["id"] = validated["id"].strip()
    validated["name"] = validated["name"].strip()
    validated["voice"] = validated["voice"].strip()
    language = validated.get("language")
    if isinstance(language, str):
        language = language.strip()
        validated["language"] = language or None
    if not validated["id"] or not validated["name"] or not validated["voice"]:
        raise vol.Invalid("Routing rule id, name and voice must not be empty")
    return validated


async def _validate_rules(hass: HomeAssistant, rules: Any) -> list[dict[str, Any]]:
    """Validate all rules and their native Home Assistant conditions."""
    if not isinstance(rules, list):
        raise vol.Invalid("Rules must be a list")
    if len(rules) > 50:
        raise vol.Invalid("A maximum of 50 routing rules is supported")

    validated_rules: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_rule in rules:
        rule = _validate_rule_shape(raw_rule)
        if rule["id"] in seen_ids:
            raise vol.Invalid(f"Duplicate routing rule id: {rule['id']}")
        seen_ids.add(rule["id"])
        for condition_config in rule["conditions"]:
            if not isinstance(condition_config, dict):
                raise vol.Invalid("Each routing condition must be an object")
            await async_validate_condition_config(hass, condition_config)
        validated_rules.append(rule)
    return validated_rules


def _adaptive_entity(hass: HomeAssistant, entity_id: str):
    """Return one loaded Adaptive TTS entity or raise a useful error."""
    for entity in hass.data.get(DOMAIN, {}).get(DATA_ENTITIES, {}).values():
        if getattr(entity, "entity_id", None) == entity_id:
            return entity
    raise HomeAssistantError(f"Adaptive TTS entity {entity_id} was not found")


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "adaptive_tts/routing_get",
        vol.Required("entity_id"): str,
    }
)
@callback
def websocket_routing_get(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return ordered routing rules for one Adaptive TTS entity."""
    try:
        entity = _adaptive_entity(hass, msg["entity_id"])
        rules = {**entity._entry.data, **entity._entry.options}.get(  # noqa: SLF001
            CONF_ROUTING_RULES, []
        )
    except HomeAssistantError as err:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, str(err))
        return
    connection.send_result(
        msg["id"], {"rules": rules if isinstance(rules, list) else []}
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "adaptive_tts/routing_save",
        vol.Required("entity_id"): str,
        vol.Required("rules"): list,
    }
)
@websocket_api.async_response
async def websocket_routing_save(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Validate, persist and reload ordered conditional voice routing rules."""
    try:
        entity = _adaptive_entity(hass, msg["entity_id"])
        rules = await _validate_rules(hass, msg["rules"])
        entry = entity._entry  # noqa: SLF001
        options = dict(entry.options)
        if rules:
            options[CONF_ROUTING_RULES] = rules
        else:
            options.pop(CONF_ROUTING_RULES, None)
        hass.config_entries.async_update_entry(entry, options=options)
    except (HomeAssistantError, vol.Invalid) as err:
        connection.send_error(
            msg["id"], websocket_api.ERR_INVALID_FORMAT, str(err)
        )
        return
    except Exception as err:
        _LOGGER.exception("Could not save Conditional Voice Routing rules")
        connection.send_error(
            msg["id"], websocket_api.ERR_UNKNOWN_ERROR, str(err)
        )
        return
    connection.send_result(msg["id"], {"saved": True, "rules": rules})


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register Conditional Voice Routing WebSocket commands."""
    websocket_api.async_register_command(hass, websocket_routing_get)
    websocket_api.async_register_command(hass, websocket_routing_save)
