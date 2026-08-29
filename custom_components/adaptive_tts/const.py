"""Constants for Adaptive TTS."""

from typing import Final

DOMAIN: Final = "adaptive_tts"
NAME: Final = "Adaptive TTS"
VERSION: Final = "0.1.0"

CONF_UNDERLYING_TTS_ENTITY: Final = "underlying_tts_entity"
CONF_QUIET_MODE: Final = "quiet_mode"
CONF_QUIET_START: Final = "quiet_start"
CONF_QUIET_END: Final = "quiet_end"
CONF_QUIET_OPTION: Final = "quiet_option"
CONF_QUIET_VALUE: Final = "quiet_value"

DEFAULT_QUIET_START: Final = "23:00:00"
DEFAULT_QUIET_END: Final = "07:00:00"
DEFAULT_QUIET_OPTION: Final = "voice"

DATA_ENTITIES: Final = "entities"
DATA_FRONTEND_REGISTERED: Final = "frontend_registered"

PANEL_URL_PATH: Final = "adaptive-tts"
STATIC_URL_PATH: Final = "/adaptive_tts_static"
PANEL_WEB_COMPONENT: Final = "adaptive-tts-panel"
