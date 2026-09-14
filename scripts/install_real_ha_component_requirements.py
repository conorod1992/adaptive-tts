"""Install exact runtime requirements for Adaptive TTS's HA dependencies.

The pytest Home Assistant package deliberately does not install every optional
integration requirement. Read the manifests from the installed Home Assistant
version so Real-HA CI uses the exact dependency versions that version declares.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import homeassistant

ROOT_DOMAINS = ("assist_pipeline", "frontend", "http", "panel_custom", "tts")


def _component_root() -> Path:
    return Path(homeassistant.__file__).resolve().parent / "components"


def _load_manifest(domain: str) -> dict:
    manifest_path = _component_root() / domain / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Home Assistant component manifest not found: {domain}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def collect_requirements() -> list[str]:
    """Collect requirements recursively from the installed HA manifests."""
    pending = list(ROOT_DOMAINS)
    seen: set[str] = set()
    requirements: set[str] = set()

    while pending:
        domain = pending.pop()
        if domain in seen:
            continue
        seen.add(domain)

        manifest = _load_manifest(domain)
        requirements.update(manifest.get("requirements", ()))
        pending.extend(manifest.get("dependencies", ()))
        pending.extend(manifest.get("after_dependencies", ()))

    return sorted(requirements)


def main() -> None:
    requirements = collect_requirements()
    if not requirements:
        print("No additional Home Assistant component requirements found.")
        return

    print("Installing Home Assistant component requirements:")
    for requirement in requirements:
        print(f"  {requirement}")

    subprocess.run(
        [sys.executable, "-m", "pip", "install", *requirements],
        check=True,
    )


if __name__ == "__main__":
    main()
