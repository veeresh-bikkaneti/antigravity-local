"""Tests for agl.app.checkpoint_offer: the yes-gated checkpoint file and pointer blocks, run only in temp folders."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agl.app import checkpoint_offer  # noqa: E402
from agl.core import checkpoint as ck  # noqa: E402
from agl.core.agent_config import AgentSetupError  # noqa: E402
from agl.platform import agent_files  # noqa: E402

NOW = "2026-11-27T10:00:00+00:00"
OLD = "2026-11-26T10:00:00+00:00"
USER_LINES = "# My rules\n\nAlways write tests first.\n"
RULES_FILE = str(Path(".continue", "rules", "agl-checkpoint.md"))


class _RecordingFiles:
    """agent_files, plus a record of whether a backup already existed when each file was written."""

    def __init__(self):
        self.seen = []

    def __getattr__(self, name):
        return getattr(agent_files, name)

    def write_text_atomic(self, path, text):
        folder = path.parent
        backed = folder.is_dir() and any(".bak-antigravity-local" in p.name for p in folder.iterdir())
        self.seen.append((path.name, backed))
        agent_files.write_text_atomic(path, text)


class CheckpointOfferTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ws = Path(self._tmp.name)
        self.lines = []
        self.prompts = []
        self.files = _RecordingFiles()
        self.tracked = False

    def _input(self, answers):
        pending = list(answers)

        def fake(prompt):
            self.prompts.append(prompt)
            if not pending:
                raise EOFError
            return pending.pop(0)

        return fake

    def _offer(self, answers, app="pi"):
        checkpoint_offer.offer(
            str(self.ws),
            app=app,
            files=self.files,
            is_tracked=lambda ws, rel: self.tracked,
            input_fn=self._input(answers),
            out=self.lines.append,
            now=NOW,
        )

    def _snapshot(self):
        return {p.relative_to(self.ws): p.read_bytes() for p in self.ws.rglob("*") if p.is_file()}

    def test_no_answer_writes_nothing(self):
        (self.ws / "AGENTS.md").write_text(USER_LINES, encoding="utf-8")
        before = self._snapshot()
        self._offer(["n"])
        self.assertEqual(len(self.prompts), 1)
        self.assertEqual(self._snapshot(), before)
        self.assertTrue(any(line.startswith("       Not changed.") for line in self.lines))

    def test_end_of_input_writes_nothing(self):
        before = self._snapshot()
        self._offer([])
        self.assertEqual(len(self.prompts), 1)
        self.assertEqual(self._snapshot(), before)
        self.assertFalse((self.ws / ".agl").exists())
        self.assertFalse((self.ws / "AGENTS.md").exists())

    def test_second_yes_changes_zero_bytes(self):
        (self.ws / "CLAUDE.md").write_text(USER_LINES, encoding="utf-8")
        self._offer(["y"])
        first = self._snapshot()
        self.prompts.clear()
        self._offer(["y"])
        self.assertEqual(self._snapshot(), first)
        self.assertEqual(self.prompts, [])
        self.assertTrue(any("already in place" in line for line in self.lines))

    def test_user_lines_survive_and_backup_exists_before_first_write(self):
        (self.ws / "AGENTS.md").write_text(USER_LINES, encoding="utf-8")
        self._offer(["y"])
        text = (self.ws / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith(USER_LINES))
        self.assertIn(ck.POINTER, text)
        backups = [p for p in self.ws.iterdir() if ".bak-antigravity-local" in p.name]
        self.assertTrue(any(p.read_text(encoding="utf-8") == USER_LINES for p in backups))
        self.assertTrue(dict(self.files.seen)["AGENTS.md"])

    def test_tracked_checkpoint_is_refused_and_nothing_is_written(self):
        self.tracked = True
        before = self._snapshot()
        self._offer(["y"])
        self.assertEqual(self.prompts, [])
        self.assertEqual(self._snapshot(), before)
        self.assertTrue(any("already tracked by git" in line for line in self.lines))

    def test_gitignore_gets_agl_only_on_yes(self):
        (self.ws / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        self._offer(["n"])
        self.assertEqual((self.ws / ".gitignore").read_text(encoding="utf-8"), "node_modules/\n")
        self._offer(["y"])
        self.assertEqual((self.ws / ".gitignore").read_text(encoding="utf-8"), "node_modules/\n.agl/\n")

    def test_broken_pointer_block_stops_before_any_write(self):
        (self.ws / "AGENTS.md").write_text(ck.BEGIN + "\nhalf a block\n", encoding="utf-8")
        before = self._snapshot()
        self._offer(["y"])
        self.assertEqual(self.prompts, [])
        self.assertEqual(self._snapshot(), before)

    def test_claude_gets_claude_md_created_and_agents_md_is_not_made(self):
        self._offer(["y"], app="claude")
        self.assertIn(ck.POINTER, (self.ws / "CLAUDE.md").read_text(encoding="utf-8"))
        self.assertFalse((self.ws / "AGENTS.md").exists())

    def test_pi_does_not_edit_an_existing_claude_md(self):
        (self.ws / "CLAUDE.md").write_text(USER_LINES, encoding="utf-8")
        self._offer(["y"], app="pi")
        self.assertEqual((self.ws / "CLAUDE.md").read_text(encoding="utf-8"), USER_LINES)
        self.assertIn(ck.POINTER, (self.ws / "AGENTS.md").read_text(encoding="utf-8"))

    def test_every_file_that_will_be_written_is_shown_before_the_yes(self):
        (self.ws / ".continue" / "rules").mkdir(parents=True)
        self._offer(["n"])
        self.assertTrue(any(RULES_FILE in line and "missing, will be created" in line for line in self.lines))
        self.assertFalse((self.ws / ".continue" / "rules" / "agl-checkpoint.md").exists())

    def test_oversize_checkpoint_is_backed_up_and_unknown_lines_survive(self):
        steps = [f"Step {i} " + "x" * 200 for i in range(500)]
        original = ck.render({"Plan": ["Ship C3."], "Done": steps, "Next": ["Write the tests."]}, OLD)
        original = original.replace("## Notes", "## Scratch\n\n- my own list\n\nFree line that stays.\n\n## Notes")
        (self.ws / ".agl").mkdir()
        (self.ws / ".agl" / "checkpoint.md").write_text(original, encoding="utf-8")
        self._offer(["y"])
        new = (self.ws / ".agl" / "checkpoint.md").read_text(encoding="utf-8")
        backups = [p for p in (self.ws / ".agl").iterdir() if ".bak-antigravity-local" in p.name]
        self.assertTrue(any(p.read_text(encoding="utf-8") == original for p in backups))
        self.assertIn("## Scratch\n\n- my own list\n\nFree line that stays.", new)
        self.assertIn("- Write the tests.", new)
        self.assertIn(f"updated: {NOW}", new)
        self.assertLessEqual(ck.tokens(new), ck.CAP_TOKENS)

    def test_markerless_checkpoint_keeps_every_line_and_gets_a_backup(self):
        original = "# My checkpoint\n\n## Done\n\n- [x] Wrote the parser.\n\nFree line that stays.\n"
        (self.ws / ".agl").mkdir()
        (self.ws / ".agl" / "checkpoint.md").write_text(original, encoding="utf-8")
        self._offer(["y"])
        new = (self.ws / ".agl" / "checkpoint.md").read_text(encoding="utf-8")
        self.assertEqual(new, ck.MARKER + "\n" + original)
        backups = [p for p in (self.ws / ".agl").iterdir() if ".bak-antigravity-local" in p.name]
        self.assertTrue(any(p.read_text(encoding="utf-8") == original for p in backups))

    def test_preview_names_the_marker_change_when_pointers_are_current(self):
        (self.ws / "AGENTS.md").write_text(ck.POINTER + "\n", encoding="utf-8")
        (self.ws / ".agl").mkdir()
        (self.ws / ".agl" / "checkpoint.md").write_text(USER_LINES, encoding="utf-8")
        self._offer(["n"])
        self.assertTrue(any(line.startswith("       Change   : add the marker line") for line in self.lines))
        self.assertTrue(any(line.startswith("       Backup   : ") and ".bak-antigravity-local" in line
                            for line in self.lines))
        self.assertEqual((self.ws / ".agl" / "checkpoint.md").read_text(encoding="utf-8"), USER_LINES)

    def test_preview_names_the_trim_when_pointers_are_current(self):
        steps = [f"Step {i} " + "x" * 200 for i in range(500)]
        (self.ws / "AGENTS.md").write_text(ck.POINTER + "\n", encoding="utf-8")
        (self.ws / ".agl").mkdir()
        (self.ws / ".agl" / "checkpoint.md").write_text(ck.render({"Done": steps, "Next": ["Write the tests."]}, OLD),
                                                        encoding="utf-8")
        before = self._snapshot()
        self._offer(["n"])
        self.assertTrue(any("Change   : trim " in line and " old Done steps" in line for line in self.lines))
        self.assertEqual(self._snapshot(), before)

    def test_oversize_file_without_the_marker_is_fixed_in_one_run(self):
        steps = [f"Step {i} " + "x" * 200 for i in range(500)]
        original = ck.render({"Done": steps, "Next": ["Write the tests."]}, OLD).replace(ck.MARKER + "\n", "")
        (self.ws / ".agl").mkdir()
        path = self.ws / ".agl" / "checkpoint.md"
        path.write_text(original, encoding="utf-8")
        self._offer(["y"])
        text = path.read_text(encoding="utf-8")
        self.assertTrue(ck.is_ours(text))
        self.assertLessEqual(ck.tokens(text), ck.CAP_TOKENS)
        self.assertTrue(any("Change   : add the marker line; trim " in line for line in self.lines))
        self.assertFalse(any("every other line stays" in line for line in self.lines))
        backups = [p for p in path.parent.iterdir() if ".bak-antigravity-local" in p.name]
        self.assertTrue(any(p.read_text(encoding="utf-8") == original for p in backups))
        self.assertIn("Write the tests.", text)
        self.assertIn("Step 499 ", text)
        self.assertNotIn("Step 0 ", text)
        before = self._snapshot()
        self._offer(["y"])
        self.assertEqual(self._snapshot(), before)

    def test_preview_says_an_empty_checkpoint_gets_the_template(self):
        (self.ws / ".agl").mkdir()
        (self.ws / ".agl" / "checkpoint.md").write_text("  \n\n", encoding="utf-8")
        self._offer(["n"])
        self.assertIn("       Change   : the file is empty, so it gets the starter template.", self.lines)

    def test_oversize_plan_keeps_every_done_step_writes_nothing_and_says_so(self):
        original = ck.render({"Plan": ["x" * 8000], "Done": [f"Step {i}" for i in range(5)],
                              "Next": ["Write the tests."]}, OLD)
        (self.ws / ".agl").mkdir()
        (self.ws / ".agl" / "checkpoint.md").write_text(original, encoding="utf-8")
        before = self._snapshot()
        self._offer(["y"])
        self.assertEqual(self._snapshot(), before)
        self.assertEqual(self.prompts, [])
        self.assertTrue(any("over the size limit" in line and "was not rewritten" in line for line in self.lines))


class GitTracksTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ws = Path(self._tmp.name)

    def test_folder_outside_git_is_untracked(self):
        self.assertFalse(agent_files.git_tracks(self.ws, ".agl/checkpoint.md"))

    def test_real_repo_reports_tracked_and_untracked(self):
        subprocess.run(["git", "init", "-q"], cwd=str(self.ws), check=True, capture_output=True)
        (self.ws / ".agl").mkdir()
        (self.ws / ".agl" / "checkpoint.md").write_text("x", encoding="utf-8")
        self.assertFalse(agent_files.git_tracks(self.ws, ".agl/checkpoint.md"))
        subprocess.run(["git", "add", ".agl/checkpoint.md"], cwd=str(self.ws), check=True, capture_output=True)
        self.assertTrue(agent_files.git_tracks(self.ws, ".agl/checkpoint.md"))

    def test_git_error_inside_a_repo_refuses(self):
        (self.ws / ".git").mkdir()
        failed = subprocess.CompletedProcess(args=["git"], returncode=128)
        with mock.patch.object(agent_files.subprocess, "run", return_value=failed):
            with self.assertRaises(AgentSetupError) as ctx:
                agent_files.git_tracks(self.ws, ".agl/checkpoint.md")
        self.assertIn("git status", str(ctx.exception))

    def test_git_missing_inside_a_repo_refuses(self):
        (self.ws / ".git").mkdir()
        with mock.patch.object(agent_files.subprocess, "run", side_effect=OSError("git not found")):
            with self.assertRaises(AgentSetupError):
                agent_files.git_tracks(self.ws, ".agl/checkpoint.md")

    def test_unknown_tracking_refuses_and_writes_nothing(self):
        def unknown(ws, rel):
            raise AgentSetupError("Could not check whether git tracks .agl/checkpoint.md. Fix: make `git status` work.")

        lines = []
        checkpoint_offer.offer(str(self.ws), app="pi", files=_RecordingFiles(), is_tracked=unknown,
                               input_fn=lambda prompt: "y", out=lines.append, now=NOW)
        self.assertEqual(list(self.ws.iterdir()), [])
        self.assertTrue(any("Not changed" in line and "git status" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
