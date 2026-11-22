"""v1.2.5: one speed badge per model row (Fast / Moderate / Slow), sizes on installed rows, one word, a legend."""
import re
import unittest

import model_wizard as mw
import run
from agl.platform import ollama


class SpeedLabel(unittest.TestCase):
    def test_four_cases_and_too_big(self):
        self.assertEqual(mw.speed_label(9.0, 16, 100), "Fast")        # 10.8 needed, fits in 16 GB of VRAM
        self.assertEqual(mw.speed_label(19.0, 16, 100), "Moderate")   # 22.8 needed, 16 >= half of it
        self.assertEqual(mw.speed_label(30.0, 16, 100), "Slow")       # 36 needed, 16 < half of it
        self.assertEqual(mw.speed_label(4.0, 0, 100), "Slow")         # no GPU at all
        self.assertIsNone(mw.speed_label(500.0, 16, 100))             # too big stays hidden
        self.assertIsNone(mw.speed_label(None, 16, 100))              # size unknown: never a guess


INFO = {"qwen2.5:14b": {"size_gb": 9.0, "digest": "a"}, "gemma2:27b": {"size_gb": 15.6, "digest": "b"},
        "hf.co/x/nano:q4_k_m": {"size_gb": 2.4, "digest": "c"}, "nano:q4_k_m": {"size_gb": 2.4, "digest": "c"}}
BADGES = {"qwen2.5:14b": ("tools",), "gemma2:27b": ("completion",), "hf.co/x/nano:q4_k_m": ("tools",)}


class Menu(unittest.TestCase):
    def menu(self, installed=("qwen2.5:14b", "gemma2:27b"), info=INFO):
        return mw.build_menu(list(installed), 16, 100, installed_info=info, badges=BADGES)

    def test_every_pick_row_has_exactly_one_speed_word_and_the_legend_is_there(self):
        lines = mw.render(self.menu(), "qwen2.5:14b")
        rows = [l for l in lines if re.match(r"\s+\*?\s*\d+\. ", l) and "More downloads" not in l and "Hugging Face" not in l]
        self.assertGreaterEqual(len(rows), 3)
        for l in rows:
            self.assertEqual(len(re.findall(r"\b(Fast|Moderate|Slow)\b", l)), 1, l)
        self.assertTrue(any(mw.LEGEND in l for l in lines))
        self.assertNotIn("?", "".join(l for l in rows))  # no guessed badges on the main menu

    def test_row_shape_name_speed_size_word_current(self):
        line = next(l for l in mw.render(self.menu(), "qwen2.5:14b") if "qwen2.5:14b" in l)
        self.assertRegex(line.strip(), r"^\*\s*\d+\. qwen2\.5:14b\s+Fast\s+9\.0 GB\s+tools\s+current$")

    def test_installed_model_with_no_tool_badge_says_chat_only(self):
        line = next(l for l in mw.render(self.menu(), "qwen2.5:14b") if "gemma2:27b" in l)
        self.assertIn("chat only", line)
        self.assertIn("Moderate", line)

    def test_unknown_installed_size_gets_no_speed_badge_and_no_guess(self):
        row = self.menu(info={})[0]
        self.assertIsNone(row["speed"])
        self.assertIsNone(row["size_gb"])
        self.assertNotRegex(mw._row_line(1, row, None, 12), r"Fast|Moderate|Slow|GB")

    def test_same_digest_is_one_row_different_or_missing_digest_keeps_both_and_says_so(self):
        same = [m["tag"] for m in self.menu(("hf.co/x/nano:q4_k_m", "nano:q4_k_m")) if m["installed"]]
        self.assertEqual(same, ["hf.co/x/nano:q4_k_m"])
        diff = dict(INFO, **{"nano:q4_k_m": {"size_gb": 2.4, "digest": "other"}})
        rows = [m for m in self.menu(("hf.co/x/nano:q4_k_m", "nano:q4_k_m"), diff) if m["installed"]]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all("different file" in m["twin"] for m in rows))
        nodigest = {k: {"size_gb": v["size_gb"]} for k, v in INFO.items()}
        rows = [m for m in self.menu(("hf.co/x/nano:q4_k_m", "nano:q4_k_m"), nodigest) if m["installed"]]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all("may be the same file" in m["twin"] for m in rows))

    def test_recommended_rows_keep_a_short_suffix_and_long_notes_are_gone(self):
        menu = mw.build_menu([], 16, 100, recommended="qwen3:8b", size_of=lambda tag, gb: {"gb": 5.2, "source": "list"})
        text = "\n".join(mw.render(menu, None))
        self.assertIn("recommended for this PC", text)
        self.assertNotIn("the established pick", text)
        self.assertNotIn("Built for agentic coding", text)

    def test_numbered_choice_enter_more_and_hf_rows_still_work(self):
        menu = self.menu()
        out = []
        self.assertEqual(mw.choose(menu, "qwen2.5:14b", input_fn=lambda _: "", out=out.append), "qwen2.5:14b")
        self.assertEqual(mw.choose(menu, "qwen2.5:14b", input_fn=lambda _: "1", out=out.append), "gemma2:27b")
        self.assertTrue(any("More downloads" in l for l in out))
        self.assertTrue(any("Hugging Face" in l for l in out))


class InstalledInfo(unittest.TestCase):
    def test_reads_size_in_bytes_and_digest_under_full_and_short_name(self):
        import io, json, urllib.request
        body = json.dumps({"models": [{"name": "hf.co/X/Nano:q4_k_m", "size": 2443115181, "digest": "abc"}]}).encode()
        real = urllib.request.urlopen
        urllib.request.urlopen = lambda *a, **k: io.BytesIO(body)
        try:
            info = ollama.installed_info()
        finally:
            urllib.request.urlopen = real
        self.assertAlmostEqual(info["hf.co/x/nano:q4_k_m"]["size_gb"], 2.44, places=2)
        self.assertEqual(info["nano:q4_k_m"]["digest"], "abc")

    def test_offline_gives_nothing_not_a_guess(self):
        import urllib.request
        real = urllib.request.urlopen

        def boom(*a, **k):
            raise OSError("down")
        urllib.request.urlopen = boom
        try:
            self.assertEqual(ollama.installed_info(), {})
        finally:
            urllib.request.urlopen = real


if __name__ == "__main__":
    unittest.main()
