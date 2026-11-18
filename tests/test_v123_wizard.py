"""v1.2.3 regressions: the give-up line names the right kind of default, and only Enter records an upgrade stay."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import model_wizard  # noqa: E402

MENU = model_wizard.build_menu({"qwen2.5:14b"}, 16.0, 64.0)


def ask(answers, default="qwen2.5:14b", label=None):
    feed, lines, result = iter(answers), [], {}
    got = model_wizard.choose(MENU, default, input_fn=lambda p="": next(feed), out=lines.append,
                              validate_fn=lambda t: "       nope" if t in ("hello", "x1", "zz") else None,
                              default_label=label, result=result)
    return got, "\n".join(str(x) for x in lines), result.get("how")


class GiveUpLabel(unittest.TestCase):
    def test_installed_default_says_current_model(self):
        _, text, _ = ask(["hello", "x1", "zz"], label="current model")
        self.assertIn("using qwen2.5:14b (current model).", text)

    def test_hardware_pick_default_says_recommended_pick(self):
        _, text, _ = ask(["hello", "x1", "zz"], default="qwen2.5-coder:14b", label="recommended pick")
        self.assertIn("using qwen2.5-coder:14b (recommended pick).", text)
        self.assertNotIn("current model", text)


class HowItEnded(unittest.TestCase):
    def test_enter_is_enter(self):
        self.assertEqual(ask([""])[2], "enter")

    def test_a_valid_pick_is_pick(self):
        got, _, how = ask(["1"])
        self.assertEqual((got, how), (MENU[0]["tag"], "pick"))

    def test_three_bad_tries_is_gave_up_even_though_the_default_comes_back(self):
        got, _, how = ask(["hello", "x1", "zz"])
        self.assertEqual((got, how), ("qwen2.5:14b", "gave_up"))


class CodingAppsBlock(unittest.TestCase):
    def test_every_app_row_carries_the_real_model_and_url(self):
        import coding_apps
        text = "
".join(coding_apps.lines("qwen2.5:14b", "http://localhost:11434/v1"))
        for app in ("VS Code", "Continue", "Terminal", "Antigravity", "Gemini CLI", "Your code"):
            self.assertIn(app, text)
        self.assertIn("apiBase http://localhost:11434,", text)
        self.assertIn("base_url http://localhost:11434/v1, model qwen2.5:14b", text)
        self.assertIn("docs/coding-apps.md", text)

    def test_an_openai_server_drops_the_ollama_only_rows(self):
        import coding_apps
        text = "
".join(coding_apps.lines("m", "http://box:1234/v1", backend="openai"))
        self.assertNotIn("Ollama.ollama", text)
        self.assertNotIn("provider ollama", text)
        self.assertIn("base_url http://box:1234/v1, model m", text)


if __name__ == "__main__":
    unittest.main()
