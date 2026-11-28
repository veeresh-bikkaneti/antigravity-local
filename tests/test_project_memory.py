"""C5: memory rooted at the user's project, and HANDOFF.md built from .agl/checkpoint.md. Offline, temp dirs only."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import handoff  # noqa: E402
import memory  # noqa: E402
from agl.core import handoff as core_handoff  # noqa: E402


def fake_git(cmd, **kw):
    text = {"status": " M a.py", "diff": " a.py | 2 +-", "rev-parse": ""}.get(cmd[1], "")
    return SimpleNamespace(stdout=text, returncode=1 if cmd[1] in ("rev-parse", "ls-files") else 0)


class Temp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)


class RenderCheckpoint(unittest.TestCase):
    def test_copies_the_checkpoint_and_adds_git(self):
        text = core_handoff.render_checkpoint("## Next\n\n- [ ] step 3", "c.md", "/r",
                                              git_text=lambda args, r: "OUT " + args[0])
        self.assertIn(core_handoff.MARKER, text)
        self.assertIn("- [ ] step 3", text)
        self.assertIn("OUT status", text)
        self.assertIn("OUT diff", text)

    def test_empty_checkpoint_says_so(self):
        self.assertIn("(the checkpoint is empty)", core_handoff.render_checkpoint("  ", "c.md", "/r"))


class FromCheckpoint(Temp):
    def go(self):
        lines = []
        code = handoff.main(["--from-checkpoint"], cwd=self.repo, git_run=fake_git, out=lines.append)
        return code, "\n".join(lines)

    def test_writes_handoff_from_the_checkpoint(self):
        (self.repo / ".agl").mkdir()
        (self.repo / ".agl" / "checkpoint.md").write_text("## Next\n\n- [ ] step 3\n", encoding="utf-8")
        code, out = self.go()
        self.assertEqual(code, 0, out)
        written = (self.repo / "HANDOFF.md").read_text(encoding="utf-8")
        self.assertIn("- [ ] step 3", written)
        self.assertIn("from `.agl/checkpoint.md`", written)

    def test_no_checkpoint_is_an_error_and_writes_nothing(self):
        code, out = self.go()
        self.assertEqual(code, 1)
        self.assertIn("No checkpoint", out)
        self.assertFalse((self.repo / "HANDOFF.md").exists())


class ProjectRoot(Temp):
    def setUp(self):
        super().setUp()
        saved = {k: getattr(memory, k) for k in ("PROJECT_ROOT", "DB_DIR", "DB_PATH", "WIKI_DIR")}
        self.addCleanup(lambda: [setattr(memory, k, v) for k, v in saved.items()])

    def test_use_project_moves_the_index_into_the_project(self):
        memory.use_project(self.repo)
        self.assertEqual(memory.DB_PATH, self.repo / ".agl" / "memory" / "index.sqlite")
        self.assertEqual((self.repo / ".agl" / "memory" / ".gitignore").read_text(encoding="utf-8"), "*\n")

    def test_project_targets_are_the_project_files_only(self):
        (self.repo / ".agl").mkdir()
        (self.repo / ".agl" / "checkpoint.md").write_text("x", encoding="utf-8")
        (self.repo / "README.md").write_text("x", encoding="utf-8")
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "guide.md").write_text("x", encoding="utf-8")
        memory.use_project(self.repo)
        got = memory.MemoryIndexer(None, None).collect_target_files()
        self.assertEqual({(p.relative_to(self.repo).as_posix(), c) for p, c in got},
                         {(".agl/checkpoint.md", "context"), ("README.md", "root_doc"), ("docs/guide.md", "doc")})

    def test_a_link_that_leaves_the_project_is_not_indexed(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        (Path(outside.name) / "secret.md").write_text("x", encoding="utf-8")
        self._link(outside.name, self.repo / "docs")
        memory.use_project(self.repo)
        self.assertEqual(memory.MemoryIndexer(None, None).collect_target_files(), [])

    def _link(self, target, link):
        if sys.platform == "win32":  # a junction needs no admin rights, a symlink does
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
        else:
            link.symlink_to(target, target_is_directory=True)

    def test_an_agl_folder_that_links_outside_stops(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        self._link(outside.name, self.repo / ".agl")
        with self.assertRaises(SystemExit):
            memory.use_project(self.repo)
        self.assertEqual(list(Path(outside.name).iterdir()), [])

    def test_sync_runs_graphify_in_the_project(self):
        memory.use_project(self.repo)
        with mock.patch.object(memory, "_run_index", return_value={}), \
                mock.patch.object(memory, "memory_cli"), \
                mock.patch.object(memory.process, "run",
                                  return_value=SimpleNamespace(returncode=0, stdout="", stderr="")) as run:
            memory.cmd_sync(SimpleNamespace())
        self.assertEqual(run.call_args.kwargs["cwd"], self.repo)

    def test_a_missing_folder_stops(self):
        with self.assertRaises(SystemExit):
            memory.use_project(self.repo / "nope")

    def test_project_flag_is_parsed_before_the_command(self):
        with mock.patch.object(sys, "argv", ["memory.py", "--project", str(self.repo), "status"]), \
                mock.patch.object(memory, "cmd_status") as status:
            memory.main()
        self.assertEqual(memory.PROJECT_ROOT, self.repo)
        status.assert_called_once()


if __name__ == "__main__":
    unittest.main()
