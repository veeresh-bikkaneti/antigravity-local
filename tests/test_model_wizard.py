import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import model_wizard as mw  # noqa: E402


class FitLabel(unittest.TestCase):
    def test_16gb_gpu_128gb_ram(self):
        self.assertEqual(mw.fit_label(13.8, 16, 128), "gpu")
        self.assertEqual(mw.fit_label(17.7, 16, 128), "split")

    def test_cpu_only_small_box_hides_big_models(self):
        self.assertEqual(mw.fit_label(15.2, 0, 8), "too big")


class BuildMenu(unittest.TestCase):
    def test_installed_first_and_not_repeated_in_catalog(self):
        menu = mw.build_menu(["qwen3.6:27b", "gemma2:27b"], 16, 128)
        self.assertEqual([m["tag"] for m in menu[:2]], ["gemma2:27b", "qwen3.6:27b"])
        self.assertTrue(all(m["installed"] for m in menu[:2]))
        self.assertEqual([m["tag"] for m in menu].count("qwen3.6:27b"), 1)

    def test_too_big_models_are_left_out(self):
        tags = [m["tag"] for m in mw.build_menu([], 8, 16)]
        self.assertNotIn("laguna-xs.2:latest", tags)
        self.assertIn("gpt-oss:20b", tags)

    def test_implicit_latest_tag_counts_as_installed(self):
        menu = mw.build_menu(["laguna-xs.2"], 16, 128)
        self.assertEqual([m["tag"] for m in menu].count("laguna-xs.2:latest"), 0)


class Choose(unittest.TestCase):
    MENU = mw.build_menu(["qwen2.5:14b"], 16, 128)

    def pick(self, *answers, default="qwen2.5:14b"):
        feed = iter(answers)
        out = []
        tag = mw.choose(self.MENU, default, input_fn=lambda _="": next(feed), out=out.append)
        return tag, out

    def test_enter_keeps_current(self):
        self.assertEqual(self.pick("")[0], "qwen2.5:14b")

    def test_number_picks_menu_row(self):
        self.assertEqual(self.pick("2")[0], self.MENU[1]["tag"])

    def test_custom_tag_is_accepted(self):
        self.assertEqual(self.pick("qwen3.9:30b")[0], "qwen3.9:30b")

    def test_out_of_range_reasks_then_falls_back_after_three(self):
        tag, out = self.pick("99", "0", "-1")
        self.assertEqual(tag, "qwen2.5:14b")
        self.assertGreaterEqual(sum("Pick 1 to" in line for line in out), 2)

    def test_eof_falls_back(self):
        def boom(_=""):
            raise EOFError
        self.assertEqual(mw.choose(self.MENU, "qwen2.5:14b", input_fn=boom, out=lambda *_: None), "qwen2.5:14b")

    def test_menu_text_says_it_is_untested_and_shows_sizes(self):
        text = "\n".join(mw.render(self.MENU, "qwen2.5:14b"))
        self.assertIn("not yet run through this project", text)
        self.assertIn("GB download", text)


class TagExists(unittest.TestCase):
    def test_offline_is_unknown_not_false(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertIsNone(mw.tag_exists("qwen3.6:27b"))


if __name__ == "__main__":
    unittest.main()
