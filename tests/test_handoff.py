"""handoff: Claude Code transcript to HANDOFF.md, and the opt-in hook installer. Offline, temp dirs only.

git is replaced by a fake runner, so these tests never look at the real repository.
"""
import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import handoff  # noqa: E402


def fake_git(args_out=None):
    def runner(cmd, **kw):
        text = {"status": " M a.py", "diff": " a.py | 2 +-", "rev-parse": ""}.get(cmd[1], "")
        code = 1 if cmd[1] in ("rev-parse", "ls-files") else 0  # ls-files: not tracked
        return SimpleNamespace(stdout=text, returncode=code)
    return runner


def rec(kind, content, **extra):
    return {"type": kind, "message": {"role": kind, "content": content}, **extra}


def fixture():
    return [
        rec("user", "Add a --verbose flag to the CLI", cwd="/proj"),
        {"type": "future-record-type", "payload": {"x": 1}},                      # unknown: must be skipped
        rec("assistant", [{"type": "text", "text": "Sure, looking at cli.py."},
                          {"type": "tool_use", "name": "TodoWrite", "input": {"todos": [
                              {"content": "read cli.py", "status": "completed"},
                              {"content": "add flag", "status": "in_progress"},
                              {"content": "write tests", "status": "pending"}]}},
                          {"type": "tool_use", "name": "Edit", "input": {"file_path": "/proj/cli.py"}},
                          {"type": "tool_use", "name": "Write", "input": {"file_path": "/proj/new.py"}},
                          {"type": "tool_use", "name": "Bash", "input": {"command": "pytest -q"}}]),
        rec("user", [{"type": "tool_result", "tool_use_id": "t", "content": "ok"}]),   # not a user message
        rec("user", "<system-reminder>ignore me</system-reminder>"),
        rec("user", "also keep the old behaviour by default"),
        rec("assistant", [{"type": "text", "text": "Done with the flag. Tests next."}]),
    ]


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.home = self.root / "home"
        self.home.mkdir()

    def transcript(self, name="s1.jsonl", records=None, where=None):
        path = (where or self.root) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(r) for r in (records if records is not None else fixture())]
        lines.insert(1, "{ this line is not json")  # a broken line must not stop the read
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path


class Summary(Base):
    def test_the_fixture_gives_every_section_and_skips_what_it_does_not_know(self):
        info = handoff.summarize(handoff.read_records(self.transcript()))
        self.assertEqual(info["users"], ["Add a --verbose flag to the CLI", "also keep the old behaviour by default"])
        self.assertEqual([t["content"] for t in info["todos"]], ["read cli.py", "add flag", "write tests"])
        self.assertEqual(info["files"], ["/proj/cli.py", "/proj/new.py"])
        self.assertEqual(info["commands"], ["pytest -q"])
        self.assertEqual(info["last_text"], "Done with the flag. Tests next.")

    def test_only_the_last_ten_commands_are_kept(self):
        recs = [rec("assistant", [{"type": "tool_use", "name": "Bash", "input": {"command": f"echo {i}"}}])
                for i in range(15)]
        self.assertEqual(handoff.summarize(recs)["commands"], [f"echo {i}" for i in range(5, 15)])

    def test_records_in_a_shape_we_have_never_seen_do_not_crash(self):
        weird = [{"type": "user", "message": None}, {"type": "assistant", "message": {"content": 5}},
                 {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": "x"}]}},
                 {"nothing": True}]
        info = handoff.summarize(weird)
        self.assertEqual(info["users"], [])
        self.assertEqual(info["commands"], [])


class Write(Base):
    def test_handoff_md_has_every_section_in_order(self):
        t = self.transcript()
        target = handoff.write_handoff(t, self.repo, git_run=fake_git())
        text = target.read_text(encoding="utf-8")
        self.assertEqual(target, self.repo / "HANDOFF.md")
        heads = [l for l in text.splitlines() if l.startswith("## ")]
        self.assertEqual(heads, ["## Original ask", "## Last 3 user messages", "## Last to-do list",
                                 "## Files edited or created", "## Last 10 Bash commands",
                                 "## Last assistant message", "## git status --short", "## git diff --stat",
                                 "## Source"])
        for needle in ("Add a --verbose flag to the CLI", "- [x] read cli.py", "- [~] add flag", "- [ ] write tests",
                       "`/proj/cli.py`", "`pytest -q`", "Done with the flag", " M a.py", "a.py | 2 +-", str(t)):
            self.assertIn(needle, text)
        self.assertNotIn("ignore me", text)

    def test_git_being_absent_is_reported_not_fatal(self):
        def boom(*a, **k):
            raise FileNotFoundError("git")
        target = handoff.write_handoff(self.transcript(), self.repo, git_run=boom)
        self.assertIn("git unavailable", target.read_text(encoding="utf-8"))


class Finding(Base):
    def project(self, base, repo, name="s1.jsonl"):
        return base / "projects" / handoff.project_dir_name(repo) / name

    def test_project_folder_name_replaces_every_non_alphanumeric(self):
        self.assertEqual(handoff.project_dir_name("C:\\Users\\v\\my repo"), "C--Users-v-my-repo")
        self.assertEqual(handoff.project_dir_name("/home/v/a.b"), "-home-v-a-b")

    def test_latest_picks_the_newest_across_the_subscription_and_local_folders(self):
        old = self.transcript(where=(self.home / ".claude" / "projects" / handoff.project_dir_name(self.repo)))
        time.sleep(0.05)
        new = self.transcript("s2.jsonl", where=(self.home / ".claude-local" / "projects"
                                                 / handoff.project_dir_name(self.repo)))
        self.assertEqual(handoff.find_transcript("latest", self.repo, home=self.home, environ={}), new)
        self.assertEqual(handoff.find_transcript("s1", self.repo, home=self.home, environ={}), old)

    def test_falls_back_to_the_cwd_field_when_the_folder_name_differs(self):
        recs = fixture()
        recs[0]["cwd"] = str(self.repo)
        t = self.transcript(records=recs, where=self.home / ".claude" / "projects" / "some-other-name")
        self.assertEqual(handoff.find_transcript("latest", self.repo, home=self.home, environ={}), t)

    def test_another_projects_transcript_is_not_picked(self):
        recs = fixture()
        recs[0]["cwd"] = str(self.root / "elsewhere")
        self.transcript(records=recs, where=self.home / ".claude" / "projects" / "x")
        with self.assertRaises(handoff.HandoffError):
            handoff.find_transcript("latest", self.repo, home=self.home, environ={})

    def test_config_dir_variable_is_searched_first(self):
        cfg = self.root / "cfg"
        t = self.transcript(where=cfg / "projects" / handoff.project_dir_name(self.repo))
        self.assertEqual(handoff.find_transcript("latest", self.repo, home=self.home,
                                                 environ={"CLAUDE_CONFIG_DIR": str(cfg)}), t)


class Main(Base):
    def go(self, argv, stdin=None, **kw):
        lines = []
        code = handoff.main(argv, stdin=stdin, home=self.home, environ={}, cwd=self.repo, git_run=fake_git(),
                            out=lines.append, **kw)
        return code, "\n".join(lines)

    def test_transcript_flag_writes_handoff_at_the_repo_root(self):
        code, text = self.go(["--transcript", str(self.transcript())])
        self.assertEqual(code, 0)
        self.assertTrue((self.repo / "HANDOFF.md").is_file())
        self.assertIn("secrets from that transcript", text)

    def test_hook_stdin_transcript_path_is_honoured(self):
        t = self.transcript()
        stdin = io.StringIO(json.dumps({"transcript_path": str(t), "hook_event_name": "StopFailure"}))
        code, _ = self.go([], stdin=stdin)
        self.assertEqual(code, 0)
        self.assertIn("Add a --verbose flag", (self.repo / "HANDOFF.md").read_text(encoding="utf-8"))

    def test_missing_transcript_is_a_clear_error_and_writes_nothing(self):
        code, text = self.go(["--transcript", str(self.root / "gone.jsonl")])
        self.assertEqual(code, 1)
        self.assertIn("not found", text)
        self.assertFalse((self.repo / "HANDOFF.md").exists())

    def test_no_stdin_json_and_no_transcript_falls_back_to_the_newest_one(self):
        t = self.transcript(where=self.home / ".claude" / "projects" / handoff.project_dir_name(self.repo))
        code, text = self.go([], stdin=io.StringIO(""))
        self.assertEqual(code, 0)
        self.assertIn(str(t), text)


class Safety(Base):
    """The reviewer's three worries: secrets committed by accident, a user's own file overwritten."""

    def git(self, ignored, exclude=".git/info/exclude"):
        def runner(cmd, **kw):
            if cmd[1] == "check-ignore":
                return SimpleNamespace(stdout="", returncode=0 if ignored else 1)
            if cmd[1] == "rev-parse" and "--git-path" in cmd:
                return SimpleNamespace(stdout=exclude + "\n", returncode=0)
            return SimpleNamespace(stdout="", returncode=1)
        return runner

    def test_a_project_that_does_not_ignore_it_gets_a_local_exclude_entry_once(self):
        lines = []
        for _ in range(2):
            handoff.ensure_ignored(self.repo, git_run=self.git(False), out=lines.append)
        text = (self.repo / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        self.assertEqual(text.splitlines().count("/HANDOFF.md*"), 1)
        self.assertIn("never committed", lines[0])

    def test_existing_exclude_content_is_kept(self):
        ex = self.repo / ".git" / "info" / "exclude"
        ex.parent.mkdir(parents=True)
        ex.write_text("*.log", encoding="utf-8")
        handoff.ensure_ignored(self.repo, git_run=self.git(False), out=lambda *_: None)
        self.assertEqual(ex.read_text(encoding="utf-8").splitlines(), ["*.log", "/HANDOFF.md*"])

    def test_an_already_ignored_file_changes_nothing(self):
        handoff.ensure_ignored(self.repo, git_run=self.git(True), out=lambda *_: None)
        self.assertFalse((self.repo / ".git").exists())

    def test_when_git_cannot_help_it_warns_instead_of_claiming_it_is_ignored(self):
        lines = []

        def boom(*a, **k):
            raise FileNotFoundError("git")
        self.assertIsNone(handoff.ensure_ignored(self.repo, git_run=boom, out=lines.append))
        self.assertIn("WARNING", lines[0])
        self.assertNotIn("is gitignored", "\n".join(lines))

    def test_main_makes_it_ignored_and_does_not_lie_about_it(self):
        lines = []
        code = handoff.main(["--transcript", str(self.transcript())], cwd=self.repo, git_run=self.git(False),
                            out=lines.append)
        self.assertEqual(code, 0)
        self.assertIn("/HANDOFF.md*", (self.repo / ".git" / "info" / "exclude").read_text(encoding="utf-8"))

    def test_a_handoff_we_did_not_write_is_backed_up_not_overwritten(self):
        mine = self.repo / "HANDOFF.md"
        mine.write_text("my own notes\n", encoding="utf-8")
        lines = []
        handoff.write_handoff(self.transcript(), self.repo, git_run=fake_git(), out=lines.append)
        backup = Path(str(mine) + handoff.BACKUP_SUFFIX)
        self.assertEqual(backup.read_text(encoding="utf-8"), "my own notes\n")
        self.assertIn(handoff.MARKER, mine.read_text(encoding="utf-8"))
        self.assertIn("saved to", lines[0])

    def test_our_own_file_is_rewritten_without_a_backup(self):
        handoff.write_handoff(self.transcript(), self.repo, git_run=fake_git(), out=lambda *_: None)
        handoff.write_handoff(self.transcript(), self.repo, git_run=fake_git(), out=lambda *_: None)
        self.assertFalse(Path(str(self.repo / "HANDOFF.md") + handoff.BACKUP_SUFFIX).exists())

    def test_a_second_foreign_file_never_destroys_the_first_backup(self):
        mine = self.repo / "HANDOFF.md"
        for text in ("first\n", "second\n"):
            mine.write_text(text, encoding="utf-8")
            handoff.write_handoff(self.transcript(), self.repo, git_run=fake_git(), out=lambda *_: None)
        first = Path(str(mine) + handoff.BACKUP_SUFFIX)
        self.assertEqual(first.read_text(encoding="utf-8"), "first\n")
        self.assertEqual(Path(str(first) + ".2").read_text(encoding="utf-8"), "second\n")


@unittest.skipUnless(shutil.which("git"), "needs git")
class TrackedHandoff(Base):
    """A real temp repo, a real git: the check is `git ls-files --error-unmatch`, so test the real thing."""

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True, text=True)

    def setUp(self):
        super().setUp()
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.invalid")
        self.git("config", "user.name", "t")

    def test_a_project_that_tracks_handoff_md_is_refused_and_nothing_is_written(self):
        tracked = self.repo / "HANDOFF.md"
        tracked.write_text("committed notes\n", encoding="utf-8")
        self.git("add", "HANDOFF.md")
        self.git("commit", "-q", "-m", "track it")
        lines = []
        code = handoff.main(["--transcript", str(self.transcript())], cwd=self.repo, out=lines.append)
        text = "\n".join(lines)
        self.assertEqual(code, 1)
        self.assertIn("already tracks HANDOFF.md", text)
        self.assertIn("would be committed", text)
        self.assertEqual(tracked.read_text(encoding="utf-8"), "committed notes\n")       # untouched
        self.assertFalse(Path(str(tracked) + handoff.BACKUP_SUFFIX).exists())           # not even a backup
        self.assertNotIn("Wrote", text)

    def test_a_merely_staged_file_counts_as_tracked(self):
        (self.repo / "HANDOFF.md").write_text("x\n", encoding="utf-8")
        self.git("add", "HANDOFF.md")
        self.assertTrue(handoff.is_tracked(self.repo))

    def test_an_untracked_file_and_a_missing_file_are_not_tracked_and_the_write_goes_ahead(self):
        self.assertFalse(handoff.is_tracked(self.repo))
        (self.repo / "HANDOFF.md").write_text("mine\n", encoding="utf-8")                # exists, never added
        self.assertFalse(handoff.is_tracked(self.repo))
        lines = []
        code = handoff.main(["--transcript", str(self.transcript())], cwd=self.repo, out=lines.append)
        self.assertEqual(code, 0, "\n".join(lines))
        self.assertIn(handoff.MARKER, (self.repo / "HANDOFF.md").read_text(encoding="utf-8"))

    def test_the_hook_path_is_refused_too(self):
        (self.repo / "HANDOFF.md").write_text("x\n", encoding="utf-8")
        self.git("add", "HANDOFF.md")
        stdin = io.StringIO(json.dumps({"transcript_path": str(self.transcript())}))
        code = handoff.main([], stdin=stdin, cwd=self.repo, out=lambda *_: None)
        self.assertEqual(code, 1)
        self.assertEqual((self.repo / "HANDOFF.md").read_text(encoding="utf-8"), "x\n")


class Hardening(Base):
    """The four low-severity review items."""

    def test_blocks_with_non_string_text_or_names_do_not_crash_and_good_records_still_count(self):
        recs = [rec("user", [{"type": "text", "text": 5}, {"type": "text", "text": {"a": 1}}]),
                rec("user", "the real ask"),
                rec("assistant", [{"type": "text", "text": ["not", "a", "string"]},
                                  {"type": "tool_use", "name": ["Bash"], "input": {"command": "x"}},
                                  {"type": "tool_use", "name": 7, "input": {"file_path": "/p"}},
                                  {"type": "tool_use", "name": "Bash", "input": {"command": "echo ok"}},
                                  {"type": "text", "text": "fine"}])]
        info = handoff.summarize(recs)
        self.assertEqual(info["users"], ["the real ask"])
        self.assertEqual(info["commands"], ["echo ok"])
        self.assertEqual(info["files"], [])
        self.assertEqual(info["last_text"], "fine")

    def test_a_stdin_pipe_that_never_closes_does_not_hang_us(self):
        release = threading.Event()
        self.addCleanup(release.set)

        class Stuck:
            def isatty(self):
                return False

            def read(self, n=-1):
                release.wait(30)
                return ""
        start = time.monotonic()
        self.assertEqual(handoff.read_hook_stdin(Stuck(), wait=0.2), {})
        self.assertLess(time.monotonic() - start, 5)

    def test_main_with_a_stuck_stdin_falls_back_to_the_newest_transcript(self):
        release = threading.Event()
        self.addCleanup(release.set)
        t = self.transcript(where=self.home / ".claude" / "projects" / handoff.project_dir_name(self.repo))

        class Stuck:
            def isatty(self):
                return False

            def read(self, n=-1):
                release.wait(30)
                return ""
        lines = []
        with mock.patch.object(handoff, "STDIN_WAIT", 0.2):
            code = handoff.main([], stdin=Stuck(), home=self.home, environ={}, cwd=self.repo,
                                git_run=fake_git(), out=lines.append)
        self.assertEqual(code, 0)
        self.assertIn(str(t), "\n".join(lines))

    def test_a_normal_hook_payload_still_reads(self):
        self.assertEqual(handoff.read_hook_stdin(io.StringIO('{"transcript_path": "x"}')), {"transcript_path": "x"})
        self.assertEqual(handoff.read_hook_stdin(io.StringIO("not json")), {})

    def test_hooks_that_are_already_there_are_recognised_whatever_the_indentation(self):
        path = self.repo / ".claude" / "settings.local.json"
        handoff.install_hook(self.repo, input_fn=lambda _="": "y", out=lambda *_: None)
        path.write_text(json.dumps(json.loads(path.read_text(encoding="utf-8")), indent=4), encoding="utf-8")
        before = path.read_bytes()

        def never(_=""):
            raise AssertionError("must not ask: nothing to change")
        lines = []
        self.assertFalse(handoff.install_hook(self.repo, input_fn=never, out=lines.append))
        self.assertIn("already in", "\n".join(lines))
        self.assertEqual(path.read_bytes(), before)


class InstallHook(Base):
    def settings(self):
        return self.repo / ".claude" / "settings.local.json"

    def install(self, answer):
        lines = []
        changed = handoff.install_hook(self.repo, input_fn=lambda _="": answer, out=lines.append)
        return changed, "\n".join(lines)

    def test_no_or_empty_answer_writes_nothing_but_shows_the_diff(self):
        for answer in ("n", ""):
            with self.subTest(answer=answer):
                changed, text = self.install(answer)
                self.assertFalse(changed)
                self.assertFalse(self.settings().exists())
                self.assertIn("StopFailure", text)

    def test_yes_merges_keeps_other_keys_and_backs_up_once(self):
        self.settings().parent.mkdir(parents=True)
        original = {"permissions": {"allow": ["Bash(ls)"]},
                    "hooks": {"PreCompact": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}
        self.settings().write_text(json.dumps(original), encoding="utf-8")
        self.assertTrue(self.install("y")[0])
        data = json.loads(self.settings().read_text(encoding="utf-8"))
        self.assertEqual(data["permissions"], original["permissions"])
        pre = data["hooks"]["PreCompact"]
        self.assertEqual(pre[0], original["hooks"]["PreCompact"][0])                  # theirs untouched
        self.assertIn("handoff", pre[1]["hooks"][0]["command"])
        stop, = data["hooks"]["StopFailure"]
        self.assertEqual(stop["matcher"], "rate_limit")
        self.assertIn("handoff", stop["hooks"][0]["command"])
        backup = Path(str(self.settings()) + handoff.BACKUP_SUFFIX)
        self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), original)
        # running again changes nothing and does not touch the backup
        self.assertFalse(self.install("y")[0])
        self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), original)

    def test_a_fresh_project_gets_the_file_and_user_settings_are_never_touched(self):
        user = self.home / ".claude" / "settings.json"
        user.parent.mkdir(parents=True)
        user.write_text("{}", encoding="utf-8")
        stamp = user.stat().st_mtime_ns
        self.assertTrue(self.install("y")[0])
        self.assertTrue(self.settings().is_file())
        self.assertEqual(user.stat().st_mtime_ns, stamp)

    def test_broken_json_is_refused_and_left_alone(self):
        self.settings().parent.mkdir(parents=True)
        self.settings().write_text("{ nope", encoding="utf-8")
        with self.assertRaises(handoff.HandoffError):
            self.install("y")
        self.assertEqual(self.settings().read_text(encoding="utf-8"), "{ nope")

    def test_main_routes_install_hook(self):
        lines = []
        code = handoff.main(["--install-hook"], input_fn=lambda _="": "n", cwd=self.repo, git_run=fake_git(),
                            out=lines.append)
        self.assertEqual(code, 0)
        self.assertFalse(self.settings().exists())


if __name__ == "__main__":
    unittest.main()
