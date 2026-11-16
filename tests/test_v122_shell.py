"""v1.2.2 shell: Ctrl+C and the SDK's close-time error end quietly, and the header prints once across the relaunch."""
import asyncio
import contextlib
import io
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import run  # noqa: E402

os.environ["ANTIGRAVITY_NO_RUN_LOG"] = "1"  # tests must not write into the real logs/ folder


class AntigravityExecutionError(Exception):
    """Stands in for the SDK error that Agent.__aexit__ raises after Ctrl+C (exit 0xC000013A on Windows)."""


def make_sdk(exit_error=None, enter_error=None, chat_error=None, close_fails_from=2):
    """A fake google.antigravity package. Each knob injects one failure at one point of the session."""
    state = {"chats": [], "opened": 0}

    class FakeAgent:
        def __init__(self, config):
            self.config = config

        async def __aenter__(self):
            state["opened"] += 1
            if enter_error is not None:
                raise enter_error
            return self

        async def __aexit__(self, *exc_info):
            # By default the demo agent (the first one opened) closes cleanly and the shell agent (the second) fails.
            if exit_error is not None and state["opened"] >= close_fails_from:
                raise exit_error
            return False

        async def chat(self, prompt):
            state["chats"].append(prompt)
            if chat_error is not None:
                raise chat_error

            async def chunks():
                if False:
                    yield ""  # an empty async stream
            return chunks()

    class FakeConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    pkg = types.ModuleType("google.antigravity")
    pkg.Agent = FakeAgent
    pkg.LocalOpenAIAgentConfig = FakeConfig
    types_mod = types.ModuleType("google.antigravity.types")
    types_mod.CapabilitiesConfig = lambda **kw: None
    hooks_mod = types.ModuleType("google.antigravity.hooks")
    policy_mod = types.SimpleNamespace(allow_all=lambda: None)
    hooks_mod.policy = policy_mod
    modules = {
        "google": types.ModuleType("google"),
        "google.antigravity": pkg,
        "google.antigravity.types": types_mod,
        "google.antigravity.hooks": hooks_mod,
    }
    return modules, state


def run_shell(inputs, **sdk_kwargs):
    """Run run.run_agent with a fake SDK and scripted typed input. Returns (stdout, exception or None, chats)."""
    modules, state = make_sdk(**sdk_kwargs)
    answers = iter(inputs)

    def fake_input(prompt=""):
        value = next(answers)
        if isinstance(value, BaseException):
            raise value
        return value

    out = io.StringIO()
    err = None
    with tempfile.TemporaryDirectory() as tmp, \
            mock.patch.dict(sys.modules, modules), \
            mock.patch.object(run, "PROJECT_DIR", tmp), \
            mock.patch.object(run, "_SETUP_ONLY", False), \
            mock.patch.object(run, "stage"), \
            mock.patch.object(run, "context_check"), \
            mock.patch.object(run, "level_clear"), \
            mock.patch("builtins.input", side_effect=fake_input), \
            contextlib.redirect_stdout(out):
        try:
            asyncio.run(run.run_agent("test-model"))
        except BaseException as exc:  # the tests assert on this, so capture everything
            err = exc
    return out.getvalue(), err, state["chats"]


class CleanExit(unittest.TestCase):
    def test_ctrl_c_at_prompt_then_sdk_close_error_is_quiet(self):
        out, err, _ = run_shell([KeyboardInterrupt()], exit_error=AntigravityExecutionError("0xC000013A"))
        self.assertIsNone(err)
        self.assertEqual(out.count("Goodbye"), 1)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("0xC000013A", out)

    def test_exit_word_then_sdk_close_error_is_quiet(self):
        out, err, _ = run_shell(["exit"], exit_error=AntigravityExecutionError("boom"))
        self.assertIsNone(err)
        self.assertEqual(out.count("Goodbye"), 1)
        self.assertNotIn("stopped unexpectedly", out)

    def test_ctrl_c_during_demo_is_a_clean_exit(self):
        out, err, chats = run_shell([], chat_error=KeyboardInterrupt(), close_fails_from=1,
                                    exit_error=AntigravityExecutionError("boom"))
        self.assertIsNone(err)
        self.assertEqual(len(chats), 1)  # the demo prompt
        self.assertIn("Goodbye", out)
        self.assertNotIn("stopped unexpectedly", out)

    def test_ctrl_c_during_demo_without_close_error_is_a_clean_exit(self):
        out, err, _ = run_shell([], chat_error=KeyboardInterrupt())
        self.assertIsNone(err)
        self.assertIn("Goodbye", out)

    def test_other_harness_error_prints_one_line_with_log_path(self):
        out, err, _ = run_shell([], enter_error=AntigravityExecutionError("backend down"))
        self.assertIsNone(err)
        self.assertIn("stopped unexpectedly", out)
        self.assertIn("Log:", out)
        self.assertNotIn("Traceback", out)

    def test_non_harness_error_still_surfaces(self):
        out, err, _ = run_shell(["exit"], exit_error=ValueError("a real bug"))
        self.assertIsInstance(err, ValueError)


class HeaderOnce(unittest.TestCase):
    def _header(self, env):
        buf = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(buf):
            run.print_header()
        return buf.getvalue()

    def test_flag_set_prints_nothing(self):
        self.assertEqual(self._header({run.HEADER_FLAG: "1"}), "")

    def test_flag_unset_prints_header(self):
        self.assertIn("Google Antigravity Local", self._header({}))


if __name__ == "__main__":
    unittest.main()
