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


class GeneratedTooling(unittest.TestCase):
    """Files that ruflo and the session hooks generate must stay out of git; tracked tooling must not."""

    def test_generated_paths_are_ignored(self):
        for path in (".claude-flow/data/x", ".claude-flow/config.json", ".swarm/memory.db", ".mcp.json",
                     ".claude/settings.json", ".claude/helpers/hook-handler.cjs", "CLAUDE.md",
                     ".ai-context/SESSION_STATE.md", ".agents/skills/ruflo/SKILL.md"):
            self.assertEqual(git("check-ignore", path).returncode, 0, path)

    def test_tracked_tooling_is_not_ignored(self):
        for path in (".agents/skills/archify/package.json", ".agents/rules/graphify.md", ".github/workflows/docker.yml",
                     "AGENTS.md", "scripts/check_docs.py"):
            self.assertEqual(git("check-ignore", path).returncode, 1, path)


if __name__ == "__main__":
    unittest.main()


class CiRunsEveryTest(unittest.TestCase):
    """CI lists test modules by hand. A new tests/test_*.py that is not listed never runs there (PR 26's
    test_run and test_model_wizard were missed this way, and so were four older files)."""

    def test_every_test_module_is_in_the_ci_unittest_command(self):
        import re
        workflow = (ROOT / ".github" / "workflows" / "docker.yml").read_text(encoding="utf-8")
        listed = set()
        for line in workflow.splitlines():
            if "python -m unittest" in line:
                listed |= set(re.findall(r"\btests\.(test_\w+)", line))
        on_disk = {p.stem for p in (ROOT / "tests").glob("test_*.py")}
        missing = sorted(on_disk - listed)
        self.assertEqual(missing, [], "add these to the `python -m unittest` line in "
                         ".github/workflows/docker.yml: " + ", ".join("tests." + m for m in missing))
