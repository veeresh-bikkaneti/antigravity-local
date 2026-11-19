"""Characterization tests: today's text, frozen.

These are the refactor safety net: a failure means user-visible text changed, which is a behavior
change, not a refactor. Expected text lives in tests/golden/ (rendered menu text from
model_wizard.render(model_wizard.build_menu(...)) and `python run.py --help`, captured 2026-11-19
at c90a615).
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import model_wizard  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = Path(__file__).resolve().parent / "golden"


def expected(name):
    return (GOLDEN / name).read_text(encoding="utf-8").replace("\r\n", "\n")


class WizardMenuGolden(unittest.TestCase):
    def _render(self, vram_gb, ram_gb):
        lines = model_wizard.render(model_wizard.build_menu([], vram_gb, ram_gb), None)
        return "\n".join(lines) + "\n"

    def test_menu_16gb_vram_128gb_ram(self):
        self.assertEqual(self._render(16.0, 128.0), expected("menu_16gb_128gb.txt"))

    def test_menu_0gb_vram_8gb_ram(self):
        self.assertEqual(self._render(0.0, 8.0), expected("menu_0gb_8gb.txt"))


class RunHelpGolden(unittest.TestCase):
    def test_run_help(self):
        env = dict(os.environ, COLUMNS="80", PYTHONUTF8="1")
        proc = subprocess.run([sys.executable, "run.py", "--help"], cwd=str(ROOT),
                              capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.replace("\r\n", "\n"), expected("run_help.txt"))


if __name__ == "__main__":
    unittest.main()
