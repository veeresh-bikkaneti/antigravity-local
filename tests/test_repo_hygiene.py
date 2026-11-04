"""The setup demo rewrites workspace/index.html on every run, so it must not be a tracked file."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)


class DemoArtifact(unittest.TestCase):
    def test_demo_output_is_not_tracked(self):
        self.assertEqual(git("ls-files", "workspace/index.html").stdout.strip(), "")

    def test_demo_output_is_ignored_but_gitkeep_is_not(self):
        self.assertEqual(git("check-ignore", "workspace/index.html").returncode, 0)
        self.assertEqual(git("check-ignore", "workspace/.gitkeep").returncode, 1)


if __name__ == "__main__":
    unittest.main()
