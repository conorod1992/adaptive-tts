"""Tests for Adaptive TTS config-entry migration."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_tts import async_migrate_entry
from custom_components.adaptive_tts.const import (
    CONF_QUIET_END,
    CONF_QUIET_LANGUAGE,
    CONF_QUIET_MODE,
    CONF_QUIET_OPTION,
    CONF_QUIET_START,
    CONF_QUIET_VALUE,
    CONF_UNDERLYING_TTS_ENTITY,
    DOMAIN,
)


@pytest.mark.asyncio
async def test_v1_migration_removes_quiet_hours_settings(hass) -> None:
    """Version 2 removes the TTS-owned quiet-hours policy from stored config."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bedroom TTS",
        version=1,
        data={
            CONF_UNDERLYING_TTS_ENTITY: "tts.source",
            CONF_QUIET_MODE: True,
            CONF_QUIET_START: "23:00:00",
            CONF_QUIET_END: "07:00:00",
            CONF_QUIET_OPTION: "voice",
            CONF_QUIET_LANGUAGE: "en-GB",
        },
        options={CONF_QUIET_VALUE: "whisper"},
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 2
    assert entry.data == {CONF_UNDERLYING_TTS_ENTITY: "tts.source"}
    assert entry.options == {}


@pytest.mark.asyncio
async def test_v2_migration_is_noop(hass) -> None:
    """Current entries are not rewritten on subsequent setup."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bedroom TTS",
        version=2,
        data={CONF_UNDERLYING_TTS_ENTITY: "tts.source"},
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    assert entry.version == 2
    assert entry.data == {CONF_UNDERLYING_TTS_ENTITY: "tts.source"}
