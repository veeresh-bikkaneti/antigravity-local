"""C4 B3: `/steps` in the shell, the resume question, the git guard and the optional test command. Fakes only."""
import asyncio
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import agl.app.agent  # noqa: E402
from agl.app import step_runner, step_shell  # noqa: E402
from agl.core import checkpoint, steps  # noqa: E402
from agl.platform import step_io  # noqa: E402

BLANK = checkpoint.render(checkpoint.TEMPLATE, "T")
OPEN_TWO = steps.with_plan(BLANK, ["a", "b"], "T")


class FakeIO:
    """In-memory stand-in for agl/platform/step_io.py."""

    def __init__(self, text=BLANK, tracked=False, test_result=(0, [])):
        self.texts = [text]
        self.tracked = tracked
        self.test_result = test_result
        self.tests_run = []

    def checkpoint_path(self, workspace):
        return Path("<repo>") / ".agl" / "checkpoint.md"

    def read_checkpoint(self, workspace):
        return self.texts[-1]

    def write_checkpoint(self, workspace, text):
        self.texts.append(text)

    def is_tracked(self, workspace):
        return self.tracked

    def run_test(self, cmd, workspace):
        self.tests_run.append(cmd)
        return self.test_result


class FakeAgent:
    """Every chat replies from `reply(prompt)`; plan prompts get three steps, checks say yes."""

    prompts = []

    def __init__(self, config=None):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def chat(self, prompt):
        FakeAgent.prompts.append(prompt)
        if prompt.startswith("Split"):
            reply = "1. a\n2. b\n3. c"
        elif prompt.startswith("Answer yes"):
            reply = "yes"
        else:
            reply = "ok"

        async def chunks():
            yield reply
        return chunks()


def answers(*values):
    pending = list(values)

    def ask(prompt):
        if not pending:
            raise EOFError
        return pending.pop(0)
    return ask


def ports_with(io):
    return types.SimpleNamespace(step_io=io, task_report=types.SimpleNamespace(snapshot=lambda ws: {}))


def kw(io, *inputs, window=32768):
    lines = []
    out = lambda text="", end="\n", flush=False: lines.append(text + end)  # noqa: E731
    return {"new_agent": FakeAgent, "workspace": "ws", "window": window, "ports": ports_with(io),
            "out": out, "input_fn": answers(*inputs)}, lines


class StepShellTests(unittest.TestCase):
    def setUp(self):
        FakeAgent.prompts = []

    def test_steps_line_runs_the_runner_with_task_and_window(self):
        io = FakeIO()
        args, lines = kw(io, "y", "", window=16384)
        with mock.patch.object(step_runner, "run_steps", wraps=step_runner.run_steps) as spy:
            result = asyncio.run(step_shell.handle("/steps build it", **args))
        self.assertEqual(result, "done")
        self.assertEqual(spy.call_count, 1)
        self.assertEqual(spy.call_args.args[0], "build it")
        self.assertEqual(spy.call_args.kwargs["window"], 16384)
        self.assertIn("Step mode. Window: 16384 tokens. Each step is a fresh chat.\n", lines)
        self.assertIn("Planning. Nothing runs until you type y.\n", lines)

    def test_bare_steps_prints_usage_and_runs_nothing(self):
        io = FakeIO()
        args, lines = kw(io)
        self.assertEqual(asyncio.run(step_shell.handle("/steps", **args)), "usage")
        self.assertEqual(lines, ["Usage: /steps <task>\n"])
        self.assertEqual(FakeAgent.prompts, [])

    def test_is_steps(self):
        self.assertTrue(step_shell.is_steps("/steps"))
        self.assertTrue(step_shell.is_steps("/steps do x"))
        self.assertFalse(step_shell.is_steps("/stepsx"))
        self.assertFalse(step_shell.is_steps("what are /steps"))

    def test_resume_yes_runs_open_steps(self):
        io = FakeIO(OPEN_TWO)
        args, _ = kw(io, "y", "")
        self.assertEqual(asyncio.run(step_shell.offer_resume(**args)), "done")
        self.assertEqual(steps.done_steps(io.texts[-1]), ["a", "b"])
        self.assertFalse(any(p.startswith("Split") for p in FakeAgent.prompts))

    def test_resume_no_enter_and_eof_run_nothing(self):
        for inputs in (("n",), ("",), ()):
            with self.subTest(inputs=inputs):
                FakeAgent.prompts = []
                io = FakeIO(OPEN_TWO)
                args, _ = kw(io, *inputs)
                self.assertEqual(asyncio.run(step_shell.offer_resume(**args)), "no")
                self.assertEqual(len(io.texts), 1)
                self.assertEqual(FakeAgent.prompts, [])

    def test_no_open_steps_asks_nothing(self):
        io = FakeIO(BLANK)
        asked = []
        args, _ = kw(io)
        args["input_fn"] = lambda prompt: asked.append(prompt) or "y"
        self.assertEqual(asyncio.run(step_shell.offer_resume(**args)), "none")
        self.assertEqual(asked, [])

    def test_tracked_checkpoint_writes_nothing(self):
        io = FakeIO(tracked=True)
        args, lines = kw(io, "y")
        self.assertEqual(asyncio.run(step_shell.handle("/steps x", **args)), "tracked")
        self.assertEqual(len(io.texts), 1)
        self.assertTrue(lines[0].startswith("Not changed: "))
        self.assertIn("is already tracked by git", lines[0])

    def test_no_port_or_workspace_is_unavailable(self):
        args, lines = kw(FakeIO())
        args["workspace"] = None
        self.assertEqual(asyncio.run(step_shell.handle("/steps x", **args)), "unavailable")
        args, _ = kw(FakeIO())
        args["ports"] = types.SimpleNamespace()
        self.assertEqual(asyncio.run(step_shell.offer_resume(**args)), "none")

    def test_window_from_stage_4(self):
        self.assertEqual(step_shell.window_from((32768, "env")), 32768)
        self.assertEqual(step_shell.window_from(None), 8192)
        self.assertEqual(step_shell.window_from(mock.Mock()), 8192)


class TestCommandTests(unittest.TestCase):
    def setUp(self):
        FakeAgent.prompts = []

    def run_with(self, io, *inputs):
        args, lines = kw(io, *inputs)
        return asyncio.run(step_shell.handle("/steps x", **args)), "".join(lines)

    def test_exit_zero_passes(self):
        io = FakeIO(test_result=(0, []))
        result, _ = self.run_with(io, "y", "python -m unittest")
        self.assertEqual(result, "done")
        self.assertEqual(io.tests_run, ["python -m unittest"] * 3)

    def test_exit_one_fails_and_shows_the_tail(self):
        io = FakeIO(test_result=(1, ["FAILED (errors=1)"]))
        result, text = self.run_with(io, "y", "pytest -q")
        self.assertEqual(result, "stopped")
        self.assertIn("Test failed (exit 1).\n  FAILED (errors=1)\n", text)
        self.assertEqual(steps.done_steps(io.texts[-1]), [])

    def test_timeout_counts_as_a_fail(self):
        io = FakeIO(test_result=(None, []))
        result, text = self.run_with(io, "y", "slow")
        self.assertEqual(result, "stopped")
        self.assertIn("Test timed out after 120 seconds.", text)

    def test_empty_skips_the_test(self):
        io = FakeIO(test_result=(1, []))
        result, _ = self.run_with(io, "y", "")
        self.assertEqual(result, "done")
        self.assertEqual(io.tests_run, [])

    def test_command_is_never_written(self):
        io = FakeIO()
        self.run_with(io, "y", "secret-cmd --flag")
        self.assertFalse(any("secret-cmd" in text for text in io.texts))

    def test_resume_asks_for_the_command_again(self):
        io = FakeIO(OPEN_TWO, test_result=(0, []))
        args, _ = kw(io, "y", "make test")
        self.assertEqual(asyncio.run(step_shell.offer_resume(**args)), "done")
        self.assertEqual(io.tests_run, ["make test", "make test"])


class StepIoTests(unittest.TestCase):
    def test_run_test_passes_a_list_and_no_shell(self):
        calls = []

        def fake_run(args, **kwargs):
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, stdout="a\nb\n", stderr="")
        code, tail = step_io.run_test("python -m unittest -q", "ws", run_fn=fake_run)
        self.assertEqual(code, 0)
        self.assertEqual(tail, ["a", "b"])
        args, kwargs = calls[0]
        self.assertIsInstance(args, list)
        self.assertEqual(args[:2], ["python", "-m"])
        self.assertNotIn("shell", kwargs)
        self.assertEqual(kwargs["timeout"], 120)

    def test_run_test_timeout_and_missing_program(self):
        def timeout(args, **kwargs):
            raise subprocess.TimeoutExpired(args, 120)

        def missing(args, **kwargs):
            raise FileNotFoundError("no such program")
        self.assertEqual(step_io.run_test("x", "ws", run_fn=timeout), (None, []))
        self.assertEqual(step_io.run_test("x", "ws", run_fn=missing)[0], 127)


class ShellHookTests(unittest.TestCase):
    def test_plain_input_still_goes_to_chat_and_steps_goes_to_step_mode(self):
        FakeAgent.prompts = []
        pkg = mock.Mock()
        pkg.Agent = FakeAgent
        io = FakeIO()
        ports = ports_with(io)
        ports.MAX_SHELL_FAILURES = 3
        inputs = answers("hello", "/steps", "exit")
        out = mock.Mock()
        with mock.patch.dict("sys.modules", {"google.antigravity": pkg}), \
                mock.patch.object(agl.app.agent, "_get_sdk", return_value=pkg):
            asyncio.run(agl.app.agent._run_shell("m", object(), {"left": False}, ports=ports, out=out,
                                                 input_fn=inputs, workspace="ws", window=(8192, "env")))
        self.assertEqual(FakeAgent.prompts, ["hello"])
        printed = [c.args[0] for c in out.call_args_list if c.args]
        self.assertIn("Usage: /steps <task>", printed)


if __name__ == "__main__":
    unittest.main()
