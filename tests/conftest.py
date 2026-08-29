"""Pytest configuration for Adaptive TTS."""

import sys

import pytest
import pytest_socket

pytest_plugins = "pytest_homeassistant_custom_component"

if sys.platform == "win32":
    # The HA test plugin allows AF_UNIX for asyncio, but Windows implements the
    # event loop's socket pair with AF_INET. Keep local Windows verification
    # usable; the supported Linux CI path retains the plugin's socket blocking.
    pytest_socket.disable_socket = lambda *args, **kwargs: None
    pytest_socket.enable_socket()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations in every test."""
