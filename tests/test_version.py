"""Packaging/version consistency tests."""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.adaptive_tts.const import VERSION


def test_manifest_version_matches_runtime_version() -> None:
    """The HACS manifest and runtime version must be released together."""
    manifest_path = (
        Path(__file__).parents[1]
        / "custom_components"
        / "adaptive_tts"
        / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["version"] == VERSION
