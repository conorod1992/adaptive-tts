"""Config flow for Adaptive TTS."""

from __future__ import annotations

from typing import Any, override

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import CONF_UNDERLYING_TTS_ENTITY, DOMAIN
from .helpers import (
    entry_config,
    get_tts_entity,
    is_adaptive_entity,
    selectable_tts_entities,
)


def _provider_selector(hass, default: str | None = None) -> selector.EntitySelector:
    """Build a selector restricted to known, non-Adaptive TTS entities."""
    entities = selectable_tts_entities(hass)
    excluded = [
        entity_id
        for entity_id in hass.states.async_entity_ids("tts")
        if is_adaptive_entity(hass, entity_id)
    ]
    if default and default not in entities and not is_adaptive_entity(hass, default):
        entities.append(default)
    return selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain="tts",
            include_entities=sorted(entities),
            exclude_entities=sorted(excluded),
        )
    )


class AdaptiveTTSConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle an Adaptive TTS config flow."""

    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow."""
        return AdaptiveTTSOptionsFlow(config_entry)

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the entity name and underlying provider."""
        errors: dict[str, str] = {}
        if user_input is not None:
            provider_id = user_input[CONF_UNDERLYING_TTS_ENTITY]
            if is_adaptive_entity(self.hass, provider_id):
                errors[CONF_UNDERLYING_TTS_ENTITY] = "recursive_provider"
            elif get_tts_entity(self.hass, provider_id) is None:
                errors[CONF_UNDERLYING_TTS_ENTITY] = "provider_not_found"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default="Adaptive TTS"
                ): selector.TextSelector(),
                vol.Required(CONF_UNDERLYING_TTS_ENTITY): _provider_selector(self.hass),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class AdaptiveTTSOptionsFlow(OptionsFlow):
    """Handle Adaptive TTS options."""

    def __init__(self, config_entry) -> None:
        """Initialize options flow."""
        self._config = entry_config(config_entry)

    @override
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select the underlying provider."""
        errors: dict[str, str] = {}
        if user_input is not None:
            provider_id = user_input[CONF_UNDERLYING_TTS_ENTITY]
            if is_adaptive_entity(self.hass, provider_id):
                errors[CONF_UNDERLYING_TTS_ENTITY] = "recursive_provider"
            elif get_tts_entity(self.hass, provider_id) is None:
                errors[CONF_UNDERLYING_TTS_ENTITY] = "provider_not_found"
            else:
                return self.async_create_entry(title="", data=user_input)

        current = self._config[CONF_UNDERLYING_TTS_ENTITY]
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UNDERLYING_TTS_ENTITY, default=current
                ): _provider_selector(self.hass, current)
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
