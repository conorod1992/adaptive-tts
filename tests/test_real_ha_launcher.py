"""Exercise launcher import ordering in fresh interpreters without HA plugins."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parents[1] / "scripts/run_real_ha_tests.py"


class RealHALauncherTests(unittest.TestCase):
    """Model stable and upcoming dependency layouts at the bootstrap boundary."""

    def run_launcher(self, *, stable=False, missing_helper=False):
        """Run the actual entry point with import-sensitive dependency doubles."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ha = root / "homeassistant"
            logger = ha / "components/logger"
            logger.mkdir(parents=True)
            (ha / "__init__.py").write_text(
                "import sys, types\n"
                "sys.modules['httpx'] = types.ModuleType('httpx')\n"
                "sys.modules['httpx'].ha_initialized = True\n"
            )
            (ha / "components/__init__.py").write_text("")
            (logger / "__init__.py").write_text(
                "def _clear_logger_overwrites(): return 'stable'\n" if stable else ""
            )
            (logger / "helpers.py").write_text(
                "raise AssertionError('stable must not import relocated helper')\n"
                if stable
                else (
                    "" if missing_helper else "def _clear_logger_overwrites(): pass\n"
                )
            )
            (root / "pytest.py").write_text(
                "import httpx\n"
                "assert httpx.ha_initialized\n"
                "from homeassistant.components.logger import _clear_logger_overwrites\n"
                + (
                    "assert _clear_logger_overwrites() == 'stable'\n"
                    if stable
                    else (
                        "from homeassistant.components.logger.helpers import "
                        "_clear_logger_overwrites as relocated\n"
                        "assert _clear_logger_overwrites is relocated\n"
                    )
                )
                + "def main(args):\n"
                "    assert args == ['tests_real_ha', '-x']\n"
                "    return 7\n"
            )
            # Use runpy with an explicit path so site-installed HA/pytest and
            # the parent test process cannot mask an import-order regression.
            return subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    "import sys, runpy; "
                    f"sys.path.insert(0, {str(root)!r}); "
                    f"sys.argv = [{str(LAUNCHER)!r}, 'tests_real_ha', '-x']; "
                    f"runpy.run_path({str(LAUNCHER)!r}, run_name='__main__')",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )

    def test_stable_preserves_existing_helper(self):
        """Stable must retain its helper and avoid importing the new module."""
        result = self.run_launcher(stable=True)
        self.assertEqual(result.returncode, 7, result.stderr)

    def test_upcoming_aliases_helper_before_pytest_import(self):
        """Both HA initialization and the alias must precede pytest loading."""
        result = self.run_launcher()
        self.assertEqual(result.returncode, 7, result.stderr)

    def test_missing_helper_is_not_silenced(self):
        """An unexpected HA layout must still fail visibly."""
        result = self.run_launcher(missing_helper=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("ImportError", result.stderr)
        self.assertIn("_clear_logger_overwrites", result.stderr)
