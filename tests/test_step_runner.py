"""Step runner tests. Fakes only: no real agent, no disk, no terminal."""

import asyncio
import io
import unittest
from datetime import datetime, timezone
from unittest import mock

from agl.app.step_runner import parse_plan, run_steps
from agl.core import checkpoint, steps

TASK = "Add a health page and a test that opens it"
CK_PATH = r"<repo>\.agl\checkpoint.md"
STEPS = [
    "Add health.html with one status line",
    "Add test_health.py that reads that file",
    "Link health.html from index.html",
    "Note both files in the checkpoint",
    "Leave a one-line note for the next session",
]
PLAN_REPLY = "\n".join(f"{i}. {text}" for i, text in enumerate(STEPS, 1))
SEED = (
    "# Checkpoint\n\n<!-- agl-checkpoint v1 -->\nupdated: 2026-11-27T12:00:00+00:00 (example)\n\n"
    "## Plan\n\n- The goal: a health page and a test that opens it.\n\n"
    "## Done\n\n- (none yet)\n\n## Next\n\n- (none yet)\n\n"
    "## Files\n\n- (none yet)\n\n## Notes\n\n- User: keep it short\n"
)


def now():
    return datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


class Script:
    """Scripted replies. Plan and step prompts get fixed text; checks pop from `checks`, else yes."""

    def __init__(self, checks=(), interrupt_on=None):
        self.checks = list(checks)
        self.interrupt_on = interrupt_on

    def __call__(self, prompt):
        if self.interrupt_on and self.interrupt_on in prompt:
            raise KeyboardInterrupt
        if prompt.startswith("Split this task"):
            return PLAN_REPLY
        if prompt.startswith("Answer yes or no"):
            return self.checks.pop(0) if self.checks else "yes"
        return "Wrote a file."


async def _chunks(text):
    for word in text.split(" "):
        yield word + " "


class _FakeAgent:
    def __init__(self, factory):
        self.factory = factory

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def chat(self, prompt):
        self.factory.prompts.append(prompt)
        return _chunks(self.factory.script(prompt))


class FakeFactory:
    """Counts agent entries and records every prompt sent."""

    def __init__(self, script=None):
        self.script = script or Script()
        self.entries = 0
        self.prompts = []

    def __call__(self):
        self.entries += 1
        return _FakeAgent(self)


class Store:
    """In-memory checkpoint: read_ck and write_ck over a list."""

    def __init__(self, text=""):
        self.items = [text]
        self.writes = 0

    def read(self):
        return self.items[-1]

    def write(self, text):
        self.writes += 1
        self.items.append(text)


def make_input(answers):
    """input_fn from a list. Raises EOFError when the list is empty. Records each prompt."""
    queue, asked = list(answers), []

    def input_fn(prompt):
        asked.append(prompt)
        if not queue:
            raise EOFError
        return queue.pop(0)

    input_fn.asked = asked
    return input_fn


def go(factory, store, answers, *, window=8192, input_fn=None):
    out = io.StringIO()
    asker = input_fn or make_input(answers)
    result = asyncio.run(run_steps(
        TASK,
        new_agent=factory,
        read_ck=store.read,
        write_ck=store.write,
        snapshot=lambda: {},
        window=window,
        system_tokens=665,
        input_fn=asker,
        out=out,
        now=now,
        checkpoint_path=CK_PATH,
    ))
    return result, out.getvalue(), asker


def touched(created=(), changed=()):
    """Pin what task_report.summarize reports for every check in the run."""
    return mock.patch("agl.core.task_report.summarize",
                      return_value=(list(created), list(changed)))


class StepRunnerTests(unittest.TestCase):
    def test_five_steps_fit_8k(self):
        factory, store = FakeFactory(), Store(SEED)
        result, _, _ = go(factory, store, ["y"], window=8192)
        self.assertEqual(result, "done")
        self.assertEqual(steps.done_steps(store.read()), STEPS)
        self.assertEqual(steps.open_steps(store.read()), [])
        for prompt in factory.prompts:
            self.assertLessEqual(665 + checkpoint.tokens(prompt) + 1024, 8192)

    def test_five_steps_at_32k(self):
        factory, store = FakeFactory(), Store(SEED)
        result, _, _ = go(factory, store, ["y"], window=32768)
        self.assertEqual(result, "done")
        self.assertEqual(steps.done_steps(store.read()), STEPS)

    def test_fresh_context_for_each_call(self):
        factory, store = FakeFactory(), Store(SEED)
        go(factory, store, ["y"])
        self.assertEqual(factory.entries, 1 + 5 * 2)

    def test_kill_then_resume_skips_done_steps(self):
        first = FakeFactory(Script(interrupt_on="This step: " + STEPS[2] + "\n"))
        store = Store(SEED)
        result, _, _ = go(first, store, ["y"])
        self.assertEqual(result, "stopped")
        self.assertEqual(steps.done_steps(store.read()), STEPS[:2])

        second = FakeFactory()
        result, out, asker = go(second, store, [])
        self.assertEqual(result, "done")
        self.assertFalse(any("Split this task" in p for p in second.prompts))
        self.assertFalse(any("Accept this plan?" in p for p in asker.asked))
        self.assertFalse(any("This step: " + s + "\n" in p
                             for p in second.prompts for s in STEPS[:2]))
        self.assertEqual(steps.done_steps(store.read()), STEPS)

    def test_check_no_then_eof_at_retry_stops_with_step_open(self):
        factory = FakeFactory(Script(checks=["no"]))
        store = Store(SEED)
        result, out, _ = go(factory, store, ["y"])
        self.assertEqual(result, "stopped")
        self.assertIn("Stopped. Step 1 is still open.", out)
        self.assertEqual(steps.open_steps(store.read())[0], STEPS[0])
        self.assertEqual(steps.done_steps(store.read()), [])

    def test_check_no_then_skip_marks_skipped_and_goes_on(self):
        factory = FakeFactory(Script(checks=["no"]))
        store = Store(SEED)
        result, out, _ = go(factory, store, ["y", "s"])
        self.assertEqual(result, "done")
        self.assertEqual(steps.done_steps(store.read())[0], "(skipped) " + STEPS[0])
        self.assertIn("Skipped step 1. Next is step 2.", out)

    def test_plan_declined_or_eof_writes_nothing(self):
        for answers in (["n"], []):
            with self.subTest(answers=answers):
                factory, store = FakeFactory(), Store(SEED)
                result, out, _ = go(factory, store, answers)
                self.assertEqual(result, "declined")
                self.assertEqual(store.writes, 0)
                self.assertIn("Plan dropped. Nothing was written.", out)

    def test_goal_and_user_note_survive_the_run(self):
        factory, store = FakeFactory(), Store(SEED)
        go(factory, store, ["y"])
        text = store.read()
        self.assertIn("- The goal: a health page and a test that opens it.", text)
        self.assertIn("- User: keep it short", text)

    def test_window_too_small_sends_no_step(self):
        factory, store = FakeFactory(), Store(SEED)
        result, out, _ = go(factory, store, ["y"], window=1000)
        self.assertEqual(result, "too_big")
        self.assertIn("This step does not fit the window. It was not sent.", out)
        self.assertFalse(any(p.startswith("You are doing one step") for p in factory.prompts))

    def test_parse_plan(self):
        self.assertEqual(parse_plan("1. Only one"), [])
        self.assertEqual(parse_plan("\n".join(f"{i}. s{i}" for i in range(1, 10))), [])
        self.assertEqual(parse_plan("1. a\n2) b\n3. c\n4. d\n5. e"),
                         ["a", "b", "c", "d", "e"])

    def test_pass_line_one_new_file(self):
        factory, store = FakeFactory(), Store(SEED)
        with touched(created=["health.html"]):
            _, out, _ = go(factory, store, ["y"])
        self.assertIn("Check passed. health.html is new.", out.splitlines())

    def test_pass_line_two_changed_files(self):
        factory, store = FakeFactory(), Store(SEED)
        with touched(changed=["a.py", "b.py"]):
            _, out, _ = go(factory, store, ["y"])
        self.assertIn("Check passed. a.py, b.py changed.", out.splitlines())

    def test_pass_line_no_files(self):
        factory, store = FakeFactory(), Store(SEED)
        with touched():
            _, out, _ = go(factory, store, ["y"])
        self.assertIn("Check passed.", out.splitlines())

    def test_fail_line_with_files_is_bare(self):
        factory = FakeFactory(Script(checks=["no"]))
        store = Store(SEED)
        with touched(changed=["a.py"]):
            _, out, _ = go(factory, store, ["y"])
        lines = out.splitlines()
        self.assertIn("Check failed.", lines)
        self.assertNotIn("No file was created or changed.", out)

    def test_fail_line_without_files_says_nothing_changed(self):
        factory = FakeFactory(Script(checks=["no"]))
        store = Store(SEED)
        with touched():
            _, out, _ = go(factory, store, ["y"])
        self.assertIn("Check failed. No file was created or changed.", out.splitlines())

    def test_wrote_line_is_exact(self):
        factory, store = FakeFactory(), Store(SEED)
        _, out, _ = go(factory, store, ["y"])
        self.assertIn(r"Wrote <repo>\.agl\checkpoint.md with 5 open steps.", out.splitlines())

    def test_ctrl_c_mid_stream_starts_a_new_line(self):
        factory = FakeFactory(Script(interrupt_on="This step: " + STEPS[0] + "\n"))
        store = Store(SEED)
        result, out, _ = go(factory, store, ["y"])
        self.assertEqual(result, "stopped")
        self.assertIn("Agent > \nInterrupted on step 1. Nothing is saved yet.", out)


if __name__ == "__main__":
    unittest.main()
