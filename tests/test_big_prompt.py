"""The shell's big-prompt question (docs/mockups/real-window.md section 5). Fakes only."""
import asyncio
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import agl.app.agent  # noqa: E402
from agl.app import big_prompt, step_shell  # noqa: E402

QUESTION = "       Send anyway? [Y/n] (or type /steps) "
OVER = "       Over the 4,096 window, so the model may forget the start."
HELD = "       Not sent. Nothing was cut, and the model was not changed."
BIG = "x" * 4 * 5000  # 5,000 tokens by checkpoint.tokens


def replies(*values):
    asked, pending = [], list(values)

    def input_fn(prompt):
        asked.append(prompt)
        value = pending.pop(0) if pending else EOFError()
        if isinstance(value, BaseException):
            raise value
        return value
    return input_fn, asked


class AskTests(unittest.TestCase):
    def run_ask(self, *answers, text=BIG, window=4096):
        out = []
        input_fn, asked = replies(*answers)
        return big_prompt.ask(text, window, input_fn=input_fn, out=out.append), out, asked

    def test_under_the_window_asks_nothing(self):
        choice, out, asked = self.run_ask(text="x" * 4 * 4096)
        self.assertEqual((choice, out, asked), (big_prompt.SEND, [], []))

    def test_an_unknown_window_asks_nothing(self):
        for window in (None, 0):
            self.assertEqual(self.run_ask(window=window)[0], big_prompt.SEND)

    def test_enter_and_yes_send_unchanged(self):
        for answer in ("", "y", " YES "):
            choice, out, asked = self.run_ask(answer)
            self.assertEqual(choice, big_prompt.SEND)
            self.assertEqual(out, [OVER])
            self.assertEqual(asked, [QUESTION])

    def test_no_and_end_of_input_hold_it(self):
        for answer in ("n", "no", "maybe", EOFError(), KeyboardInterrupt()):
            choice, out, _ = self.run_ask(answer)
            self.assertEqual(choice, big_prompt.HOLD)
            self.assertEqual(out, [OVER, HELD])

    def test_steps_hands_it_to_step_mode(self):
        self.assertEqual(self.run_ask("/steps")[0], big_prompt.STEPS)

    def test_the_window_in_the_question_is_the_running_one(self):
        _, out, _ = self.run_ask("", text="x" * 4 * 20000, window=16384)
        self.assertEqual(out, ["       Over the 16,384 window, so the model may forget the start."])

    def test_known_window(self):
        self.assertEqual(big_prompt.known_window((4096, "default")), 4096)
        self.assertEqual(big_prompt.known_window((16384, "model", "m-ctx16k")), 16384)
        for checked in (None, (), (0, "default"), ("x", "y")):
            self.assertIsNone(big_prompt.known_window(checked))


class FakeAgent:
    prompts = []

    def __init__(self, config=None):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def chat(self, prompt):
        FakeAgent.prompts.append(prompt)

        async def reply():
            yield "ok"
        return reply()


class ShellTests(unittest.TestCase):
    def run_shell(self, *typed):
        FakeAgent.prompts = []
        pkg = SimpleNamespace(Agent=FakeAgent)
        ports = SimpleNamespace(MAX_SHELL_FAILURES=3)
        input_fn, _ = replies(*typed, "exit")
        out = mock.Mock()
        with mock.patch.object(agl.app.agent, "_get_sdk", return_value=pkg), \
                mock.patch.object(agl.app.agent, "_resume", mock.AsyncMock()), \
                mock.patch.object(step_shell, "handle", mock.AsyncMock()) as handle:
            asyncio.run(agl.app.agent._run_shell("m", object(), {"left": False}, ports=ports, out=out,
                                                 input_fn=input_fn, workspace="ws", window=(4096, "default")))
        printed = [c.args[0] for c in out.call_args_list if c.args]
        return printed, handle

    def test_a_held_prompt_never_reaches_the_model(self):
        printed, _ = self.run_shell(BIG, "n")
        self.assertEqual(FakeAgent.prompts, [])
        self.assertIn(HELD, printed)

    def test_enter_sends_the_whole_prompt(self):
        self.run_shell(BIG, "")
        self.assertEqual(FakeAgent.prompts, [BIG])

    def test_steps_runs_step_mode_with_the_prompt_as_its_task(self):
        _, handle = self.run_shell(BIG, "/steps")
        self.assertEqual(FakeAgent.prompts, [])
        self.assertEqual(handle.await_args.args[0], "/steps " + BIG)

    def test_a_short_prompt_is_sent_without_a_question(self):
        printed, _ = self.run_shell("hello")
        self.assertEqual(FakeAgent.prompts, ["hello"])
        self.assertNotIn(OVER, printed)


if __name__ == "__main__":
    unittest.main()
