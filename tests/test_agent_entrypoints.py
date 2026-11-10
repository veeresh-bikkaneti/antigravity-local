"""--help must work with the SDK absent, and /clear must be wired into the REPL."""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestEntrypointHelp(unittest.TestCase):
    def _help(self, script):
        # -I + empty cwd import path: the SDK is not installed in CI/dev boxes without it,
        # and we block it explicitly so the test holds even where it is.
        code = (
            "import sys, runpy; sys.modules['google']=None; sys.argv=[%r,'--help']; "
            "runpy.run_path(%r, run_name='__main__')" % (script, os.path.join(ROOT, script))
        )
        return subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                              capture_output=True, text=True, encoding="utf-8", errors="replace")

    def test_help_without_sdk(self):
        for script in ("code_agent.py", "agent_with_workspace.py", "test_local.py"):
            with self.subTest(script=script):
                r = self._help(script)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("usage", r.stdout.lower())

    def test_missing_sdk_is_friendly(self):
        code = ("import sys, runpy; sys.modules['google']=None; sys.argv=['code_agent.py']; "
                "runpy.run_path('code_agent.py', run_name='__main__')")
        r = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 1)
        self.assertIn("pip install -r requirements.txt", r.stdout)


class TestClear(unittest.TestCase):
    def test_clear_recreates_agent_session(self):
        code = """
import sys, types, asyncio, builtins, tempfile
class A:
    n = 0
    def __init__(s, c): A.n += 1
    async def __aenter__(s): return s
    async def __aexit__(s, *a): pass
names = ['google', 'google.antigravity', 'google.antigravity.hooks', 'google.antigravity.types']
m = {k: types.ModuleType(k) for k in names}
m['google.antigravity'].Agent = A
m['google.antigravity'].LocalOpenAIAgentConfig = lambda **k: None
m['google.antigravity.hooks'].policy = types.SimpleNamespace(allow_all=lambda: None)
m['google.antigravity.types'].CapabilitiesConfig = lambda **k: None
sys.modules.update(m)
import code_agent
it = iter(['/clear', '/clear', 'exit'])
builtins.input = lambda p='': next(it)
asyncio.run(code_agent.run_interactive_session('u', 'm', tempfile.mkdtemp()))
print('SESSIONS', A.n)
"""
        r = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertIn("SESSIONS 3", r.stdout, r.stderr)


if __name__ == "__main__":
    unittest.main()


class TestPromptsNameRealFileTool(unittest.TestCase):
    """SDK 0.1.23 has write_to_file(TargetFile, CodeContent, Overwrite), not create_file."""

    def test_prompts_use_write_to_file(self):
        for script in ("run.py", "agent_with_workspace.py", "code_agent.py"):
            with self.subTest(script=script):
                with open(os.path.join(ROOT, script), encoding="utf-8") as f:
                    src = f.read()
                self.assertIn("write_to_file", src)
                self.assertIn("TargetFile", src)
                self.assertIn("CodeContent", src)
                self.assertNotIn("create_file", src)
