"""Adaptive TTS entity platform."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, override

from homeassistant.components.tts import (
    TextToSpeechEntity,
    TTSAudioRequest,
    TTSAudioResponse,
    TtsAudioType,
    Voice,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    CACHE_POLICY_OPTION,
    CONF_QUIET_END,
    CONF_QUIET_LANGUAGE,
    CONF_QUIET_MODE,
    CONF_QUIET_OPTION,
    CONF_QUIET_START,
    CONF_QUIET_VALUE,
    CONF_UNDERLYING_TTS_ENTITY,
    DATA_ENTITIES,
    DOMAIN,
)
from .helpers import entry_config, get_tts_entity, is_time_in_range

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ResolvedRequest:
    """A TTS request after Adaptive TTS policy is applied."""

    underlying_entity_id: str
    language: str
    options: dict[str, Any]
    quiet_mode_active: bool


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up an Adaptive TTS entity."""
    entity = AdaptiveTTSEntity(entry)
    hass.data[DOMAIN][DATA_ENTITIES][entry.entry_id] = entity
    async_add_entities([entity])


class AdaptiveTTSEntity(TextToSpeechEntity):
    """A policy-aware wrapper around another TTS entity."""

    _attr_has_entity_name = True
    is_adaptive_tts = True

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the entity."""
        self._entry = entry
        self._attr_name = entry.title
        self._attr_unique_id = entry.entry_id

    @property
    def _config(self) -> dict[str, Any]:
        return entry_config(self._entry)

    @property
    def underlying_entity_id(self) -> str:
        """Return the configured underlying TTS entity ID."""
        return self._config[CONF_UNDERLYING_TTS_ENTITY]

    @property
    def _underlying(self) -> TextToSpeechEntity | None:
        if not hasattr(self, "hass"):
            return None
        engine = get_tts_entity(self.hass, self.underlying_entity_id)
        if engine is self or getattr(engine, "is_adaptive_tts", False):
            return None
        return engine

    @property
    @override
    def available(self) -> bool:
        """Return whether the underlying entity is available."""
        underlying = self._underlying
        return underlying is not None and underlying.available

    @property
    @override
    def default_language(self) -> str:
        """Expose the underlying entity's default language."""
        return self._underlying.default_language if self._underlying else ""

    @property
    @override
    def supported_languages(self) -> list[str]:
        """Expose the underlying entity's supported languages."""
        return list(self._underlying.supported_languages) if self._underlying else []

    @property
    @override
    def supported_options(self) -> list[str] | None:
        """Expose the underlying entity's supported option names."""
        return (
            list(self._underlying.supported_options)
            if self._underlying and self._underlying.supported_options is not None
            else None
        )

    @property
    @override
    def default_options(self) -> Mapping[str, Any] | None:
        """Expose provider defaults plus a wrapper-only cache discriminator."""
        options = (
            dict(self._underlying.default_options or {}) if self._underlying else {}
        )
        options[CACHE_POLICY_OPTION] = self._policy_cache_value()
        return options

    def _policy_cache_value(self) -> str:
        """Return a stable fingerprint of configuration and current policy state."""
        config = self._config
        quiet_active = self.is_quiet_mode_active()
        policy = "\0".join(
            str(value)
            for value in (
                config[CONF_UNDERLYING_TTS_ENTITY],
                config[CONF_QUIET_MODE],
                config[CONF_QUIET_START],
                config[CONF_QUIET_END],
                config[CONF_QUIET_OPTION],
                config.get(CONF_QUIET_LANGUAGE, ""),
                config[CONF_QUIET_VALUE],
                quiet_active,
            )
        )
        state = "quiet" if quiet_active else "normal"
        return f"{state}:{hashlib.blake2s(policy.encode(), digest_size=8).hexdigest()}"

    @callback
    @override
    def async_get_supported_voices(self, language: str) -> list[Voice] | None:
        """Expose the underlying entity's voices for a language."""
        if (underlying := self._underlying) is None:
            return None
        return underlying.async_get_supported_voices(language)

    @callback
    @override
    def async_supports_streaming_input(self) -> bool:
        """Return whether the underlying provider supports streaming input."""
        return bool(
            (underlying := self._underlying)
            and underlying.async_supports_streaming_input()
        )

    def is_quiet_mode_active(self, now: datetime | None = None) -> bool:
        """Return whether the configured quiet policy is active."""
        config = self._config
        if not config[CONF_QUIET_MODE]:
            return False
        return is_time_in_range(
            now or dt_util.now(),
            config[CONF_QUIET_START],
            config[CONF_QUIET_END],
        )

    @callback
    def resolve_request(
        self,
        language: str | None,
        options: Mapping[str, Any] | None,
        *,
        now: datetime | None = None,
    ) -> ResolvedRequest:
        """Validate and apply Adaptive TTS policy to a request."""
        underlying = self._underlying
        if underlying is None:
            _LOGGER.error(
                "Underlying TTS entity %s is missing, unavailable, or recursive",
                self.underlying_entity_id,
            )
            raise HomeAssistantError(
                f"Underlying TTS entity {self.underlying_entity_id} is not available"
            )
        if not underlying.available:
            _LOGGER.error(
                "Underlying TTS entity %s is unavailable", self.underlying_entity_id
            )
            raise HomeAssistantError(
                f"Underlying TTS entity {self.underlying_entity_id} is unavailable"
            )

        incoming_options = dict(options or {})
        policy_cache_value = incoming_options.pop(CACHE_POLICY_OPTION, None)
        quiet_active = (
            policy_cache_value.startswith("quiet:")
            if isinstance(policy_cache_value, str)
            else self.is_quiet_mode_active(now)
        )
        config = self._config

        effective_language = language or underlying.default_language
        if quiet_active and config[CONF_QUIET_OPTION] == "voice":
            effective_language = config.get(CONF_QUIET_LANGUAGE) or effective_language

        if effective_language not in underlying.supported_languages:
            _LOGGER.error(
                "Underlying TTS entity %s does not support language %s",
                self.underlying_entity_id,
                effective_language,
            )
            raise HomeAssistantError(
                f"Language '{effective_language}' is not supported by "
                f"{self.underlying_entity_id}"
            )

        effective_options = dict(underlying.default_options or {})
        effective_options.update(incoming_options)
        if quiet_active:
            option_name = config[CONF_QUIET_OPTION]
            option_value = config[CONF_QUIET_VALUE]
            supported_options = underlying.supported_options or []
            if option_name not in supported_options:
                _LOGGER.error(
                    "Quiet override option %s is no longer supported by %s",
                    option_name,
                    self.underlying_entity_id,
                )
                raise HomeAssistantError(
                    f"Quiet override option '{option_name}' is not supported by "
                    f"{self.underlying_entity_id}"
                )
            if option_name == "voice":
                voices = underlying.async_get_supported_voices(effective_language)
                if voices and option_value not in {voice.voice_id for voice in voices}:
                    _LOGGER.error(
                        "Quiet voice %s is no longer supported by %s for %s",
                        option_value,
                        self.underlying_entity_id,
                        effective_language,
                    )
                    raise HomeAssistantError(
                        f"Quiet voice '{option_value}' is not supported by "
                        f"{self.underlying_entity_id} for {effective_language}"
                    )
            effective_options[option_name] = option_value

        return ResolvedRequest(
            underlying_entity_id=self.underlying_entity_id,
            language=effective_language,
            options=effective_options,
            quiet_mode_active=quiet_active,
        )

    @override
    async def async_get_tts_audio(
        self, message: str, language: str, options: dict[str, Any]
    ) -> TtsAudioType:
        """Generate one-shot audio through the underlying entity."""
        resolved = self.resolve_request(language, options)
        underlying = self._underlying
        if underlying is None:
            raise HomeAssistantError(
                f"Underlying TTS entity {self.underlying_entity_id} disappeared"
            )
        try:
            return await underlying.async_get_tts_audio(
                message, resolved.language, resolved.options
            )
        except HomeAssistantError:
            raise
        except Exception as err:
            _LOGGER.error(
                "Underlying TTS generation failed for %s: %s",
                self.underlying_entity_id,
                err,
            )
            raise HomeAssistantError(
                f"TTS generation failed in {self.underlying_entity_id}: {err}"
            ) from err

    @override
    async def async_stream_tts_audio(
        self, request: TTSAudioRequest
    ) -> TTSAudioResponse:
        """Forward streaming input when supported, otherwise safely collect it."""
        resolved = self.resolve_request(request.language, request.options)
        underlying = self._underlying
        if underlying is None:
            raise HomeAssistantError(
                f"Underlying TTS entity {self.underlying_entity_id} disappeared"
            )
        if underlying.async_supports_streaming_input():
            try:
                return await underlying.async_stream_tts_audio(
                    TTSAudioRequest(
                        resolved.language, resolved.options, request.message_gen
                    )
                )
            except HomeAssistantError:
                raise
            except Exception as err:
                _LOGGER.error(
                    "Underlying streaming TTS generation failed for %s: %s",
                    self.underlying_entity_id,
                    err,
                )
                raise HomeAssistantError(
                    f"Streaming TTS generation failed in "
                    f"{self.underlying_entity_id}: {err}"
                ) from err

        message = "".join([chunk async for chunk in request.message_gen])
        try:
            extension, data = await underlying.async_get_tts_audio(
                message, resolved.language, resolved.options
            )
        except HomeAssistantError:
            raise
        except Exception as err:
            _LOGGER.error(
                "Underlying TTS generation failed for %s: %s",
                self.underlying_entity_id,
                err,
            )
            raise HomeAssistantError(
                f"TTS generation failed in {self.underlying_entity_id}: {err}"
            ) from err
        if extension is None or data is None:
            raise HomeAssistantError(
                f"No TTS audio returned by {self.underlying_entity_id}"
            )

        async def data_gen():
            yield data

        return TTSAudioResponse(extension, data_gen())
