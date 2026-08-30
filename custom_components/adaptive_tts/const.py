"""Constants for Adaptive TTS."""

from typing import Final

DOMAIN: Final = "adaptive_tts"
NAME: Final = "Adaptive TTS"
VERSION: Final = "0.2.5"

CONF_UNDERLYING_TTS_ENTITY: Final = "underlying_tts_entity"
CONF_QUIET_MODE: Final = "quiet_mode"
CONF_QUIET_START: Final = "quiet_start"
CONF_QUIET_END: Final = "quiet_end"
CONF_QUIET_OPTION: Final = "quiet_option"
CONF_QUIET_LANGUAGE: Final = "quiet_language"
CONF_QUIET_VALUE: Final = "quiet_value"

# Included in the wrapper's processed options so Home Assistant's normal TTS
# cache identity reflects the effective policy. It is always removed before
# options are delegated to the underlying provider.
CACHE_POLICY_OPTION: Final = "_adaptive_tts_policy"

DEFAULT_QUIET_START: Final = "23:00:00"
DEFAULT_QUIET_END: Final = "07:00:00"
DEFAULT_QUIET_OPTION: Final = "voice"

DATA_ENTITIES: Final = "entities"
DATA_FRONTEND_REGISTERED: Final = "frontend_registered"
DATA_SERVICES_REGISTERED: Final = "services_registered"

SERVICE_SET_VOICE_OVERRIDE: Final = "set_voice_override"
SERVICE_CLEAR_VOICE_OVERRIDE: Final = "clear_voice_override"
ATTR_VOICE: Final = "voice"
ATTR_LANGUAGE: Final = "language"
ATTR_DURATION: Final = "duration"
ATTR_SCOPE: Final = "scope"
DURATION_NEXT_REQUEST: Final = "next_request"
DURATION_UNTIL_CHANGED: Final = "until_changed"
SCOPE_ALL: Final = "all"
SCOPE_NEXT_REQUEST: Final = "next_request"
SCOPE_PERSISTENT: Final = "persistent"

PANEL_URL_PATH: Final = "adaptive-tts"
STATIC_URL_PATH: Final = "/adaptive_tts_static"
PANEL_WEB_COMPONENT: Final = "adaptive-tts-panel"
