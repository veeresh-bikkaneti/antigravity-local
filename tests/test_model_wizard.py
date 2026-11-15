import json
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

    def test_a_yes_or_no_is_not_a_model_name_and_asks_again(self):
        tag, out = self.pick("y", "")
        self.assertEqual(tag, "qwen2.5:14b")
        self.assertIn("       That looks like a yes/no answer. Type a number, a model tag, or press Enter for qwen2.5:14b.", out)

    def test_yes_no_in_any_case_with_spaces_then_a_number_picks_that_row(self):
        for answer in ("NO", " Yes ", "n", "y"):
            with self.subTest(answer=answer):
                self.assertEqual(self.pick(answer, "2")[0], self.MENU[1]["tag"])

    def test_eof_after_a_yes_behaves_like_eof_today(self):
        answers = iter(["y"])

        def input_fn(_=""):
            try:
                return next(answers)
            except StopIteration:
                raise EOFError

        out = []
        self.assertEqual(mw.choose(self.MENU, "qwen2.5:14b", input_fn=input_fn, out=out.append), "qwen2.5:14b")
        self.assertEqual(sum("yes/no" in line for line in out), 1)

    def test_three_yes_no_answers_use_up_the_tries_and_fall_back(self):
        self.assertEqual(self.pick("y", "n", "yes")[0], "qwen2.5:14b")

    def test_out_of_range_reasks_then_falls_back_after_three(self):
        tag, out = self.pick("99", "0", "-1")
        self.assertEqual(tag, "qwen2.5:14b")
        self.assertGreaterEqual(sum("Pick 1 to" in line for line in out), 2)

    def test_eof_falls_back(self):
        def boom(_=""):
            raise EOFError
        self.assertEqual(mw.choose(self.MENU, "qwen2.5:14b", input_fn=boom, out=lambda *_: None), "qwen2.5:14b")

    def test_ctrl_c_is_not_an_answer(self):
        """Ctrl+C means stop. It must reach the caller instead of quietly picking the default."""
        def ctrl_c(_=""):
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            mw.choose(self.MENU, "qwen2.5:14b", input_fn=ctrl_c, out=lambda *_: None)

    def test_menu_text_says_it_is_untested_and_shows_sizes(self):
        text = "\n".join(mw.render(self.MENU, "qwen2.5:14b"))
        self.assertIn("not yet run through this project", text)
        self.assertIn("GB download", text)


class Recommended(unittest.TestCase):
    def test_recommended_row_comes_first_and_is_not_repeated(self):
        menu = mw.build_menu([], 0, 32, recommended="gpt-oss:20b")
        self.assertEqual(menu[0]["tag"], "gpt-oss:20b")
        self.assertEqual([m["tag"] for m in menu].count("gpt-oss:20b"), 1)
        self.assertIn("recommended for this PC", menu[0]["note"])
        self.assertIsNone(menu[0]["size_gb"])

    def test_row_without_a_size_renders_as_size_unknown_not_a_crash(self):
        menu = mw.build_menu([], 0, 32, recommended="llama3.2:3b")
        self.assertIn("size unknown", "\n".join(mw.render(menu, "llama3.2:3b")))

    def test_recommended_that_is_already_installed_is_not_added_again(self):
        menu = mw.build_menu(["llama3.2:3b"], 0, 32, recommended="llama3.2:3b")
        self.assertEqual([m["tag"] for m in menu].count("llama3.2:3b"), 1)


class SmallFixes(unittest.TestCase):
    def test_empty_menu_without_default_does_not_promise_row_one(self):
        text = "\n".join(mw.render([], None))
        self.assertIn("automatic pick", text)
        self.assertNotIn("picks 1", text)

    def test_typed_tag_is_lowercased(self):
        menu = mw.build_menu([], 16, 128)
        got = mw.choose(menu, "a:1", input_fn=lambda _="": "Qwen3:8B", out=lambda *_: None)
        self.assertEqual(got, "qwen3:8b")


def _hub_reply(files, status=200):
    """A pretend huggingface.co/api/models/... reply for urllib.request.urlopen."""
    import io
    import json
    import urllib.error
    if status != 200:
        return urllib.error.HTTPError("https://huggingface.co/api/models/x/y", status, "err", {}, io.BytesIO(b""))
    body = json.dumps({"id": "x/y", "siblings": [{"rfilename": f} for f in files]}).encode()
    reply = mock.MagicMock()
    reply.__enter__.return_value.read.return_value = body
    return reply


class HuggingFace(unittest.TestCase):
    FILES = ["README.md", "Nanbeige4.1-3B.Q4_K_M.gguf", "Nanbeige4.1-3B.Q8_0.gguf", "Nanbeige4.1-3B.IQ4_XS.gguf",
             "Nanbeige4.1-3B.f16.gguf"]

    def check(self, tag, reply):
        effect = reply if isinstance(reply, BaseException) else None
        with mock.patch.object(mw.urllib.request, "urlopen", side_effect=effect, return_value=None if effect else reply):
            return mw.hf_check(tag)

    def test_tag_shapes(self):
        self.assertTrue(mw.is_hf_tag("hf.co/a/b:q4_k_m"))
        self.assertTrue(mw.is_hf_tag("HuggingFace.co/a/b"))
        self.assertFalse(mw.is_hf_tag("qwen3.6:27b"))
        self.assertEqual(mw.parse_hf_tag("hf.co/mradermacher/Nanbeige4.1-3B-GGUF:Q4_K_M"),
                         ("mradermacher", "Nanbeige4.1-3B-GGUF", "Q4_K_M"))
        self.assertEqual(mw.parse_hf_tag("huggingface.co/a/b"), ("a", "b", None))
        for bad in ("hf.co/justone", "hf.co/a/b/c", "hf.co//b", "qwen3.6:27b"):
            self.assertIsNone(mw.parse_hf_tag(bad), bad)

    def test_repo_that_exists_is_ok_with_or_without_a_quant(self):
        self.assertEqual(self.check("hf.co/x/y", _hub_reply(self.FILES)), ("ok", None))
        self.assertEqual(self.check("hf.co/x/y:q4_k_m", _hub_reply(self.FILES)), ("ok", None))
        self.assertEqual(self.check("hf.co/x/y:IQ4_XS", _hub_reply(self.FILES)), ("ok", None))

    def test_404_means_missing(self):
        self.assertEqual(self.check("hf.co/x/nope", _hub_reply([], status=404)), ("missing", None))

    def test_offline_and_private_are_unknown_not_refused(self):
        self.assertEqual(self.check("hf.co/x/y", OSError("no network")), ("unknown", None))
        self.assertEqual(self.check("hf.co/x/y", _hub_reply([], status=401)), ("unknown", None))
        self.assertEqual(self.check("hf.co/x/y", _hub_reply([], status=500)), ("unknown", None))

    def test_a_quant_the_repo_does_not_have_lists_the_ones_it_has(self):
        status, have = self.check("hf.co/x/y:q5_k_m", _hub_reply(self.FILES))
        self.assertEqual(status, "no_quant")
        self.assertEqual(have, ["F16", "IQ4_XS", "Q4_K_M", "Q8_0"])

    def test_a_repo_with_no_gguf_files_has_no_quants(self):
        self.assertEqual(self.check("hf.co/x/y:q4_k_m", _hub_reply(["model.safetensors"])), ("no_quant", []))

    def test_bad_shape_never_touches_the_network(self):
        with mock.patch.object(mw.urllib.request, "urlopen", side_effect=AssertionError("no network")):
            self.assertEqual(mw.hf_check("hf.co/justone"), ("bad_tag", None))

    def test_the_hub_check_only_sends_the_repo_name(self):
        with mock.patch.object(mw.urllib.request, "urlopen", return_value=_hub_reply(self.FILES)) as call:
            mw.hf_check("hf.co/x/y:q4_k_m")
        self.assertEqual(call.call_args.args[0], "https://huggingface.co/api/models/x/y")


class HuggingFaceMenu(unittest.TestCase):
    def test_ollama_menu_ends_with_the_hugging_face_row_and_lists_nanbeige(self):
        menu = mw.build_menu(["qwen2.5:14b"], 16, 128)
        self.assertTrue(menu[-1].get("hf"))
        self.assertIn("Hugging Face model (type hf.co/user/repo:quant)", "\n".join(mw.render(menu, "qwen2.5:14b")))
        nb = [m for m in menu if m["tag"].startswith("hf.co/mradermacher/nanbeige4.1-3b-gguf")]
        self.assertEqual(len(nb), 1)
        self.assertTrue(mw.is_hf_tag(nb[0]["tag"]) and mw.parse_hf_tag(nb[0]["tag"])[2] == "q4_k_m")

    def test_openai_backend_has_only_what_the_server_lists(self):
        menu = mw.build_menu(["lm-model-a", "lm-model-b"], 16, 128, backend="openai", recommended="qwen2.5-coder:7b")
        self.assertEqual([m["tag"] for m in menu], ["lm-model-a", "lm-model-b"])
        self.assertFalse(any(m.get("hf") for m in menu))
        text = "\n".join(mw.render(menu, "lm-model-a", backend="openai"))
        self.assertNotIn("Hugging Face", text)
        self.assertIn("a model id your server lists", text)
        self.assertNotIn("Ollama tag", text)

    def test_picking_the_hf_row_asks_for_a_tag_and_returns_it_lowercased(self):
        menu = mw.build_menu(["qwen2.5:14b"], 16, 128)
        row = str(len(menu))
        answers = iter([row, "HF.co/User/Repo:Q4_K_M"])
        got = mw.choose(menu, "qwen2.5:14b", input_fn=lambda _="": next(answers), out=lambda *_: None)
        self.assertEqual(got, "hf.co/user/repo:q4_k_m")

    def test_hf_row_with_a_blank_or_wrong_answer_keeps_the_default(self):
        menu = mw.build_menu(["qwen2.5:14b"], 16, 128)
        row = str(len(menu))
        for typed in ("", "not-a-hf-tag", "qwen3.6:27b"):
            answers = iter([row, typed, typed, typed])
            got = mw.choose(menu, "qwen2.5:14b", input_fn=lambda _="": next(answers), out=lambda *_: None)
            self.assertEqual(got, "qwen2.5:14b", typed)

    def test_the_placeholder_row_is_never_the_fallback(self):
        menu = [m for m in mw.build_menu([], 0, 0, catalog=[]) ]
        self.assertEqual(mw.choose(menu, None, input_fn=lambda _="": "", out=lambda *_: None), None)


class TagExists(unittest.TestCase):
    def test_other_registry_is_unknown_and_never_asks_ollama(self):
        # tag_exists swallows exceptions, so a raising mock would pass vacuously; assert on calls instead.
        with mock.patch("urllib.request.urlopen") as opened:
            self.assertIsNone(mw.tag_exists("hf.co/a/b:q4"))
            self.assertIsNone(mw.tag_exists("registry.example.com/team/model:1"))
        opened.assert_not_called()

    def test_plain_and_namespaced_ollama_tags_still_hit_the_registry(self):
        with mock.patch("urllib.request.urlopen") as opened:
            self.assertTrue(mw.tag_exists("qwen3.6:27b"))
            self.assertTrue(mw.tag_exists("someuser/mymodel:1"))
        self.assertEqual(opened.call_count, 2)

    def test_offline_is_unknown_not_false(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertIsNone(mw.tag_exists("qwen3.6:27b"))


class MenuBadges(unittest.TestCase):
    """Badges sit AFTER the bracket, so the row still starts with its number and tag."""

    def rows(self, menu, default=None):
        return mw.render(menu, default)

    def test_installed_rows_show_what_ollama_said(self):
        menu = mw.build_menu(["qwen3:8b"], 16, 128, badges={"qwen3:8b": ("tools", "thinking")})
        self.assertEqual(menu[0]["badges"], ("tools", "thinking"))
        line = next(l for l in self.rows(menu) if "qwen3:8b" in l)
        self.assertRegex(line.strip(), r"^1\. qwen3:8b  \[installed, no download\]  \(tools, thinking\)  already on this machine$")

    def test_unknown_badges_show_nothing_rather_than_a_guess(self):
        menu = mw.build_menu(["old:1b"], 16, 128, badges={})
        self.assertEqual(menu[0]["badges"], ())
        self.assertNotIn("(", next(l for l in self.rows(menu) if "old:1b" in l))

    def test_catalog_rows_carry_the_curated_badges_and_guesses_keep_their_question_mark(self):
        menu = {m["tag"]: m for m in mw.build_menu([], 16, 128)}
        self.assertIn("tools", menu["gpt-oss:20b"]["badges"])
        self.assertIn("tools?", menu["qwen3.8:27b"]["badges"])
        text = "\n".join(self.rows(list(menu.values())))
        self.assertIn("(tools?, thinking?)", text)

    def test_a_coding_name_gets_a_coding_badge_once(self):
        menu = mw.build_menu(["qwen2.5-coder:7b"], 16, 128, badges={"qwen2.5-coder:7b": ("tools", "coding")})
        self.assertEqual(menu[0]["badges"].count("coding"), 1)

    def test_rows_stay_alphabetical_whatever_the_badges(self):
        menu = mw.build_menu(["zeta:1", "alpha:1"], 16, 128, badges={"zeta:1": ("tools",)})
        self.assertEqual([m["tag"] for m in menu[:2]], ["alpha:1", "zeta:1"])

    def test_library_rows_are_added_once_and_never_duplicate_an_installed_or_catalog_model(self):
        lib = [{"tag": "newmodel:7b", "badges": ("tools",), "note": "n"}, {"tag": "newmodel:7b"}, {"tag": "gpt-oss:20b"}]
        tags = [m["tag"] for m in mw.build_menu([], 16, 128, library=lib)]
        self.assertEqual(tags.count("newmodel:7b"), 1)
        self.assertEqual(tags.count("gpt-oss:20b"), 1)


class MediaSection(unittest.TestCase):
    MEDIA = [{"tag": "x/z-image-turbo", "badges": ("image",), "note": "text to image",
              "hint": 'Run it with: ollama run x/z-image-turbo "a red fox"'}]

    def menu(self):
        return mw.build_menu(["qwen3:8b"], 16, 128, media=self.MEDIA)

    def test_media_rows_come_before_the_hf_row_which_stays_last(self):
        menu = self.menu()
        self.assertTrue(menu[-1].get("hf"))
        self.assertTrue(menu[-2].get("media"))

    def test_render_prints_a_section_header_once_and_marks_the_row(self):
        menu = mw.build_menu([], 16, 128, media=self.MEDIA * 2)
        lines = mw.render(menu, None)
        self.assertEqual(sum("Media models" in l for l in lines), 1)
        row = next(l for l in lines if "x/z-image-turbo" in l)
        self.assertIn("[media]  (image)", row)

    def test_picking_a_media_row_shows_how_to_run_it_and_asks_again_never_returning_it(self):
        menu = self.menu()
        n = str([m["tag"] for m in menu].index("x/z-image-turbo") + 1)
        feed, out = iter([n, ""]), []
        got = mw.choose(menu, "qwen3:8b", input_fn=lambda _="": next(feed), out=out.append)
        self.assertEqual(got, "qwen3:8b")
        self.assertTrue(any('ollama run x/z-image-turbo "a red fox"' in l for l in out))

    def test_a_media_row_is_never_the_fallback_when_there_is_no_default(self):
        menu = mw.build_menu([], 16, 128, media=self.MEDIA, catalog=[])
        out = []
        got = mw.choose(menu, None, input_fn=lambda _="": "", out=out.append)
        self.assertIsNone(got)  # nothing but a media row and the HF placeholder: no pick, never the media row

    def test_three_media_picks_in_a_row_fall_back_to_the_default(self):
        menu = self.menu()
        n = str([m["tag"] for m in menu].index("x/z-image-turbo") + 1)
        feed = iter([n, n, n])
        self.assertEqual(mw.choose(menu, "qwen3:8b", input_fn=lambda _="": next(feed), out=lambda l: None), "qwen3:8b")


class HfSearchAtTheMenu(unittest.TestCase):
    RESULTS = [{"repo": "Org/Fast-GGUF", "badges": ("tools?",), "downloads": 12345},
               {"repo": "org/Other", "badges": (), "downloads": None}]

    def ask(self, answers, search):
        feed, out, seen = iter(answers), [], []

        def fake_search(words):
            seen.append(words)
            return search

        got = mw._ask_hf_tag(lambda p="": next(feed), out.append, "fallback:1", fake_search)
        return got, out, seen

    def test_words_are_searched_and_a_pick_becomes_an_hf_tag(self):
        got, out, seen = self.ask(["Fast coder", "1"], self.RESULTS)
        self.assertEqual(got, "hf.co/org/fast-gguf")
        self.assertEqual(seen, ["fast coder"])
        text = "\n".join(out)
        self.assertIn("Org/Fast-GGUF  (tools?)  12,345 downloads", text)
        self.assertIn("a ? after a badge is a guess", text)

    def test_a_real_hf_tag_is_taken_as_typed_without_searching(self):
        got, _, seen = self.ask(["hf.co/u/r:q4_k_m"], self.RESULTS)
        self.assertEqual((got, seen), ("hf.co/u/r:q4_k_m", []))

    def test_no_results_says_so_and_asks_again(self):
        got, out, _ = self.ask(["nothing here", ""], [])
        self.assertEqual(got, "fallback:1")
        self.assertTrue(any("No GGUF models found" in l for l in out))

    def test_enter_at_the_result_list_goes_back_and_a_bad_number_is_not_a_pick(self):
        self.assertEqual(self.ask(["words", "", ""], self.RESULTS)[0], "fallback:1")
        self.assertEqual(self.ask(["words", "99", ""], self.RESULTS)[0], "fallback:1")

    def test_a_bare_yes_or_no_is_not_searched(self):
        got, out, seen = self.ask(["yes", ""], self.RESULTS)
        self.assertEqual((got, seen), ("fallback:1", []))

    def test_without_a_search_function_words_are_still_refused_like_before(self):
        feed, out = iter(["some words", ""]), []
        self.assertEqual(mw._ask_hf_tag(lambda p="": next(feed), out.append, "fb"), "fb")
        self.assertTrue(any("not a Hugging Face tag" in l for l in out))

    def test_eof_while_picking_a_result_goes_back(self):
        answers = iter(["words"])

        def input_fn(prompt=""):
            try:
                return next(answers)
            except StopIteration:
                raise EOFError

        got = mw._ask_hf_tag(input_fn, lambda l: None, "fb", lambda words: self.RESULTS)
        self.assertEqual(got, "fb")


class TreePages(unittest.TestCase):
    """hf_tree_files follows next-page links, but never past max_pages: a partial list would undercount split quants."""

    class _Page:
        def __init__(self, rows, link=""):
            self.body, self.headers = json.dumps(rows).encode(), {"Link": link}

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def pages(self, n):
        nxt = '<https://huggingface.co/api/models/u/r/tree/main?cursor=%d>; rel="next"'
        return [self._Page([{"type": "file", "path": f"m-Q4_K_M-0000{i}-of-0000{n}.gguf", "size": 1}], nxt % i)
                for i in range(1, n + 1)]

    def test_more_pages_than_the_cap_gives_nothing(self):
        with mock.patch("urllib.request.urlopen", side_effect=self.pages(8)):
            self.assertEqual(mw.hf_tree_files("u", "r", max_pages=5), [])

    def test_pages_within_the_cap_are_all_read(self):
        last = self._Page([{"type": "file", "path": "m-Q4_K_M-00003-of-00003.gguf", "size": 1}])
        first_two = self.pages(2)
        with mock.patch("urllib.request.urlopen", side_effect=first_two + [last]):
            got = mw.hf_tree_files("u", "r", max_pages=5)
        self.assertEqual(len(got), 3)


class FitFree(unittest.TestCase):
    """The fit rule against FREE memory: size x 1.2 in VRAM is a GPU fit, else it can spill into 70% of free RAM."""

    def fit(self, size, vram, ram):
        return mw.fit_label(size, vram, ram, headroom=mw.FIT_HEADROOM)

    def test_gpu_fit_needs_twenty_percent_headroom(self):
        self.assertEqual(self.fit(13.3, 16, 0), "gpu")   # 13.3 x 1.2 = 15.96
        self.assertEqual(self.fit(13.4, 16, 0), "too big")  # 16.08: no RAM to spill into

    def test_cpu_only_split_fit_is_labelled_slow(self):
        self.assertEqual(self.fit(15.2, 0, 128), "split")  # 18.2 <= 0.7 x 128
        self.assertIn("slow", mw.FIT_TEXT["split"])

    def test_nothing_free_fits_nothing(self):
        self.assertEqual(self.fit(1.0, 0, 0), "too big")

    def test_the_old_total_vram_default_is_unchanged(self):
        self.assertEqual(mw.fit_label(13.8, 16, 128), "gpu")  # 13.8 x 1.11 = 15.3: the old 90% rule



class HugeNumbers(unittest.TestCase):
    """int() refuses 4300+ digits; a typed number that long must be a polite no, not a crash."""

    def test_choose_treats_a_huge_number_as_out_of_range(self):
        menu = mw.build_menu(["a:1"], 16, 128)
        feed, out = iter(["1" * 5000, "", ""]), []
        got = mw.choose(menu, "a:1", input_fn=lambda _="": next(feed), out=out.append)
        self.assertEqual(got, "a:1")
        self.assertTrue(any("Pick 1 to" in l for l in out))

    def test_a_huge_number_at_the_search_list_goes_back(self):
        rows = [{"repo": "org/r", "badges": (), "downloads": 1}]
        self.assertIsNone(mw._search_pick(rows, lambda _="": "9" * 5000, lambda l: None))

    def test_a_normal_number_still_works_at_the_search_list(self):
        rows = [{"repo": "Org/R", "badges": (), "downloads": 1}]
        self.assertEqual(mw._search_pick(rows, lambda _="": "1", lambda l: None), "hf.co/org/r")


if __name__ == "__main__":
    unittest.main()
