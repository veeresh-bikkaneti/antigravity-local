"""Tests for agl.app.checkpoint_offer: the yes-gated checkpoint file and pointer blocks, run only in temp folders."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agl.app import checkpoint_offer  # noqa: E402
from agl.core import checkpoint as ck  # noqa: E402
from agl.platform import agent_files  # noqa: E402

NOW = "2026-11-27T10:00:00+00:00"
USER_LINES = "# My rules\n\nAlways write tests first.\n"


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

    def _offer(self, answers):
        checkpoint_offer.offer(
            str(self.ws),
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


if __name__ == "__main__":
    unittest.main()
