"""WebSocket backend for the Adaptive TTS test panel."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, Mapping
from typing import Any

import voluptuous as vol
from homeassistant.components import tts, websocket_api
from homeassistant.components.tts.helper import get_engine_instance
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import CACHE_POLICY_OPTION
from .tts import AdaptiveTTSEntity

_LOGGER = logging.getLogger(__name__)


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
    """Serialize metadata for one TTS entity without hiding a broken provider."""
    engine = get_engine_instance(hass, engine_id)
    if engine is None:
        raise HomeAssistantError(f"TTS entity {engine_id} was not found")

    metadata_errors: dict[str, str] = {}

    def read_metadata(key: str, reader, default):
        try:
            return reader()
        except Exception as err:
            metadata_errors[key] = type(err).__name__
            _LOGGER.warning(
                "Could not read %s metadata for TTS provider %s: %s",
                key,
                engine_id,
                err,
            )
            return default

    available = read_metadata(
        "available", lambda: bool(getattr(engine, "available", True)), False
    )
    default_language = read_metadata(
        "default_language", lambda: engine.default_language, ""
    )
    supported_languages = read_metadata(
        "supported_languages", lambda: list(engine.supported_languages), []
    )
    supported_options = read_metadata(
        "supported_options", lambda: list(engine.supported_options or []), []
    )
    default_options = read_metadata(
        "default_options", lambda: dict(engine.default_options or {}), {}
    )

    effective_language = language or default_language
    voices = None
    if available and effective_language:
        try:
            voices = engine.async_get_supported_voices(effective_language)
        except Exception as err:
            metadata_errors["voices"] = type(err).__name__
            _LOGGER.warning(
                "Could not enumerate voices for TTS provider %s (%s): %s",
                engine_id,
                effective_language,
                err,
            )

    return {
        "engine_id": engine_id,
        "name": getattr(engine, "name", None) or engine_id,
        "is_adaptive": isinstance(engine, AdaptiveTTSEntity),
        "underlying_entity_id": (
            engine.underlying_entity_id
            if isinstance(engine, AdaptiveTTSEntity)
            else engine_id
        ),
        "default_language": default_language,
        "supported_languages": supported_languages,
        "supported_options": supported_options,
        "default_options": _json_value(
            {
                key: value
                for key, value in default_options.items()
                if key != CACHE_POLICY_OPTION
            }
        ),
        "voices": [
            {"voice_id": voice.voice_id, "name": voice.name} for voice in (voices or [])
        ],
        "voices_enumerated": voices is not None,
        "available": available,
        "metadata_errors": metadata_errors,
    }


def _engine_infos(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Return provider metadata while isolating failures to one provider."""
    engines = []
    for engine_id in hass.states.async_entity_ids("tts"):
        try:
            engines.append(_engine_info(hass, engine_id, None))
        except Exception as err:
            _LOGGER.warning("Skipping broken TTS provider %s: %s", engine_id, err)
    return engines


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
    connection.send_result(
        msg["id"], {"pipelines": pipelines, "engines": _engine_infos(hass)}
    )


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
    except Exception as err:
        _LOGGER.exception("Failed to inspect TTS provider %s", msg["engine_id"])
        connection.send_error(
            msg["id"],
            websocket_api.ERR_UNKNOWN_ERROR,
            f"Could not read TTS provider metadata: {err}",
        )
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
@websocket_api.async_response
async def websocket_generate(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Create a bounded, memory-only Home Assistant TTS preview stream."""
    try:
        result = await create_preview(hass, msg)
    except Exception as err:
        connection.send_error(
            msg["id"], websocket_api.ERR_UNKNOWN_ERROR, f"TTS generation failed: {err}"
        )
        return

    connection.send_result(msg["id"], result)


async def create_preview(hass: HomeAssistant, msg: dict[str, Any]) -> dict[str, Any]:
    """Generate a bounded TTS preview before returning replay metadata."""
    engine = get_engine_instance(hass, msg["engine_id"])
    if engine is None:
        raise HomeAssistantError(f"TTS entity {msg['engine_id']} was not found")
    if not getattr(engine, "available", True):
        raise HomeAssistantError(
            f"TTS entity {msg['engine_id']} is currently unavailable"
        )

    # Reject an unavailable provider before Home Assistant allocates and
    # registers a temporary result stream for a request that cannot run.
    stream = tts.async_create_stream(
        hass,
        engine=msg["engine_id"],
        language=msg.get("language"),
        options=msg.get("options", {}),
    )
    try:
        if isinstance(engine, AdaptiveTTSEntity):
            resolved = await engine.async_resolve_request_for_preflight(
                stream.language, stream.options
            )
            underlying_entity_id = resolved.underlying_entity_id
            effective_language = resolved.language
            effective_options = resolved.options
        else:
            underlying_entity_id = msg["engine_id"]
            effective_language = stream.language
            effective_options = stream.options

        async def message_gen() -> AsyncGenerator[str]:
            yield msg["message"]

        # A message stream always uses HA's in-memory cache path, even for a
        # provider that internally falls back to one-shot synthesis.
        stream.async_set_message_stream(message_gen())
        has_audio = False
        async for chunk in stream.async_stream_result():
            if chunk:
                has_audio = True
        if not has_audio:
            raise HomeAssistantError("The provider returned no preview audio")
    except asyncio.CancelledError:
        stream.delete()
        raise
    except HomeAssistantError:
        stream.delete()
        raise
    except Exception as err:
        stream.delete()
        raise HomeAssistantError(str(err)) from err

    return {
        "url": stream.url,
        "extension": stream.extension,
        "engine_id": msg["engine_id"],
        "underlying_entity_id": underlying_entity_id,
        "language": effective_language,
        "options": _json_value(effective_options),
        "storage": "Home Assistant temporary in-memory TTS cache",
    }


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register the Adaptive TTS panel commands."""
    websocket_api.async_register_command(hass, websocket_info)
    websocket_api.async_register_command(hass, websocket_engine)
    websocket_api.async_register_command(hass, websocket_generate)
