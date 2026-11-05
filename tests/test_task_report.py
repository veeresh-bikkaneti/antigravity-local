"""--task must report what the agent actually did, not just that it stopped."""
import asyncio
import contextlib
import io
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class Pure(unittest.TestCase):
    def test_snapshot_and_summarize_find_created_and_changed(self):
        import task_report
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.txt").write_text("one", encoding="utf-8")
            before = task_report.snapshot(d)
            (Path(d) / "a.txt").write_text("one and more", encoding="utf-8")
            (Path(d) / "b.txt").write_text("new", encoding="utf-8")
            created, changed = task_report.summarize(before, task_report.snapshot(d))
        self.assertEqual((created, changed), (["b.txt"], ["a.txt"]))

    def test_same_size_edit_is_changed_but_touch_only_is_not(self):
        import task_report
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "a.txt"
            f.write_text("aaaa", encoding="utf-8")
            snap = task_report.snapshot(d)
            f.write_text("bbbb", encoding="utf-8")
            self.assertEqual(task_report.summarize(snap, task_report.snapshot(d)), ([], ["a.txt"]))
            f.write_text("aaaa", encoding="utf-8")
            os.utime(f, (1, 1))
            self.assertEqual(task_report.summarize(snap, task_report.snapshot(d)), ([], []))

    def test_deleted_files_are_reported(self):
        import task_report
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "gone.txt").write_text("x", encoding="utf-8")
            (Path(d) / "keep.txt").write_text("y", encoding="utf-8")
            before = task_report.snapshot(d)
            (Path(d) / "gone.txt").unlink()
            after = task_report.snapshot(d)
        self.assertEqual(task_report.deleted(before, after), ["gone.txt"])
        text = "\n".join(task_report.render("ws", ["keep.txt"], [], [], ["gone.txt"]))
        self.assertIn("Deleted 1: gone.txt", text)
        self.assertNotIn("created or changed no files", text)

    def test_nothing_written_gives_a_warning_not_task_completed(self):
        import task_report
        text = "\n".join(task_report.render("ws", ["old.txt"], [], []))
        self.assertNotIn("Task completed", text)
        self.assertIn("created or changed no files", text)
        self.assertIn("run the same command again", text.lower())

    def test_files_written_says_task_completed_with_counts(self):
        import task_report
        text = "\n".join(task_report.render("ws", ["a.txt", "b.txt"], ["b.txt"], ["a.txt"]))
        self.assertIn("Task completed. Created 1, changed 1.", text)


def install_fake_sdk(writes_file):
    """A stand-in for google.antigravity so code_agent can be imported and run without the real SDK."""
    class FakeAgent:
        def __init__(self, config):
            self.workspace = config.workspaces[0]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def chat(self, prompt):
            if writes_file:
                Path(self.workspace, "hello.py").write_text("print('hi')\n", encoding="utf-8")

            async def gen():
                yield "ok"
            return gen()

    class Cfg:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    mods = {
        "google": types.ModuleType("google"),
        "google.antigravity": types.ModuleType("google.antigravity"),
        "google.antigravity.hooks": types.ModuleType("google.antigravity.hooks"),
        "google.antigravity.types": types.ModuleType("google.antigravity.types"),
    }
    mods["google.antigravity"].Agent = FakeAgent
    mods["google.antigravity"].LocalOpenAIAgentConfig = Cfg
    mods["google.antigravity.hooks"].policy = types.SimpleNamespace(allow_all=lambda: None)
    mods["google.antigravity.types"].CapabilitiesConfig = Cfg
    return mods


class OneShotWiring(unittest.TestCase):
    def run_task(self, writes_file):
        mods = install_fake_sdk(writes_file)
        saved = {k: sys.modules.get(k) for k in list(mods) + ["code_agent"]}
        sys.modules.update(mods)
        sys.modules.pop("code_agent", None)
        try:
            import code_agent
            with tempfile.TemporaryDirectory() as d:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    asyncio.run(code_agent.run_one_shot("http://x", "m", os.path.join(d, "ws"), "Create hello.py"))
                return buf.getvalue()
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def test_agent_that_writes_a_file_is_reported_as_completed(self):
        out = self.run_task(writes_file=True)
        self.assertIn("Task completed. Created 1, changed 0.", out)
        self.assertIn("hello.py", out)

    def test_agent_that_writes_nothing_is_not_reported_as_completed(self):
        out = self.run_task(writes_file=False)
        self.assertNotIn("Task completed", out)
        self.assertIn("created or changed no files", out)



class AgentWithWorkspaceWiring(unittest.TestCase):
    """agent_with_workspace.py (README test 2) must not claim success when index.html was not written."""

    def run_script(self, writes_file):
        mods = install_fake_sdk(writes_file=False)
        # This script's agent writes index.html instead of hello.py.
        orig_chat = mods["google.antigravity"].Agent.chat

        async def chat(self, prompt):
            if writes_file:
                Path(self.workspace, "index.html").write_text("<html></html>", encoding="utf-8")
            return await orig_chat(self, prompt)
        mods["google.antigravity"].Agent.chat = chat
        saved = {k: sys.modules.get(k) for k in list(mods) + ["agent_with_workspace"]}
        sys.modules.update(mods)
        sys.modules.pop("agent_with_workspace", None)
        old_env, old_argv = os.environ.get("WORKSPACE_DIR"), sys.argv
        try:
            with tempfile.TemporaryDirectory() as d:
                os.environ["WORKSPACE_DIR"] = os.path.join(d, "ws")
                sys.argv = ["agent_with_workspace.py", "m"]
                import agent_with_workspace
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    asyncio.run(agent_with_workspace.main())
                return buf.getvalue()
        finally:
            sys.argv = old_argv
            if old_env is None:
                os.environ.pop("WORKSPACE_DIR", None)
            else:
                os.environ["WORKSPACE_DIR"] = old_env
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def test_written_index_html_is_reported_as_success(self):
        out = self.run_script(writes_file=True)
        self.assertIn("Agent task completed successfully", out)
        self.assertIn("Output file generated", out)

    def test_missing_index_html_is_not_reported_as_success(self):
        out = self.run_script(writes_file=False)
        self.assertNotIn("completed successfully", out)
        self.assertIn("did not create or change index.html", out)


if __name__ == "__main__":
    unittest.main()
