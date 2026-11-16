"""v1.2.2 regressions: one model list, bad input asks again, and a small model never beats a fitting bigger one."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import model_wizard  # noqa: E402
import ranking  # noqa: E402

UPGRADE = {"tag": "qwen3-coder:30b", "gb": 18.0, "label": "catalog", "fit": "split"}


def menu(upgrade=None):
    return model_wizard.build_menu({"qwen2.5:14b"}, 16.0, 64.0, upgrade=upgrade)


def ask(rows, answers, default="qwen2.5:14b"):
    feed, prompts, lines = iter(answers), [], []

    def fake_input(prompt=""):
        prompts.append(prompt)
        return next(feed)

    known = {r["tag"] for r in rows}
    got = model_wizard.choose(rows, default, input_fn=fake_input, out=lines.append,
                              validate_fn=lambda t: None if t in known else f"       '{t}' is not a model I can find.")
    return got, prompts, "\n".join(str(x) for x in lines)


class OneList(unittest.TestCase):
    def test_upgrade_is_a_marked_row_and_enter_asks_once(self):
        rows = menu(UPGRADE)
        self.assertTrue(any(r.get("note") == "recommended upgrade" and r["tag"] == UPGRADE["tag"] for r in rows))
        got, prompts, _ = ask(rows, [""])
        self.assertEqual(got, "qwen2.5:14b")
        self.assertEqual(len(prompts), 1)


class ReAsk(unittest.TestCase):
    def test_a_bad_tag_then_a_number_picks_that_item(self):
        rows = menu()
        got, prompts, text = ask(rows, ["hello", "4"])
        self.assertEqual(got, rows[3]["tag"])
        self.assertEqual(len(prompts), 2)
        self.assertIn("'hello' is not a model I can find", text)

    def test_three_bad_tries_use_the_default_and_say_so(self):
        got, _, text = ask(menu(), ["hello", "x1", "zz"])
        self.assertEqual(got, "qwen2.5:14b")
        self.assertIn("No valid pick after 3 tries, using qwen2.5:14b (current model).", text)


class SizeAwarePick(unittest.TestCase):
    def test_a_3b_never_beats_a_fitting_14b(self):
        pool = [
            {"tag": "gemma2:27b", "kind": "chat", "fit": "split", "size_gb": 15.0, "badges": (), "installed": True},
            {"tag": "hf.co/mradermacher/nanbeige4.1-3b-gguf:q4_k_m", "kind": "chat", "fit": "gpu", "size_gb": 2.4,
             "badges": ("tools", "thinking"), "installed": True, "last_modified": "2026-11-01T00:00:00Z",
             "name_score": 92},
            {"tag": "qwen2.5:14b", "kind": "chat", "fit": "gpu", "size_gb": 9.0, "badges": ("tools",),
             "installed": True, "last_modified": "2024-09-01T00:00:00Z", "name_score": 88},
        ]
        self.assertEqual(ranking.best_for_agent(pool)["tag"], "qwen2.5:14b")
        self.assertEqual(ranking.best_for_agent(list(reversed(pool)))["tag"], "qwen2.5:14b")


if __name__ == "__main__":
    unittest.main()
