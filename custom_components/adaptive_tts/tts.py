"""Adaptive TTS entity platform."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, override

from homeassistant.components.tts import (
    ATTR_PREFERRED_BITRATE,
    ATTR_PREFERRED_FORMAT,
    ATTR_PREFERRED_SAMPLE_BYTES,
    ATTR_PREFERRED_SAMPLE_CHANNELS,
    ATTR_PREFERRED_SAMPLE_RATE,
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
from homeassistant.helpers.storage import Store
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
    DURATION_NEXT_REQUEST,
    DURATION_UNTIL_CHANGED,
    SCOPE_ALL,
    SCOPE_NEXT_REQUEST,
    SCOPE_PERSISTENT,
)
from .helpers import entry_config, get_tts_entity, is_time_in_range

_LOGGER = logging.getLogger(__name__)
_STORAGE_VERSION = 1
_POLICY_SNAPSHOT_PREFIX = "snapshot-v2:"
_PREFERRED_OUTPUT_OPTIONS = frozenset(
    {
        ATTR_PREFERRED_FORMAT,
        ATTR_PREFERRED_SAMPLE_RATE,
        ATTR_PREFERRED_SAMPLE_CHANNELS,
        ATTR_PREFERRED_SAMPLE_BYTES,
        ATTR_PREFERRED_BITRATE,
    }
)


@dataclass(frozen=True, slots=True)
class VoiceOverride:
    """An explicit voice override."""

    voice: str
    language: str | None = None
    token: str | None = None


@dataclass(frozen=True, slots=True)
class PolicySnapshot:
    """Policy state captured when Home Assistant prepares a TTS request."""

    underlying_entity_id: str
    quiet_mode_active: bool
    quiet_option: str
    quiet_language: str | None
    quiet_value: str
    override_scope: str | None = None
    voice_override: VoiceOverride | None = None


@dataclass(frozen=True, slots=True)
class ResolvedRequest:
    """A TTS request after Adaptive TTS policy is applied."""

    underlying_entity_id: str
    language: str
    options: dict[str, Any]
    quiet_mode_active: bool
    voice_override: VoiceOverride | None = None
    voice_override_scope: str | None = None


def _validate_tts_audio_result(
    entity_id: str, extension: Any, data: Any
) -> tuple[str, bytes]:
    """Validate one-shot audio returned by an underlying provider."""
    if not extension or not data:
        raise HomeAssistantError(f"No TTS audio returned by {entity_id}")
    if not isinstance(extension, str) or not isinstance(data, bytes):
        raise HomeAssistantError(f"Invalid TTS audio returned by {entity_id}")
    return extension, data


def _validate_stream_response(entity_id: str, response: Any) -> TTSAudioResponse:
    """Validate the shape of a streaming response before exposing it to HA."""
    if (
        not isinstance(response, TTSAudioResponse)
        or not isinstance(response.extension, str)
        or not response.extension
        or not hasattr(response.data_gen, "__aiter__")
    ):
        raise HomeAssistantError(
            f"Invalid streaming TTS response returned by {entity_id}"
        )
    return response


def _voice_override_store(
    hass: HomeAssistant, entry: ConfigEntry
) -> Store[dict[str, str | None]]:
    """Return the persistent voice override store for a config entry."""
    return Store(
        hass,
        _STORAGE_VERSION,
        f"{DOMAIN}.voice_override.{entry.entry_id}",
    )


async def async_remove_voice_override_storage(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Remove persistent voice override storage for a deleted config entry."""
    await _voice_override_store(hass, entry).async_remove()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up an Adaptive TTS entity."""
    entity = AdaptiveTTSEntity(entry)
    await entity.async_load_voice_override(hass)
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
        self._persistent_voice_override: VoiceOverride | None = None
        self._next_voice_override: VoiceOverride | None = None
        self._override_store: Store[dict[str, str | None]] | None = None
        self._override_lock = asyncio.Lock()

    async def async_load_voice_override(self, hass: HomeAssistant) -> None:
        """Load a valid persistent voice override without blocking entity setup."""
        self._override_store = _voice_override_store(hass, self._entry)
        self._persistent_voice_override = None
        try:
            stored = await self._override_store.async_load()
        except Exception as err:
            _LOGGER.warning(
                "Could not load persistent voice override for %s; "
                "ignoring stored state: %s",
                self._entry.entry_id,
                err,
            )
            return

        if not stored:
            return
        if not isinstance(stored, dict):
            _LOGGER.warning(
                "Discarding malformed persistent voice override for %s",
                self._entry.entry_id,
            )
            await self._async_discard_stored_voice_override("malformed payload")
            return

        voice = stored.get("voice")
        language = stored.get("language")
        token = stored.get("token")
        stored_provider = stored.get("underlying_entity_id")
        if (
            not isinstance(voice, str)
            or not voice
            or not (language is None or isinstance(language, str))
            or not (token is None or isinstance(token, str))
            or not (stored_provider is None or isinstance(stored_provider, str))
        ):
            _LOGGER.warning(
                "Discarding malformed persistent voice override for %s",
                self._entry.entry_id,
            )
            await self._async_discard_stored_voice_override("malformed fields")
            return

        current_provider = self.underlying_entity_id
        if stored_provider and stored_provider != current_provider:
            _LOGGER.info(
                "Discarding persistent voice override for old TTS provider %s; "
                "Adaptive TTS now wraps %s",
                stored_provider,
                current_provider,
            )
            await self._async_discard_stored_voice_override("provider changed")
            return

        effective_token = token or secrets.token_hex(8)
        self._persistent_voice_override = VoiceOverride(
            voice=voice,
            language=(language or None),
            token=effective_token,
        )
        if not token or not stored_provider:
            try:
                await self._override_store.async_save(
                    {
                        "underlying_entity_id": current_provider,
                        "language": self._persistent_voice_override.language,
                        "voice": self._persistent_voice_override.voice,
                        "token": effective_token,
                    }
                )
            except Exception as err:
                _LOGGER.warning(
                    "Could not migrate persistent voice override storage for %s; "
                    "using the loaded override for this session: %s",
                    self._entry.entry_id,
                    err,
                )

    async def _async_discard_stored_voice_override(self, reason: str) -> None:
        """Best-effort remove invalid persisted override state."""
        self._persistent_voice_override = None
        if self._override_store is None:
            return
        try:
            await self._override_store.async_remove()
        except Exception as err:
            _LOGGER.warning(
                "Could not remove discarded persistent voice override for %s (%s): %s",
                self._entry.entry_id,
                reason,
                err,
            )

    @property
    def persistent_voice_override(self) -> VoiceOverride | None:
        """Return the currently persistent voice override."""
        return self._persistent_voice_override

    @property
    def next_voice_override(self) -> VoiceOverride | None:
        """Return the pending one-shot voice override."""
        return self._next_voice_override

    @property
    def _config(self) -> dict[str, Any]:
        return entry_config(self._entry)

    @property
    def underlying_entity_id(self) -> str:
        """Return the configured underlying TTS entity ID."""
        return self._config[CONF_UNDERLYING_TTS_ENTITY]

    def _underlying_for_entity_id(self, entity_id: str) -> TextToSpeechEntity | None:
        """Resolve a non-recursive TTS entity by ID."""
        if not hasattr(self, "hass"):
            return None
        engine = get_tts_entity(self.hass, entity_id)
        if engine is self or getattr(engine, "is_adaptive_tts", False):
            return None
        return engine

    @property
    def _underlying(self) -> TextToSpeechEntity | None:
        return self._underlying_for_entity_id(self.underlying_entity_id)

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
        """Expose provider options while leaving output conversion to Home Assistant."""
        underlying = self._underlying
        if underlying is None:
            return None
        supported_options = underlying.supported_options
        if supported_options is None:
            return None
        return [
            option
            for option in supported_options
            if option not in _PREFERRED_OUTPUT_OPTIONS
        ]

    @property
    @override
    def default_options(self) -> Mapping[str, Any] | None:
        """Expose provider defaults plus a wrapper-only cache discriminator."""
        options = (
            dict(self._underlying.default_options or {}) if self._underlying else {}
        )
        options[CACHE_POLICY_OPTION] = self._policy_cache_value()
        return options

    def _current_policy_snapshot(self, now: datetime | None = None) -> PolicySnapshot:
        """Capture the effective policy for a newly prepared TTS request."""
        config = self._config
        override_scope: str | None = None
        voice_override: VoiceOverride | None = None
        if self._next_voice_override is not None:
            override_scope = SCOPE_NEXT_REQUEST
            voice_override = self._next_voice_override
        elif self._persistent_voice_override is not None:
            override_scope = SCOPE_PERSISTENT
            voice_override = self._persistent_voice_override

        return PolicySnapshot(
            underlying_entity_id=config[CONF_UNDERLYING_TTS_ENTITY],
            quiet_mode_active=self.is_quiet_mode_active(now),
            quiet_option=config[CONF_QUIET_OPTION],
            quiet_language=config.get(CONF_QUIET_LANGUAGE),
            quiet_value=config[CONF_QUIET_VALUE],
            override_scope=override_scope,
            voice_override=voice_override,
        )

    @staticmethod
    def _encode_policy_snapshot(snapshot: PolicySnapshot) -> str:
        """Serialize a policy snapshot into Home Assistant's TTS cache options."""
        override = snapshot.voice_override
        payload: dict[str, Any] = {
            "underlying": snapshot.underlying_entity_id,
            "quiet": snapshot.quiet_mode_active,
            "quiet_option": snapshot.quiet_option,
            "quiet_language": snapshot.quiet_language,
            "quiet_value": snapshot.quiet_value,
            "override": None,
            # A one-shot override must not let two separately prepared streams
            # share the same HA cache entry before either one consumes it.
            "request": (
                secrets.token_hex(8)
                if snapshot.override_scope == SCOPE_NEXT_REQUEST
                else None
            ),
        }
        if override is not None and snapshot.override_scope is not None:
            payload["override"] = {
                "scope": snapshot.override_scope,
                "language": override.language,
                "voice": override.voice,
                "token": override.token,
            }
        return _POLICY_SNAPSHOT_PREFIX + json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        )

    @staticmethod
    def _decode_policy_snapshot(value: str) -> PolicySnapshot:
        """Decode and validate a versioned policy snapshot."""
        try:
            payload = json.loads(value.removeprefix(_POLICY_SNAPSHOT_PREFIX))
        except (TypeError, ValueError) as err:
            raise HomeAssistantError("Invalid Adaptive TTS policy snapshot") from err

        if not isinstance(payload, dict):
            raise HomeAssistantError("Invalid Adaptive TTS policy snapshot")

        underlying = payload.get("underlying")
        quiet = payload.get("quiet")
        quiet_option = payload.get("quiet_option")
        quiet_language = payload.get("quiet_language")
        quiet_value = payload.get("quiet_value")
        if (
            not isinstance(underlying, str)
            or not isinstance(quiet, bool)
            or not isinstance(quiet_option, str)
            or not isinstance(quiet_value, str)
            or not (quiet_language is None or isinstance(quiet_language, str))
        ):
            raise HomeAssistantError("Invalid Adaptive TTS policy snapshot")

        override_scope: str | None = None
        voice_override: VoiceOverride | None = None
        override = payload.get("override")
        if override is not None:
            if not isinstance(override, dict):
                raise HomeAssistantError("Invalid Adaptive TTS policy snapshot")
            override_scope = override.get("scope")
            override_language = override.get("language")
            override_voice = override.get("voice")
            override_token = override.get("token")
            if (
                override_scope not in (SCOPE_NEXT_REQUEST, SCOPE_PERSISTENT)
                or not isinstance(override_voice, str)
                or not override_voice
                or not (override_language is None or isinstance(override_language, str))
                or not isinstance(override_token, str)
                or not override_token
            ):
                raise HomeAssistantError("Invalid Adaptive TTS policy snapshot")
            voice_override = VoiceOverride(
                voice=override_voice,
                language=override_language,
                token=override_token,
            )

        return PolicySnapshot(
            underlying_entity_id=underlying,
            quiet_mode_active=quiet,
            quiet_option=quiet_option,
            quiet_language=quiet_language,
            quiet_value=quiet_value,
            override_scope=override_scope,
            voice_override=voice_override,
        )

    def _legacy_policy_snapshot(
        self, value: str, now: datetime | None = None
    ) -> PolicySnapshot:
        """Interpret cache markers produced before snapshot-v2."""
        config = self._config
        quiet_active = self.is_quiet_mode_active(now)
        override_scope: str | None = None
        voice_override: VoiceOverride | None = None

        if "|" in value:
            parts = value.split("|", 2)
            if len(parts) != 3:
                raise HomeAssistantError("Invalid Adaptive TTS policy snapshot")
            state, marker, _digest = parts
            quiet_active = state == "quiet"
            if marker.startswith("next:"):
                token = marker.partition(":")[2]
                pending = self._next_voice_override
                if pending is not None and pending.token == token:
                    override_scope = SCOPE_NEXT_REQUEST
                    voice_override = pending
            elif marker == "persistent" and self._persistent_voice_override is not None:
                override_scope = SCOPE_PERSISTENT
                voice_override = self._persistent_voice_override
        else:
            quiet_active = value.startswith("quiet:")

        return PolicySnapshot(
            underlying_entity_id=config[CONF_UNDERLYING_TTS_ENTITY],
            quiet_mode_active=quiet_active,
            quiet_option=config[CONF_QUIET_OPTION],
            quiet_language=config.get(CONF_QUIET_LANGUAGE),
            quiet_value=config[CONF_QUIET_VALUE],
            override_scope=override_scope,
            voice_override=voice_override,
        )

    def _policy_snapshot_from_options(
        self,
        options: Mapping[str, Any] | None,
        *,
        now: datetime | None = None,
    ) -> PolicySnapshot:
        """Return the policy captured in manager-processed options."""
        cache_value = (options or {}).get(CACHE_POLICY_OPTION)
        if cache_value is None:
            return self._current_policy_snapshot(now)
        if not isinstance(cache_value, str):
            raise HomeAssistantError("Invalid Adaptive TTS policy snapshot")
        if cache_value.startswith(_POLICY_SNAPSHOT_PREFIX):
            return self._decode_policy_snapshot(cache_value)
        return self._legacy_policy_snapshot(cache_value, now)

    def _policy_cache_value(self) -> str:
        """Return a self-contained snapshot used in Home Assistant's cache key."""
        return self._encode_policy_snapshot(self._current_policy_snapshot())

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
        """Return whether Adaptive TTS can accept streaming text input."""
        return True

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

    def validate_voice_override(
        self, language: str | None, voice: str
    ) -> VoiceOverride:
        """Validate an explicit voice override against the wrapped provider."""
        underlying = self._underlying
        if underlying is None or not underlying.available:
            raise HomeAssistantError(
                f"Underlying TTS entity {self.underlying_entity_id} is unavailable"
            )
        if "voice" not in (underlying.supported_options or []):
            raise HomeAssistantError(
                f"{self.underlying_entity_id} does not support voice overrides"
            )
        if language is not None:
            if language not in underlying.supported_languages:
                raise HomeAssistantError(
                    f"Language '{language}' is not supported by "
                    f"{self.underlying_entity_id}"
                )
            voices = underlying.async_get_supported_voices(language)
            if voices is not None and voice not in {item.voice_id for item in voices}:
                raise HomeAssistantError(
                    f"Voice '{voice}' is not supported by "
                    f"{self.underlying_entity_id} for {language}"
                )
        return VoiceOverride(voice=voice, language=language)

    async def async_set_voice_override(
        self, language: str | None, voice: str, duration: str
    ) -> None:
        """Set a one-shot or persistent voice override."""
        override = self.validate_voice_override(language, voice)
        if duration not in (DURATION_NEXT_REQUEST, DURATION_UNTIL_CHANGED):
            raise HomeAssistantError(f"Unsupported voice override duration: {duration}")

        async with self._override_lock:
            if duration == DURATION_NEXT_REQUEST:
                self._next_voice_override = VoiceOverride(
                    voice=override.voice,
                    language=override.language,
                    token=secrets.token_hex(8),
                )
                return

            if self._override_store is None:
                raise HomeAssistantError(
                    "Adaptive TTS voice override storage is unavailable"
                )
            persistent = VoiceOverride(
                voice=override.voice,
                language=override.language,
                token=secrets.token_hex(8),
            )
            await self._override_store.async_save(
                {
                    "underlying_entity_id": self.underlying_entity_id,
                    "language": persistent.language,
                    "voice": persistent.voice,
                    "token": persistent.token,
                }
            )
            self._persistent_voice_override = persistent

    async def async_clear_voice_override(self, scope: str = SCOPE_ALL) -> None:
        """Clear one-shot and/or persistent voice overrides."""
        if scope not in (SCOPE_ALL, SCOPE_NEXT_REQUEST, SCOPE_PERSISTENT):
            raise HomeAssistantError(f"Unsupported voice override scope: {scope}")

        async with self._override_lock:
            if scope in (SCOPE_ALL, SCOPE_PERSISTENT):
                if self._override_store is not None:
                    await self._override_store.async_remove()
                self._persistent_voice_override = None
            if scope in (SCOPE_ALL, SCOPE_NEXT_REQUEST):
                self._next_voice_override = None

    def _override_from_snapshot(self, snapshot: PolicySnapshot) -> VoiceOverride | None:
        """Return the explicit override captured for this request."""
        override = snapshot.voice_override
        if override is None:
            return None
        if snapshot.override_scope == SCOPE_NEXT_REQUEST:
            pending = self._next_voice_override
            if pending is not None and pending.token == override.token:
                return override
            return None
        if snapshot.override_scope == SCOPE_PERSISTENT:
            return override
        return None

    def _clear_matching_next_voice_override(
        self, override: VoiceOverride | None
    ) -> None:
        """Clear a matching one-shot override while the override lock is held."""
        if override is None or override.token is None:
            return
        pending = self._next_voice_override
        if pending is not None and pending.token == override.token:
            self._next_voice_override = None

    async def _async_consume_next_voice_override(
        self, override: VoiceOverride | None, scope: str | None
    ) -> None:
        """Consume a matching one-shot override when synthesis actually starts."""
        if scope != SCOPE_NEXT_REQUEST:
            return
        async with self._override_lock:
            self._clear_matching_next_voice_override(override)

    async def _async_clear_failed_voice_override(
        self, override: VoiceOverride | None, scope: str | None
    ) -> None:
        """Clear an explicit override after a request using it fails."""
        if override is None:
            return
        if scope == SCOPE_NEXT_REQUEST:
            await self._async_consume_next_voice_override(override, scope)
            return
        if scope != SCOPE_PERSISTENT:
            return

        async with self._override_lock:
            persistent = self._persistent_voice_override
            if persistent is None or persistent.token != override.token:
                return
            if self._override_store is not None:
                try:
                    await self._override_store.async_remove()
                except Exception as err:
                    _LOGGER.error(
                        "Failed to remove invalid persistent voice override "
                        "from storage: %s",
                        err,
                    )
            self._persistent_voice_override = None
        _LOGGER.warning(
            "Cleared persistent voice override %s for %s after TTS generation failed",
            override.voice,
            self.underlying_entity_id,
        )

    def _resolve_request_with_snapshot(
        self,
        language: str | None,
        options: Mapping[str, Any] | None,
        snapshot: PolicySnapshot,
    ) -> ResolvedRequest:
        """Validate and apply a previously captured Adaptive TTS policy."""
        underlying = self._underlying_for_entity_id(snapshot.underlying_entity_id)
        if underlying is None:
            _LOGGER.error(
                "Underlying TTS entity %s is missing, unavailable, or recursive",
                snapshot.underlying_entity_id,
            )
            raise HomeAssistantError(
                f"Underlying TTS entity {snapshot.underlying_entity_id} "
                "is not available"
            )
        if not underlying.available:
            _LOGGER.error(
                "Underlying TTS entity %s is unavailable",
                snapshot.underlying_entity_id,
            )
            raise HomeAssistantError(
                f"Underlying TTS entity {snapshot.underlying_entity_id} is unavailable"
            )

        incoming_options = dict(options or {})
        incoming_options.pop(CACHE_POLICY_OPTION, None)
        explicit_override = self._override_from_snapshot(snapshot)
        quiet_active = snapshot.quiet_mode_active
        normal_language = language or underlying.default_language
        effective_language = normal_language

        if explicit_override and explicit_override.language:
            effective_language = explicit_override.language
        elif quiet_active and snapshot.quiet_option == "voice":
            quiet_language = snapshot.quiet_language or normal_language
            if quiet_language in underlying.supported_languages:
                effective_language = quiet_language
            else:
                _LOGGER.warning(
                    "Ignoring quiet-hours voice policy for %s because language %s "
                    "is no longer supported; using normal TTS settings",
                    snapshot.underlying_entity_id,
                    quiet_language,
                )
                quiet_active = False

        if effective_language not in underlying.supported_languages:
            _LOGGER.error(
                "Underlying TTS entity %s does not support language %s",
                snapshot.underlying_entity_id,
                effective_language,
            )
            raise HomeAssistantError(
                f"Language '{effective_language}' is not supported by "
                f"{snapshot.underlying_entity_id}"
            )

        effective_options = dict(underlying.default_options or {})
        effective_options.update(incoming_options)
        if quiet_active:
            option_name = snapshot.quiet_option
            option_value = snapshot.quiet_value

            # A user-requested voice override intentionally supersedes a
            # quiet voice, so only validate/apply quiet policy that would
            # actually affect this request.
            if not (option_name == "voice" and explicit_override is not None):
                try:
                    supported_options = underlying.supported_options or []
                except Exception as err:
                    _LOGGER.warning(
                        "Ignoring quiet-hours policy for %s because provider "
                        "option metadata failed: %s",
                        snapshot.underlying_entity_id,
                        err,
                    )
                    quiet_active = False
                else:
                    if option_name not in supported_options:
                        _LOGGER.warning(
                            "Ignoring quiet-hours option %s for %s because it is "
                            "no longer supported; using normal TTS settings",
                            option_name,
                            snapshot.underlying_entity_id,
                        )
                        quiet_active = False
                    elif option_name == "voice":
                        try:
                            voices = underlying.async_get_supported_voices(
                                effective_language
                            )
                        except Exception as err:
                            _LOGGER.warning(
                                "Ignoring quiet-hours voice policy for %s because "
                                "voice metadata failed: %s",
                                snapshot.underlying_entity_id,
                                err,
                            )
                            quiet_active = False
                        else:
                            if voices is not None and option_value not in {
                                voice.voice_id for voice in voices
                            }:
                                _LOGGER.warning(
                                    "Ignoring quiet-hours voice %s for %s/%s because "
                                    "it is no longer supported; using normal TTS "
                                    "settings",
                                    option_value,
                                    snapshot.underlying_entity_id,
                                    effective_language,
                                )
                                quiet_active = False
                            else:
                                effective_options[option_name] = option_value
                    else:
                        effective_options[option_name] = option_value

            if (
                not quiet_active
                and option_name == "voice"
                and explicit_override is None
            ):
                effective_language = normal_language
                if effective_language not in underlying.supported_languages:
                    _LOGGER.error(
                        "Underlying TTS entity %s does not support language %s",
                        snapshot.underlying_entity_id,
                        effective_language,
                    )
                    raise HomeAssistantError(
                        f"Language '{effective_language}' is not supported by "
                        f"{snapshot.underlying_entity_id}"
                    )

        if explicit_override is not None:
            if "voice" not in (underlying.supported_options or []):
                raise HomeAssistantError(
                    f"{snapshot.underlying_entity_id} does not support voice overrides"
                )
            voices = underlying.async_get_supported_voices(effective_language)
            if voices is not None and explicit_override.voice not in {
                voice.voice_id for voice in voices
            }:
                raise HomeAssistantError(
                    f"Voice '{explicit_override.voice}' is not supported by "
                    f"{snapshot.underlying_entity_id} for {effective_language}"
                )
            effective_options["voice"] = explicit_override.voice

        return ResolvedRequest(
            underlying_entity_id=snapshot.underlying_entity_id,
            language=effective_language,
            options=effective_options,
            quiet_mode_active=quiet_active,
            voice_override=explicit_override,
            voice_override_scope=(
                snapshot.override_scope if explicit_override is not None else None
            ),
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
        snapshot = self._policy_snapshot_from_options(options, now=now)
        return self._resolve_request_with_snapshot(language, options, snapshot)

    async def async_resolve_request_for_preflight(
        self,
        language: str | None,
        options: Mapping[str, Any] | None,
    ) -> ResolvedRequest:
        """Resolve without consuming a valid one-shot, but recover failed overrides."""
        snapshot = self._policy_snapshot_from_options(options)
        request_override = self._override_from_snapshot(snapshot)
        request_scope = (
            snapshot.override_scope if request_override is not None else None
        )
        try:
            return self._resolve_request_with_snapshot(language, options, snapshot)
        except Exception:
            await self._async_clear_failed_voice_override(
                request_override, request_scope
            )
            raise

    async def _async_resolve_for_synthesis(
        self,
        language: str | None,
        options: Mapping[str, Any] | None,
    ) -> ResolvedRequest:
        """Resolve a synthesis request and clear a failing explicit override."""
        snapshot = self._policy_snapshot_from_options(options)

        # A next-request override must be claimed atomically. Otherwise two
        # synthesis tasks can both resolve the same pending token while another
        # override mutation holds this lock, then both use the supposedly
        # one-shot voice after the lock becomes available.
        if snapshot.override_scope == SCOPE_NEXT_REQUEST:
            async with self._override_lock:
                request_override = self._override_from_snapshot(snapshot)
                try:
                    resolved = self._resolve_request_with_snapshot(
                        language, options, snapshot
                    )
                except Exception:
                    self._clear_matching_next_voice_override(request_override)
                    raise
                self._clear_matching_next_voice_override(resolved.voice_override)
                return resolved

        request_override = self._override_from_snapshot(snapshot)
        request_scope = (
            snapshot.override_scope if request_override is not None else None
        )
        try:
            return self._resolve_request_with_snapshot(language, options, snapshot)
        except Exception:
            await self._async_clear_failed_voice_override(
                request_override, request_scope
            )
            raise

    @override
    async def async_get_tts_audio(
        self, message: str, language: str, options: dict[str, Any]
    ) -> TtsAudioType:
        """Generate one-shot audio through the underlying entity."""
        resolved = await self._async_resolve_for_synthesis(language, options)
        underlying = self._underlying_for_entity_id(resolved.underlying_entity_id)
        if underlying is None:
            await self._async_clear_failed_voice_override(
                resolved.voice_override, resolved.voice_override_scope
            )
            raise HomeAssistantError(
                f"Underlying TTS entity {resolved.underlying_entity_id} disappeared"
            )
        try:
            extension, data = await underlying.async_get_tts_audio(
                message, resolved.language, resolved.options
            )
            extension, data = _validate_tts_audio_result(
                resolved.underlying_entity_id, extension, data
            )
        except HomeAssistantError:
            await self._async_clear_failed_voice_override(
                resolved.voice_override, resolved.voice_override_scope
            )
            raise
        except Exception as err:
            await self._async_clear_failed_voice_override(
                resolved.voice_override, resolved.voice_override_scope
            )
            _LOGGER.error(
                "Underlying TTS generation failed for %s: %s",
                resolved.underlying_entity_id,
                err,
            )
            raise HomeAssistantError(
                f"TTS generation failed in {resolved.underlying_entity_id}: {err}"
            ) from err
        return extension, data

    @override
    async def async_stream_tts_audio(
        self, request: TTSAudioRequest
    ) -> TTSAudioResponse:
        """Forward streaming input when supported, otherwise safely collect it."""
        resolved = await self._async_resolve_for_synthesis(
            request.language, request.options
        )
        underlying = self._underlying_for_entity_id(resolved.underlying_entity_id)
        if underlying is None:
            await self._async_clear_failed_voice_override(
                resolved.voice_override, resolved.voice_override_scope
            )
            raise HomeAssistantError(
                f"Underlying TTS entity {resolved.underlying_entity_id} disappeared"
            )
        try:
            supports_streaming = underlying.async_supports_streaming_input()
        except HomeAssistantError:
            await self._async_clear_failed_voice_override(
                resolved.voice_override, resolved.voice_override_scope
            )
            raise
        except Exception as err:
            await self._async_clear_failed_voice_override(
                resolved.voice_override, resolved.voice_override_scope
            )
            raise HomeAssistantError(
                f"Could not read TTS streaming capability from "
                f"{resolved.underlying_entity_id}: {err}"
            ) from err

        if supports_streaming:
            try:
                response = await underlying.async_stream_tts_audio(
                    TTSAudioRequest(
                        resolved.language, resolved.options, request.message_gen
                    )
                )
                response = _validate_stream_response(
                    resolved.underlying_entity_id, response
                )
            except HomeAssistantError:
                await self._async_clear_failed_voice_override(
                    resolved.voice_override, resolved.voice_override_scope
                )
                raise
            except Exception as err:
                await self._async_clear_failed_voice_override(
                    resolved.voice_override, resolved.voice_override_scope
                )
                _LOGGER.error(
                    "Underlying streaming TTS generation failed for %s: %s",
                    resolved.underlying_entity_id,
                    err,
                )
                raise HomeAssistantError(
                    f"Streaming TTS generation failed in "
                    f"{resolved.underlying_entity_id}: {err}"
                ) from err

            async def guarded_data_gen():
                has_audio = False
                try:
                    async for chunk in response.data_gen:
                        if not isinstance(chunk, bytes):
                            raise HomeAssistantError(
                                f"Invalid TTS audio chunk returned by "
                                f"{resolved.underlying_entity_id}"
                            )
                        if chunk:
                            has_audio = True
                        yield chunk
                except HomeAssistantError:
                    await self._async_clear_failed_voice_override(
                        resolved.voice_override, resolved.voice_override_scope
                    )
                    raise
                except Exception as err:
                    await self._async_clear_failed_voice_override(
                        resolved.voice_override, resolved.voice_override_scope
                    )
                    raise HomeAssistantError(
                        f"Streaming TTS audio failed in "
                        f"{resolved.underlying_entity_id}: {err}"
                    ) from err
                if not has_audio:
                    await self._async_clear_failed_voice_override(
                        resolved.voice_override, resolved.voice_override_scope
                    )
                    raise HomeAssistantError(
                        f"No TTS audio returned by {resolved.underlying_entity_id}"
                    )

            return TTSAudioResponse(response.extension, guarded_data_gen())

        try:
            message = "".join([chunk async for chunk in request.message_gen])
            extension, data = await underlying.async_get_tts_audio(
                message, resolved.language, resolved.options
            )
            extension, data = _validate_tts_audio_result(
                resolved.underlying_entity_id, extension, data
            )
        except HomeAssistantError:
            await self._async_clear_failed_voice_override(
                resolved.voice_override, resolved.voice_override_scope
            )
            raise
        except Exception as err:
            await self._async_clear_failed_voice_override(
                resolved.voice_override, resolved.voice_override_scope
            )
            _LOGGER.error(
                "Underlying TTS generation failed for %s: %s",
                resolved.underlying_entity_id,
                err,
            )
            raise HomeAssistantError(
                f"TTS generation failed in {resolved.underlying_entity_id}: {err}"
            ) from err

        async def data_gen():
            yield data

        return TTSAudioResponse(extension, data_gen())
