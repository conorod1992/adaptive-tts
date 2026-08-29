"""WebSocket backend for the Adaptive TTS test panel."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping
from typing import Any

import voluptuous as vol
from homeassistant.components import tts, websocket_api
from homeassistant.components.tts.helper import get_engine_instance
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .tts import AdaptiveTTSEntity


def _json_value(value: Any) -> Any:
    """Convert provider metadata to a WebSocket-safe value."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_value(item) for item in value]
    return str(value)


def _engine_info(hass: HomeAssistant, engine_id: str, language: str | None) -> dict:
    """Serialize metadata for one TTS entity."""
    engine = get_engine_instance(hass, engine_id)
    if engine is None:
        raise HomeAssistantError(f"TTS entity {engine_id} was not found")
    effective_language = language or engine.default_language
    voices = engine.async_get_supported_voices(effective_language) or []
    return {
        "engine_id": engine_id,
        "name": getattr(engine, "name", None) or engine_id,
        "is_adaptive": isinstance(engine, AdaptiveTTSEntity),
        "underlying_entity_id": (
            engine.underlying_entity_id
            if isinstance(engine, AdaptiveTTSEntity)
            else engine_id
        ),
        "default_language": engine.default_language,
        "supported_languages": list(engine.supported_languages),
        "supported_options": list(engine.supported_options or []),
        "default_options": _json_value(dict(engine.default_options or {})),
        "voices": [
            {"voice_id": voice.voice_id, "name": voice.name} for voice in voices
        ],
        "available": getattr(engine, "available", True),
    }


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "adaptive_tts/info"})
@callback
def websocket_info(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return Assist pipelines and TTS entities for the test panel."""
    # Import after Home Assistant has set up the declared assist_pipeline
    # dependency, including its platform-specific requirements.
    from homeassistant.components import assist_pipeline

    pipelines = [
        {
            "id": pipeline.id,
            "name": pipeline.name,
            "tts_engine": pipeline.tts_engine,
            "tts_language": pipeline.tts_language,
            "tts_voice": pipeline.tts_voice,
        }
        for pipeline in assist_pipeline.async_get_pipelines(hass)
    ]
    engines = []
    for engine_id in hass.states.async_entity_ids("tts"):
        try:
            engines.append(_engine_info(hass, engine_id, None))
        except HomeAssistantError:
            continue
    connection.send_result(msg["id"], {"pipelines": pipelines, "engines": engines})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "adaptive_tts/engine",
        vol.Required("engine_id"): cv.entity_id,
        vol.Optional("language"): str,
    }
)
@callback
def websocket_engine(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return current provider metadata and voices."""
    try:
        info = _engine_info(hass, msg["engine_id"], msg.get("language"))
    except HomeAssistantError as err:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, str(err))
        return
    connection.send_result(msg["id"], info)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "adaptive_tts/generate",
        vol.Required("engine_id"): cv.entity_id,
        vol.Required("message"): vol.All(str, vol.Length(min=1, max=5000)),
        vol.Optional("language"): str,
        vol.Optional("options", default={}): dict,
    }
)
@callback
def websocket_generate(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Create a bounded, memory-only Home Assistant TTS preview stream."""
    try:
        result = create_preview(hass, msg)
    except (HomeAssistantError, ValueError) as err:
        connection.send_error(
            msg["id"], websocket_api.ERR_UNKNOWN_ERROR, f"TTS generation failed: {err}"
        )
        return

    connection.send_result(msg["id"], result)


@callback
def create_preview(hass: HomeAssistant, msg: dict[str, Any]) -> dict[str, Any]:
    """Create a native, bounded TTS preview and return frontend metadata."""
    stream = tts.async_create_stream(
        hass,
        engine=msg["engine_id"],
        language=msg.get("language"),
        options=msg.get("options", {}),
    )
    engine = get_engine_instance(hass, msg["engine_id"])
    if engine is None:
        raise HomeAssistantError(f"TTS entity {msg['engine_id']} was not found")

    if isinstance(engine, AdaptiveTTSEntity):
        resolved = engine.resolve_request(stream.language, stream.options)
        underlying_entity_id = resolved.underlying_entity_id
        effective_language = resolved.language
        effective_options = resolved.options
        quiet_active = resolved.quiet_mode_active
    else:
        underlying_entity_id = msg["engine_id"]
        effective_language = stream.language
        effective_options = stream.options
        quiet_active = False

    async def message_gen() -> AsyncGenerator[str]:
        yield msg["message"]

    # A message stream always uses HA's in-memory cache path, even for a
    # provider that internally falls back to one-shot synthesis.
    stream.async_set_message_stream(message_gen())
    return {
        "url": stream.url,
        "extension": stream.extension,
        "engine_id": msg["engine_id"],
        "underlying_entity_id": underlying_entity_id,
        "language": effective_language,
        "options": _json_value(effective_options),
        "quiet_mode_active": quiet_active,
        "storage": "Home Assistant temporary in-memory TTS cache",
    }


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register the Adaptive TTS panel commands."""
    websocket_api.async_register_command(hass, websocket_info)
    websocket_api.async_register_command(hass, websocket_engine)
    websocket_api.async_register_command(hass, websocket_generate)
