"""The setup demo rewrites workspace/index.html on every run, so it must not be a tracked file."""
import contextlib
import io
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


class CommitTrailers(unittest.TestCase):
    """No AI co-author trailers. The commit-msg hook (sh) and scripts/check_commit_trailers.py (CI) read one
    pattern file, so both are tested against the same messages."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("check_commit_trailers", ROOT / "scripts" / "check_commit_trailers.py")
        cls.script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.script)

    def hook_rejects(self, message):
        import shutil
        import tempfile
        sh = shutil.which("sh")
        if not sh:
            self.skipTest("no sh on PATH")
        with tempfile.TemporaryDirectory() as d:
            msg = Path(d, "COMMIT_EDITMSG")
            msg.write_text(message, encoding="utf-8")
            r = subprocess.run([sh, str(ROOT / ".githooks" / "commit-msg"), str(msg)], capture_output=True, text=True)
        return r.returncode != 0

    def check(self, message, bad):
        with self.subTest(message=message, side="script"):
            self.assertEqual(bool(self.script.bad_lines(message)), bad)
        with self.subTest(message=message, side="hook"):
            self.assertEqual(self.hook_rejects(message), bad)

    def test_ai_co_author_trailers_fail(self):
        for name in ("Claude <noreply@anthropic.com>", "Claude Sonnet 5.5 <noreply@anthropic.com>",
                     "GitHub Copilot <copilot@github.com>", "ChatGPT <x@openai.com>", "Gemini <g@example.com>",
                     "Cursor Agent <c@example.com>", "aider (gpt-5) <a@example.com>", "Codex <c@example.com>"):
            self.check("feat: x\n\nCo-Authored-By: " + name + "\n", True)
        self.check("feat: x\n\nco-authored-by: CLAUDE <a@b.c>\n", True)  # any case

    def test_a_human_co_author_passes(self):
        self.check("feat: x\n\nCo-Authored-By: Pat Lee <pat@example.com>\n", False)

    def test_a_commented_out_trailer_passes(self):
        self.check("feat: x\n\n# Co-Authored-By: Claude <noreply@anthropic.com>\n", False)

    def test_generated_with_an_ai_tool_fails(self):
        self.check("feat: x\n\nGenerated with Claude Code\n", True)
        self.check("feat: x\n\nGenerated with [Claude Code](https://claude.com/claude-code)\n", True)
        self.check("feat: x\n\nGenerated with the project script\n", False)

    def test_the_pattern_list_is_not_empty(self):
        names = self.script.vendor_patterns()
        for want in ("claude", "anthropic", "copilot", "openai", "gpt", "gemini", "cursor", "aider", "codex"):
            self.assertIn(want, names)

    def test_a_clean_range_passes_and_a_bad_commit_in_a_range_is_named(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            def run(*a):
                return subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@example.com", *a],
                                      capture_output=True, text=True)
            run("init", "-q")
            run("commit", "-q", "--allow-empty", "-m", "base")
            run("commit", "-q", "--allow-empty", "-m", "ok", "-m", "Co-Authored-By: Pat Lee <p@example.com>")
            run("commit", "-q", "--allow-empty", "-m", "bad", "-m", "Co-Authored-By: Claude <noreply@anthropic.com>")
            repo = Path(d)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                clean = self.script.main(["HEAD~2..HEAD~1"], repo=repo)
                dirty = self.script.main(["HEAD~2..HEAD"], repo=repo)
        self.assertEqual(clean, 0)
        self.assertEqual(dirty, 1)
        self.assertIn("'bad'", out.getvalue())
        self.assertNotIn("'ok'", out.getvalue())


if __name__ == "__main__":
    unittest.main()


