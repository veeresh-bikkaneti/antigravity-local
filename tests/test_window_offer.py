"""Stage 4's copy offer and the Ollama create call (docs/mockups/real-window.md, PR B)."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agl.app import agent, window_offer  # noqa: E402
from agl.core import window_fit  # noqa: E402
from agl.platform import ollama  # noqa: E402

QUESTION = "       Make a 16K copy now? It reuses your weights. No download. [y/N] "


def answers(*replies):
    asked = []

    def input_fn(prompt):
        asked.append(prompt)
        reply = replies[len(asked) - 1]
        if isinstance(reply, BaseException):
            raise reply
        return reply

    return input_fn, asked


class OfferTests(unittest.TestCase):
    def run_offer(self, reply, create=None, tag="qwen2.5:14b", target=16384):
        out, made = [], []
        input_fn, asked = answers(reply)

        def fake_create(src, new, num_ctx):
            made.append((src, new, num_ctx))
            return None

        result = window_offer.offer(tag, target, create=create or fake_create, input_fn=input_fn, out=out.append)
        return result, out, asked, made

    def test_yes_creates_and_switches(self):
        for reply in ("y", "yes", " YES "):
            result, out, asked, made = self.run_offer(reply)
            self.assertEqual(asked, [QUESTION])
            self.assertEqual(made, [("qwen2.5:14b", "qwen2.5:14b-ctx16k", 16384)])
            self.assertEqual(result, "qwen2.5:14b-ctx16k")
            self.assertEqual(out, [
                "       Made qwen2.5:14b-ctx16k. It uses the weights you already have.",
                "       This run will use qwen2.5:14b-ctx16k, with a 16,384 token window.",
            ])

    def test_no_and_end_of_input_change_nothing(self):
        for reply in ("", "n", "no", "sure", EOFError(), KeyboardInterrupt()):
            result, out, _, made = self.run_offer(reply)
            self.assertIsNone(result)
            self.assertEqual(made, [])
            self.assertEqual(out, ["       Keeping qwen2.5:14b. I'll offer the copy again next start."])

    def test_failed_create_keeps_the_model_and_says_why(self):
        result, out, _, _ = self.run_offer("y", create=lambda *a: "pulling manifest\nError: model not found\n")
        self.assertIsNone(result)
        self.assertEqual(out, [
            "       Could not make qwen2.5:14b-ctx16k. Keeping qwen2.5:14b.",
            "       Reason: Error: model not found. Nothing was downloaded.",
        ])

    def test_empty_error_uses_the_fallback_reason(self):
        _, out, _, _ = self.run_offer("y", create=lambda *a: "")
        self.assertEqual(out[1], "       Reason: the create command failed. Nothing was downloaded.")

    def test_long_reason_is_cut_to_one_short_line(self):
        _, out, _, _ = self.run_offer("y", create=lambda *a: "x" * 300)
        self.assertLess(len(out[1]), 100)

    def test_64k_and_8k_wording(self):
        result, out, asked, _ = self.run_offer("y", target=64000)
        self.assertEqual(result, "qwen2.5:14b-ctx64k")
        self.assertIn("Make a 64K copy now?", asked[0])
        _, out, asked, _ = self.run_offer("y", target=8192)
        self.assertIn("Make an 8K copy now?", asked[0])
        self.assertEqual(out[1], "       This run will use qwen2.5:14b-ctx8k, with an 8,192 token window.")

    def test_a_copy_of_a_copy_keeps_one_suffix(self):
        result, _, _, made = self.run_offer("y", tag="qwen2.5:14b-ctx8k")
        self.assertEqual(result, "qwen2.5:14b-ctx16k")
        self.assertEqual(made[0][0], "qwen2.5:14b-ctx8k")


class WantsCopyTests(unittest.TestCase):
    def test_cases(self):
        self.assertTrue(window_fit.wants_copy(4096, 16384, 131072))
        self.assertFalse(window_fit.wants_copy(32768, 16384, 131072))
        self.assertFalse(window_fit.wants_copy(8192, 16384, 8192))
        self.assertFalse(window_fit.wants_copy(4096, 0, 131072))
        self.assertFalse(window_fit.wants_copy(4096, None, None))
        self.assertTrue(window_fit.wants_copy(4096, 16384, None))


class CreateCopyTests(unittest.TestCase):
    def test_command_is_a_list_and_the_modelfile_has_two_lines(self):
        seen = {}

        def run(cmd, **kwargs):
            seen["cmd"], seen["kwargs"] = cmd, kwargs
            with open(cmd[4], encoding="utf-8") as f:
                seen["modelfile"] = f.read()
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        self.assertIsNone(ollama.create_copy("qwen2.5:14b", "qwen2.5:14b-ctx16k", 16384, run=run))
        self.assertEqual(seen["cmd"][:4], ["ollama", "create", "qwen2.5:14b-ctx16k", "-f"])
        self.assertNotIn("pull", seen["cmd"])
        self.assertEqual(seen["modelfile"], "FROM qwen2.5:14b\nPARAMETER num_ctx 16384\n")
        self.assertNotIn("shell", seen["kwargs"])
        self.assertTrue(seen["kwargs"]["timeout"])
        self.assertFalse(os.path.exists(seen["cmd"][4]))

    def test_failure_returns_the_error_text(self):
        def run(cmd, **k):
            return SimpleNamespace(returncode=1, stdout="", stderr="Error: boom\n")
        self.assertEqual(ollama.create_copy("a", "a-ctx16k", 16384, run=run), "Error: boom")

    def test_a_missing_ollama_returns_text_not_a_crash(self):
        def run(cmd, **k):
            raise FileNotFoundError("ollama")
        self.assertEqual(ollama.create_copy("a", "a-ctx16k", 16384, run=run), "ollama")


class SwitchTests(unittest.TestCase):
    def test_a_made_copy_is_saved_and_used(self):
        ports = mock.Mock()
        self.assertEqual(agent._switch_to_copy((16384, "model", "m-ctx16k"), "m", ports=ports), "m-ctx16k")
        ports.update_env_model.assert_called_once_with("m-ctx16k")

    def test_no_copy_keeps_the_model_and_saves_nothing(self):
        ports = mock.Mock()
        for checked in ((4096, "default"), None):
            self.assertEqual(agent._switch_to_copy(checked, "m", ports=ports), "m")
        ports.update_env_model.assert_not_called()


if __name__ == "__main__":
    unittest.main()
