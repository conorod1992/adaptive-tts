"""Adaptive TTS entity extension for Conditional Voice Routing."""

from __future__ import annotations

import json
import logging
from dataclasses import replace

from homeassistant.exceptions import HomeAssistantError

from .const import SCOPE_ROUTING
from .routing import ConditionalVoiceRouter
from .tts import AdaptiveTTSEntity, PolicySnapshot, VoiceOverride

_LOGGER = logging.getLogger(__name__)
_POLICY_SNAPSHOT_PREFIX = "snapshot-v2:"


class RoutedAdaptiveTTSEntity(AdaptiveTTSEntity):
    """Adaptive TTS entity with ordered native-HA conditional voice routing."""

    def __init__(self, entry) -> None:
        """Initialize the routed wrapper."""
        super().__init__(entry)
        self._conditional_voice_router = ConditionalVoiceRouter(entry)

    async def async_load_voice_override(self, hass) -> None:
        """Load manual override state and compile conditional routing rules."""
        await super().async_load_voice_override(hass)
        await self._conditional_voice_router.async_setup(hass)
        self.async_on_remove(self._conditional_voice_router.async_unload)

    def _current_policy_snapshot(self, now=None) -> PolicySnapshot:
        """Add the first valid matching route below explicit manual overrides."""
        snapshot = super()._current_policy_snapshot(now)
        if snapshot.voice_override is not None:
            return snapshot

        for route in self._conditional_voice_router.matching_voices():
            try:
                validated = self.validate_voice_override(route.language, route.voice)
            except HomeAssistantError as err:
                _LOGGER.warning(
                    "Ignoring matching Conditional Voice Routing rule %s (%s): %s",
                    route.rule_name,
                    route.rule_id,
                    err,
                )
                continue
            return replace(
                snapshot,
                override_scope=SCOPE_ROUTING,
                voice_override=VoiceOverride(
                    voice=validated.voice,
                    language=validated.language,
                    token=route.rule_id,
                ),
            )
        return snapshot

    @staticmethod
    def _decode_policy_snapshot(value: str) -> PolicySnapshot:
        """Decode current snapshots while extending the base scope vocabulary."""
        if not value.startswith(_POLICY_SNAPSHOT_PREFIX):
            return AdaptiveTTSEntity._decode_policy_snapshot(value)
        try:
            payload = json.loads(value.removeprefix(_POLICY_SNAPSHOT_PREFIX))
        except (TypeError, ValueError) as err:
            raise HomeAssistantError("Invalid Adaptive TTS policy snapshot") from err
        override = payload.get("override") if isinstance(payload, dict) else None
        if not isinstance(override, dict) or override.get("scope") != SCOPE_ROUTING:
            return AdaptiveTTSEntity._decode_policy_snapshot(value)

        # Let the mature base decoder validate every existing field by temporarily
        # mapping the new automatic scope to an accepted non-one-shot scope.
        override["scope"] = "persistent"
        base_value = _POLICY_SNAPSHOT_PREFIX + json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        )
        snapshot = AdaptiveTTSEntity._decode_policy_snapshot(base_value)
        return replace(snapshot, override_scope=SCOPE_ROUTING)

    def _override_from_snapshot(self, snapshot: PolicySnapshot) -> VoiceOverride | None:
        """Return routed voices directly; preserve manual one-shot token semantics."""
        if snapshot.override_scope == SCOPE_ROUTING:
            return snapshot.voice_override
        return super()._override_from_snapshot(snapshot)
