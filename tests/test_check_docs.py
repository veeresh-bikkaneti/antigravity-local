"""scripts/check_docs.py must catch a dead anchor, an em dash, and an emoji heading."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_docs.py"


def run(readme):
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "README.md").write_text(readme, encoding="utf-8")
        return subprocess.run([sys.executable, str(SCRIPT), "--root", d], capture_output=True, text=True)


class CheckDocs(unittest.TestCase):
    def test_clean_doc_passes(self):
        self.assertEqual(run("# Title\n\nSee [it](#title).\n").returncode, 0)

    def test_dead_anchor_fails(self):
        r = run("# Title\n\nSee [it](#nope).\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("dead anchor", r.stdout)

    def test_em_dash_fails(self):
        self.assertEqual(run("# Title\n\nOne — two.\n").returncode, 1)

    def test_emoji_heading_fails(self):
        self.assertEqual(run("# \U0001F680 Title\n").returncode, 1)


if __name__ == "__main__":
    unittest.main()
