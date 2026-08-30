"""Adaptive TTS integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_UNDERLYING_TTS_ENTITY,
    DATA_ENTITIES,
    DATA_FRONTEND_REGISTERED,
    DATA_SERVICES_REGISTERED,
    DOMAIN,
    PANEL_URL_PATH,
    PANEL_WEB_COMPONENT,
    STATIC_URL_PATH,
)
from .helpers import entry_config, is_adaptive_entity
from .preview import async_register_websocket_commands
from .services import async_register_services
from .tts import async_remove_voice_override_storage

PLATFORMS = [Platform.TTS]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up shared Adaptive TTS frontend and backend resources."""
    domain_data = hass.data.setdefault(
        DOMAIN,
        {
            DATA_ENTITIES: {},
            DATA_FRONTEND_REGISTERED: False,
            DATA_SERVICES_REGISTERED: False,
        },
    )
    domain_data.setdefault(DATA_ENTITIES, {})
    domain_data.setdefault(DATA_FRONTEND_REGISTERED, False)
    domain_data.setdefault(DATA_SERVICES_REGISTERED, False)

    if not domain_data[DATA_FRONTEND_REGISTERED]:
        frontend_path = Path(__file__).parent / "frontend"
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL_PATH, str(frontend_path), cache_headers=False)]
        )
        await panel_custom.async_register_panel(
            hass=hass,
            frontend_url_path=PANEL_URL_PATH,
            config_panel_domain=DOMAIN,
            webcomponent_name=PANEL_WEB_COMPONENT,
            module_url=f"{STATIC_URL_PATH}/adaptive-tts-panel.js",
            require_admin=True,
        )
        async_register_websocket_commands(hass)
        domain_data[DATA_FRONTEND_REGISTERED] = True

    if not domain_data[DATA_SERVICES_REGISTERED]:
        async_register_services(hass)
        domain_data[DATA_SERVICES_REGISTERED] = True

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up an Adaptive TTS config entry."""
    underlying_entity_id = entry_config(entry)[CONF_UNDERLYING_TTS_ENTITY]
    if is_adaptive_entity(hass, underlying_entity_id):
        raise ConfigEntryError(
            "Adaptive TTS entities cannot wrap other Adaptive TTS entities"
        )
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an Adaptive TTS config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN][DATA_ENTITIES].pop(entry.entry_id, None)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove storage owned by a permanently deleted config entry."""
    await async_remove_voice_override_storage(hass, entry)


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload an entry after its options change."""
    await hass.config_entries.async_reload(entry.entry_id)