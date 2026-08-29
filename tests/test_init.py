"""Tests for integration setup safeguards."""

from unittest.mock import patch

import pytest
from homeassistant.exceptions import ConfigEntryError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adaptive_tts import async_setup_entry
from custom_components.adaptive_tts.const import (
    CONF_QUIET_END,
    CONF_QUIET_MODE,
    CONF_QUIET_OPTION,
    CONF_QUIET_START,
    CONF_QUIET_VALUE,
    CONF_UNDERLYING_TTS_ENTITY,
    DOMAIN,
)


@pytest.mark.asyncio
async def test_runtime_recursive_configuration_is_rejected(hass) -> None:
    """Stored recursive configurations cannot bypass config-flow validation."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_UNDERLYING_TTS_ENTITY: "tts.other_adaptive_tts",
            CONF_QUIET_MODE: False,
            CONF_QUIET_START: "23:00:00",
            CONF_QUIET_END: "07:00:00",
            CONF_QUIET_OPTION: "voice",
            CONF_QUIET_VALUE: "",
        },
    )
    with (
        patch("custom_components.adaptive_tts.is_adaptive_entity", return_value=True),
        pytest.raises(ConfigEntryError, match="cannot wrap"),
    ):
        await async_setup_entry(hass, entry)
