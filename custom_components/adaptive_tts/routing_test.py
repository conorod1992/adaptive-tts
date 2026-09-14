"""Live condition testing for Conditional Voice Routing."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers.condition import (
    ConditionChecker,
    async_from_config as async_condition_from_config,
    async_validate_condition_config,
)


async def _test_condition_list(
    hass: HomeAssistant, conditions: Any
) -> tuple[bool, list[ConditionChecker]]:
    """Validate, compile, and evaluate one unsaved condition list."""
    if not isinstance(conditions, list) or not conditions:
        raise vol.Invalid("Add at least one condition before testing this rule")

    checkers: list[ConditionChecker] = []
    try:
        for condition_config in conditions:
            if not isinstance(condition_config, dict):
                raise vol.Invalid("Each routing condition must be an object")
            validated = await async_validate_condition_config(hass, condition_config)
            checker = await async_condition_from_config(hass, validated)
            checkers.append(checker)
        return all(bool(checker.async_check()) for checker in checkers), checkers
    except Exception:
        for checker in checkers:
            checker.async_unload()
        raise


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "adaptive_tts/routing_test",
        vol.Required("rules"): list,
        vol.Required("target_index"): vol.All(int, vol.Range(min=0)),
    }
)
@websocket_api.async_response
async def websocket_routing_test(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Evaluate unsaved routing conditions and report effective priority."""
    rules = msg["rules"]
    target_index = msg["target_index"]
    if target_index >= len(rules):
        connection.send_error(
            msg["id"], websocket_api.ERR_INVALID_FORMAT, "Rule no longer exists"
        )
        return

    results: list[bool] = []
    all_checkers: list[ConditionChecker] = []
    try:
        # Only higher-priority rules can prevent the target from winning. Lower
        # draft rules are deliberately ignored so an unfinished rule below the
        # target cannot make its Test conditions action fail.
        for index, raw_rule in enumerate(rules[: target_index + 1]):
            if not isinstance(raw_rule, dict):
                raise vol.Invalid(f"Rule {index + 1} must be an object")
            matched, checkers = await _test_condition_list(
                hass, raw_rule.get("conditions")
            )
            all_checkers.extend(checkers)
            results.append(matched)

        winner_index = next(
            (
                index
                for index, (rule, matched) in enumerate(
                    zip(rules[: target_index + 1], results, strict=True)
                )
                if rule.get("enabled", True) and matched
            ),
            None,
        )
        target = rules[target_index]
        target_enabled = bool(target.get("enabled", True))
        winner_name = None
        if winner_index is not None:
            winner_name = str(
                rules[winner_index].get("name") or f"Rule {winner_index + 1}"
            )

        connection.send_result(
            msg["id"],
            {
                "matches": results[target_index],
                "enabled": target_enabled,
                "would_win": target_enabled and winner_index == target_index,
                "winner_index": winner_index,
                "winner_name": winner_name,
            },
        )
    except vol.Invalid as err:
        connection.send_error(
            msg["id"], websocket_api.ERR_INVALID_FORMAT, str(err)
        )
    except Exception as err:
        connection.send_error(
            msg["id"], websocket_api.ERR_UNKNOWN_ERROR, str(err)
        )
    finally:
        for checker in all_checkers:
            checker.async_unload()


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register live routing-test WebSocket commands."""
    websocket_api.async_register_command(hass, websocket_routing_test)
