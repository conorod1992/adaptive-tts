"""Config flow for Adaptive TTS."""

from __future__ import annotations

from typing import Any, override

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_QUIET_END,
    CONF_QUIET_LANGUAGE,
    CONF_QUIET_MODE,
    CONF_QUIET_OPTION,
    CONF_QUIET_START,
    CONF_QUIET_VALUE,
    CONF_UNDERLYING_TTS_ENTITY,
    DEFAULT_QUIET_END,
    DEFAULT_QUIET_START,
    DOMAIN,
)
from .helpers import (
    entry_config,
    get_tts_entity,
    is_adaptive_entity,
    preferred_quiet_option,
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


def _option_selector(options: list[str], default: str) -> selector.SelectSelector:
    """Build the provider option selector."""
    choices = options or [default]
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=choices,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _language_selector(provider) -> selector.SelectSelector:
    """Build a selector for the underlying provider's supported languages."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=language, label=language)
                for language in provider.supported_languages
            ],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _enumerated_voices(provider, language: str | None):
    """Return provider voices, preserving None as 'cannot enumerate'."""
    return provider.async_get_supported_voices(language or provider.default_language)


def _override_selector(
    provider, option: str, language: str | None = None
) -> selector.SelectSelector | selector.TextSelector:
    """Build a voice dropdown when enumeration is available, else text input."""
    if option == "voice":
        voices = _enumerated_voices(provider, language)
        if voices:
            return selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=voice.voice_id, label=voice.name or voice.voice_id
                        )
                        for voice in voices
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    custom_value=False,
                )
            )
    return selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
    )


def _override_error(
    provider, option: str, language: str | None, value: str
) -> str | None:
    """Validate an override value when the provider exposes a finite voice list."""
    if not value:
        return "override_required"
    if option != "voice":
        return None
    voices = _enumerated_voices(provider, language)
    if voices is not None and value not in {voice.voice_id for voice in voices}:
        return "unsupported_voice"
    return None


def _existing_override_default(
    provider,
    option: str,
    language: str | None,
    value: str,
    *,
    provider_changed: bool,
) -> str:
    """Return an existing value only when it remains valid for this provider."""
    if provider_changed or not value:
        return ""
    return value if _override_error(provider, option, language, value) is None else ""


class AdaptiveTTSConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle an Adaptive TTS config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._pending: dict[str, Any] = {}

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
                self._pending.update(user_input)
                return await self.async_step_policy()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default="Adaptive TTS"
                ): selector.TextSelector(),
                vol.Required(CONF_UNDERLYING_TTS_ENTITY): _provider_selector(self.hass),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_policy(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect quiet-hours policy settings."""
        provider = get_tts_entity(self.hass, self._pending[CONF_UNDERLYING_TTS_ENTITY])
        if provider is None:
            return self.async_abort(reason="provider_not_found")
        supported_options = list(provider.supported_options or [])
        default_option = preferred_quiet_option(supported_options)
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_QUIET_MODE] and (
                user_input[CONF_QUIET_OPTION] not in supported_options
            ):
                errors[CONF_QUIET_OPTION] = "unsupported_option"
            else:
                self._pending.update(user_input)
                if not user_input[CONF_QUIET_MODE]:
                    self._pending[CONF_QUIET_VALUE] = ""
                    self._pending.pop(CONF_QUIET_LANGUAGE, None)
                    return self._create_entry()
                if user_input[CONF_QUIET_OPTION] == "voice":
                    return await self.async_step_language()
                self._pending.pop(CONF_QUIET_LANGUAGE, None)
                return await self.async_step_override()

        schema = vol.Schema(
            {
                vol.Required(CONF_QUIET_MODE, default=True): selector.BooleanSelector(),
                vol.Required(
                    CONF_QUIET_START, default=DEFAULT_QUIET_START
                ): selector.TimeSelector(),
                vol.Required(
                    CONF_QUIET_END, default=DEFAULT_QUIET_END
                ): selector.TimeSelector(),
                vol.Required(
                    CONF_QUIET_OPTION, default=default_option
                ): _option_selector(supported_options, default_option),
            }
        )
        return self.async_show_form(step_id="policy", data_schema=schema, errors=errors)

    async def async_step_language(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the language/accent family before choosing a quiet voice."""
        provider = get_tts_entity(self.hass, self._pending[CONF_UNDERLYING_TTS_ENTITY])
        if provider is None:
            return self.async_abort(reason="provider_not_found")
        if user_input is not None:
            language = user_input[CONF_QUIET_LANGUAGE]
            if language not in provider.supported_languages:
                return self.async_show_form(
                    step_id="language",
                    data_schema=vol.Schema(
                        {
                            vol.Required(
                                CONF_QUIET_LANGUAGE,
                                default=provider.default_language,
                            ): _language_selector(provider)
                        }
                    ),
                    errors={CONF_QUIET_LANGUAGE: "unsupported_language"},
                )
            self._pending[CONF_QUIET_LANGUAGE] = language
            return await self.async_step_override()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_QUIET_LANGUAGE,
                    default=provider.default_language,
                ): _language_selector(provider)
            }
        )
        return self.async_show_form(step_id="language", data_schema=schema)

    async def async_step_override(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect and validate the quiet override value."""
        errors: dict[str, str] = {}
        provider = get_tts_entity(self.hass, self._pending[CONF_UNDERLYING_TTS_ENTITY])
        if provider is None:
            return self.async_abort(reason="provider_not_found")
        if user_input is not None:
            value = user_input[CONF_QUIET_VALUE].strip()
            error = _override_error(
                provider,
                self._pending[CONF_QUIET_OPTION],
                self._pending.get(CONF_QUIET_LANGUAGE),
                value,
            )
            if error is not None:
                errors[CONF_QUIET_VALUE] = error
            else:
                self._pending[CONF_QUIET_VALUE] = value
                return self._create_entry()

        schema = vol.Schema(
            {
                vol.Required(CONF_QUIET_VALUE): _override_selector(
                    provider,
                    self._pending[CONF_QUIET_OPTION],
                    self._pending.get(CONF_QUIET_LANGUAGE),
                )
            }
        )
        return self.async_show_form(
            step_id="override", data_schema=schema, errors=errors
        )

    def _create_entry(self) -> ConfigFlowResult:
        """Create the config entry."""
        title = self._pending[CONF_NAME]
        return self.async_create_entry(title=title, data=self._pending)


class AdaptiveTTSOptionsFlow(OptionsFlow):
    """Handle Adaptive TTS options."""

    def __init__(self, config_entry) -> None:
        """Initialize options flow."""
        self._config = entry_config(config_entry)
        self._pending: dict[str, Any] = {}

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
                self._pending.update(user_input)
                return await self.async_step_policy()

        current = self._config[CONF_UNDERLYING_TTS_ENTITY]
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UNDERLYING_TTS_ENTITY, default=current
                ): _provider_selector(self.hass, current)
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    async def async_step_policy(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update quiet-hours policy settings."""
        provider = get_tts_entity(self.hass, self._pending[CONF_UNDERLYING_TTS_ENTITY])
        if provider is None:
            return self.async_abort(reason="provider_not_found")
        supported_options = list(provider.supported_options or [])
        current_option = self._config.get(
            CONF_QUIET_OPTION, preferred_quiet_option(supported_options)
        )
        default_option = (
            current_option
            if current_option in supported_options
            else preferred_quiet_option(supported_options)
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_QUIET_MODE] and (
                user_input[CONF_QUIET_OPTION] not in supported_options
            ):
                errors[CONF_QUIET_OPTION] = "unsupported_option"
            else:
                self._pending.update(user_input)
                if not user_input[CONF_QUIET_MODE]:
                    self._pending[CONF_QUIET_VALUE] = ""
                    self._pending.pop(CONF_QUIET_LANGUAGE, None)
                    return self.async_create_entry(title="", data=self._pending)
                if user_input[CONF_QUIET_OPTION] == "voice":
                    return await self.async_step_language()
                self._pending.pop(CONF_QUIET_LANGUAGE, None)
                return await self.async_step_override()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_QUIET_MODE,
                    default=self._config.get(CONF_QUIET_MODE, True),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_QUIET_START,
                    default=self._config.get(CONF_QUIET_START, DEFAULT_QUIET_START),
                ): selector.TimeSelector(),
                vol.Required(
                    CONF_QUIET_END,
                    default=self._config.get(CONF_QUIET_END, DEFAULT_QUIET_END),
                ): selector.TimeSelector(),
                vol.Required(
                    CONF_QUIET_OPTION, default=default_option
                ): _option_selector(supported_options, default_option),
            }
        )
        return self.async_show_form(step_id="policy", data_schema=schema, errors=errors)

    async def async_step_language(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the quiet synthesis language before choosing the voice."""
        provider = get_tts_entity(self.hass, self._pending[CONF_UNDERLYING_TTS_ENTITY])
        if provider is None:
            return self.async_abort(reason="provider_not_found")
        current_language = self._config.get(
            CONF_QUIET_LANGUAGE, provider.default_language
        )
        provider_changed = (
            self._pending[CONF_UNDERLYING_TTS_ENTITY]
            != self._config[CONF_UNDERLYING_TTS_ENTITY]
        )
        if provider_changed or current_language not in provider.supported_languages:
            current_language = provider.default_language

        if user_input is not None:
            language = user_input[CONF_QUIET_LANGUAGE]
            if language not in provider.supported_languages:
                return self.async_show_form(
                    step_id="language",
                    data_schema=vol.Schema(
                        {
                            vol.Required(
                                CONF_QUIET_LANGUAGE,
                                default=current_language,
                            ): _language_selector(provider)
                        }
                    ),
                    errors={CONF_QUIET_LANGUAGE: "unsupported_language"},
                )
            self._pending[CONF_QUIET_LANGUAGE] = language
            return await self.async_step_override()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_QUIET_LANGUAGE,
                    default=current_language,
                ): _language_selector(provider)
            }
        )
        return self.async_show_form(step_id="language", data_schema=schema)

    async def async_step_override(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update the quiet override value."""
        errors: dict[str, str] = {}
        provider = get_tts_entity(self.hass, self._pending[CONF_UNDERLYING_TTS_ENTITY])
        if provider is None:
            return self.async_abort(reason="provider_not_found")
        option = self._pending[CONF_QUIET_OPTION]
        language = self._pending.get(CONF_QUIET_LANGUAGE)
        if user_input is not None:
            value = user_input[CONF_QUIET_VALUE].strip()
            error = _override_error(provider, option, language, value)
            if error is not None:
                errors[CONF_QUIET_VALUE] = error
            else:
                self._pending[CONF_QUIET_VALUE] = value
                return self.async_create_entry(title="", data=self._pending)

        default_value = _existing_override_default(
            provider,
            option,
            language,
            self._config.get(CONF_QUIET_VALUE, ""),
            provider_changed=(
                self._pending[CONF_UNDERLYING_TTS_ENTITY]
                != self._config[CONF_UNDERLYING_TTS_ENTITY]
            ),
        )
        value_key = (
            vol.Required(CONF_QUIET_VALUE, default=default_value)
            if default_value
            else vol.Required(CONF_QUIET_VALUE)
        )
        schema = vol.Schema(
            {
                value_key: _override_selector(
                    provider,
                    option,
                    language,
                )
            }
        )
        return self.async_show_form(
            step_id="override", data_schema=schema, errors=errors
        )
