"""PR A: real download sizes on every row. No test touches the network."""
import http.client
import io
import unittest
import urllib.error
from unittest import mock

import download_size
import model_wizard
import pull_gate
import run

_REAL_GET_JSON = download_size._get_json  # kept before any test patches it


class _Net(unittest.TestCase):
    def setUp(self):
        download_size.reset_cache()
        self.calls = []
        self.answers = {}  # url substring -> value to return from the fake _get_json

        def fake_get_json(url, headers=None, timeout=3):
            self.calls.append(url)
            for key, value in self.answers.items():
                if key in url:
                    return value
            return None

        patcher = mock.patch.object(download_size, "_get_json", side_effect=fake_get_json)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(download_size.reset_cache)


class ManifestSize(_Net):
    def test_registry_layers_are_summed(self):  # pass/fail 1: sum the manifest layers
        self.answers["manifests/27b"] = {"layers": [{"size": 10_000_000_000}, {"size": 6_000_000_000}, {"size": 1}]}
        self.assertEqual(download_size.ollama_registry_size("qwen3.6:27b"), 16_000_000_001)
        self.assertTrue(any("library/qwen3.6/manifests/27b" in c for c in self.calls))

    def test_one_request_per_tag_per_run(self):
        self.answers["manifests/27b"] = {"layers": [{"size": 5}]}
        download_size.ollama_registry_size("qwen3.6:27b")
        download_size.ollama_registry_size("qwen3.6:27b")
        self.assertEqual(len(self.calls), 1)

    def test_a_layer_without_a_size_means_no_total(self):
        self.answers["manifests/27b"] = {"layers": [{"size": 5}, {"digest": "x"}]}
        self.assertIsNone(download_size.ollama_registry_size("qwen3.6:27b"))

    def test_other_registries_are_not_sized(self):
        self.assertIsNone(download_size.ollama_registry_size("hf.co/user/repo:Q4_K_M"))
        self.assertEqual(self.calls, [])


class EstimateFallback(_Net):
    def test_estimate_from_parameter_count(self):  # pass/fail 3: estimate when the registry is silent
        self.assertAlmostEqual(download_size.estimate_gb("qwen3.6:27b"), 15.1875)
        self.assertIsNone(download_size.estimate_gb("laguna-xs.2:latest"))

    def test_resolve_marks_an_estimate(self):
        info = download_size.resolve("qwen3.6:27b")
        self.assertEqual(info["source"], "estimate")
        self.assertAlmostEqual(info["gb"], 15.1875)

    def test_resolve_prefers_registry_then_list(self):
        self.answers["manifests/27b"] = {"layers": [{"size": 2_000_000_000}]}
        self.assertEqual(download_size.resolve("qwen3.6:27b", 17.8), {"gb": 2.0, "source": "registry"})
        download_size.reset_cache()
        self.answers.clear()
        self.assertEqual(download_size.resolve("qwen3.6:27b", 17.8), {"gb": 17.8, "source": "list"})

    def test_offline_stops_asking_and_falls_back(self):  # pass/fail 3: offline never crashes, asks once
        with mock.patch.object(download_size, "_get_json", _REAL_GET_JSON), \
                mock.patch("urllib.request.OpenerDirector.open", side_effect=urllib.error.URLError("no net")) as opened:
            self.assertIsNone(download_size.ollama_registry_size("qwen3.6:27b"))
            self.assertIsNone(download_size.ollama_registry_size("gpt-oss:20b"))
        self.assertEqual(opened.call_count, 1)  # the second tag was not even asked for
        self.assertEqual(download_size.resolve("gpt-oss:20b")["source"], "estimate")


class SameHostRedirects(unittest.TestCase):  # pass/fail 5: no new host followed
    def test_same_host_redirect_is_followed(self):
        h = download_size._SameHostOnly()
        req = mock.Mock(full_url="https://registry.ollama.ai/v2/a")
        with mock.patch("urllib.request.HTTPRedirectHandler.redirect_request", return_value="FOLLOW") as base:
            self.assertEqual(h.redirect_request(req, None, 302, "Found", {}, "https://registry.ollama.ai/v2/b"), "FOLLOW")
            base.assert_called_once()

    def test_redirect_to_another_host_returns_none(self):
        h = download_size._SameHostOnly()
        req = mock.Mock(full_url="https://registry.ollama.ai/v2/a")
        self.assertIsNone(h.redirect_request(req, None, 302, "Found", {}, "https://evil.example/blob"))


class MenuRows(_Net):
    def test_rows_show_registry_list_and_estimate_text(self):  # pass/fail 1, 3: every row has a size, and an estimate says so
        self.answers["manifests/27b"] = {"layers": [{"size": 12_300_000_000}]}
        menu = model_wizard.build_menu([], 24.0, 32.0, catalog=[], recommended="qwen3.6:27b",
                                       library=[{"tag": "llama3.1:70b", "badges": ()}],
                                       size_of=download_size.resolve)
        text = "\n".join(model_wizard.render(menu, "qwen3.6:27b"))
        self.assertIn("12.3 GB download", text)
        self.assertIn("~", text)  # llama3.1:70b has no registry answer here, so it is an estimate
        self.assertIn("(estimate)", text)
        self.assertNotIn("size unknown", text)

    def test_no_size_source_still_says_unknown(self):
        menu = model_wizard.build_menu([], 24.0, 32.0, catalog=[], library=[{"tag": "mystery", "badges": ()}])
        self.assertIn("size unknown", "\n".join(model_wizard.render(menu, None)))

    def test_without_size_of_nothing_is_fetched(self):
        model_wizard.build_menu([], 24.0, 32.0, recommended="qwen3.6:27b")
        self.assertEqual(self.calls, [])


class HuggingFaceSizes(_Net):
    FILES = [{"name": "m-Q4_K_M.gguf", "size": 2_400_000_000}, {"name": "m-Q8_0.gguf", "size": 8_500_000_000}]

    def test_search_row_shows_the_quant_that_would_be_pulled(self):  # pass/fail 2
        with mock.patch.object(model_wizard, "hf_tree_files", return_value=self.FILES):
            info = download_size.hf_quant_size("u", "r", 24.0, 32.0)
        self.assertEqual(info["quant"], "Q8_0")  # the largest that fits 24 GB VRAM
        row = {"repo": "u/r", "quant": info["quant"], "size_gb": info["gb"], "size_source": info["source"]}
        self.assertIn("Q8_0 8.5 GB download", model_wizard._search_size_text(row))

    def test_no_files_means_no_size(self):
        with mock.patch.object(model_wizard, "hf_tree_files", return_value=[]):
            self.assertIsNone(download_size.hf_quant_size("u", "r", 24.0, 32.0))
        self.assertEqual(model_wizard._search_size_text({"repo": "u/r"}), "")

    def test_estimated_hf_size_is_labelled(self):
        # Q2_K is sized and only sets the parameter count; Q4_K_M has no size, so its size is an estimate.
        files = [{"name": "m-Q2_K.gguf", "size": 1_000_000_000}, {"name": "m-Q4_K_M.gguf", "size": None}]
        with mock.patch.object(model_wizard, "hf_tree_files", return_value=files):
            info = download_size.hf_quant_size("u", "r", 24.0, 32.0)
        self.assertEqual(info["quant"], "Q4_K_M")
        self.assertEqual(info["source"], "estimate")
        self.assertIn("(estimate)", model_wizard._search_size_text({"quant": "Q4_K_M", "size_gb": 2.0,
                                                                    "size_source": "estimate"}))


class PullQuestion(unittest.TestCase):
    def _plan(self, source, size=12.3):
        return {"tag": "qwen3.6:27b", "quant": None, "size_gb": size, "size_source": source, "license": None,
                "gated": False, "free_disk_gb": 200.0, "disk_total_gb": 500.0}

    def _ask(self, plan):
        lines = []
        pull_gate.ask_pull(plan, True, input_fn=lambda _: "n", out=lines.append)
        return "\n".join(lines)

    def test_pull_question_shows_registry_source(self):  # pass/fail 4
        self.assertIn("size: 12.3 GB (from Ollama registry)", self._ask(self._plan("registry")))

    def test_pull_question_marks_estimates(self):
        self.assertIn("size: ~12.3 GB (estimate)", self._ask(self._plan("estimate")))

    def test_pull_question_defaults_to_no(self):  # a blank answer never pulls
        decision = pull_gate.ask_pull(self._plan("registry"), True, input_fn=lambda _: "", out=lambda _: None)
        self.assertEqual(decision, "no")


class CouncilFixes(unittest.TestCase):
    """Regression tests for the council findings on PR 41: wrong estimate, malformed registry reply,
    cross-host redirect on the Hub path, and no offline stop for the Hub path."""

    def setUp(self):
        download_size.reset_cache()
        self.addCleanup(download_size.reset_cache)

    def test_a_tag_like_e2b_is_not_read_as_2b(self):
        # gemma3n:e2b is a 5.6 GB pull; a "2b" guess would print about 1.1 GB.
        self.assertIsNone(download_size.estimate_gb("gemma3n:e2b"))
        self.assertIsNotNone(download_size.estimate_gb("qwen3-coder:30b"))

    def test_a_registry_reply_with_a_wrong_shape_does_not_crash(self):
        with mock.patch.object(download_size, "_get_json", return_value={"layers": 5}):
            self.assertIsNone(download_size.ollama_registry_size("qwen3:8b"))

    def test_the_hub_path_uses_the_same_host_opener(self):
        handlers = download_size.model_wizard._HF_OPENER.handlers
        self.assertTrue(any(isinstance(h, model_wizard._SameHostOnly) for h in handlers))

    def test_a_network_failure_on_the_hub_stops_later_calls_in_the_run(self):
        model_wizard._STATE["offline"] = False
        self.addCleanup(lambda: model_wizard._STATE.__setitem__("offline", False))
        with mock.patch.object(model_wizard._HF_OPENER, "open", side_effect=urllib.error.URLError("down")):
            self.assertEqual(model_wizard.hf_tree_files("u", "r"), [])
        self.assertTrue(model_wizard._STATE["offline"])
        with mock.patch.object(model_wizard, "hf_tree_files") as tree:
            self.assertIsNone(download_size.hf_quant_size("u", "r", 24.0, 32.0))
            tree.assert_not_called()


class FixPass(unittest.TestCase):
    """PR 41 fix pass: truncated reply, total time budget, offline at the Hub call, escaping, rows that are shown."""

    def setUp(self):
        download_size.reset_cache()
        self.addCleanup(download_size.reset_cache)

    def test_a_cut_off_reply_returns_none_and_is_not_an_outage(self):
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.side_effect = http.client.IncompleteRead(b"")
        with mock.patch.object(download_size._OPENER, "open", return_value=resp):
            self.assertIsNone(download_size.ollama_registry_size("qwen3:8b"))
        self.assertFalse(download_size._STATE["offline"])

    def test_no_lookup_opens_a_connection_once_the_budget_is_spent(self):
        download_size._STATE["started"] = 0.0
        with mock.patch.object(download_size.time, "monotonic", return_value=download_size.SIZE_BUDGET_S + 1.0),                 mock.patch.object(download_size._OPENER, "open") as opened,                 mock.patch.object(model_wizard, "hf_tree_files") as tree:
            self.assertIsNone(download_size._get_json("https://registry.ollama.ai/v2/x"))
            self.assertIsNone(download_size.hf_quant_size("u", "r", 24.0, 32.0))
        opened.assert_not_called()
        tree.assert_not_called()

    def test_the_hub_is_not_asked_again_when_it_is_offline(self):
        model_wizard._STATE["offline"] = True
        res = {"free_disk_gb": 100, "disk_total_gb": 500}
        with mock.patch.object(run, "_free_for_fit", return_value=(24.0, 32.0)),                 mock.patch.object(model_wizard, "hf_repo_info") as info,                 mock.patch.object(model_wizard, "hf_tree_files") as tree, mock.patch("builtins.print"):
            plan = run._plan_download("hf.co/u/r:Q4_K_M", {}, res)
        self.assertIsNotNone(plan)
        info.assert_not_called()
        tree.assert_not_called()

    def test_a_tag_that_could_change_the_request_path_is_refused(self):
        with mock.patch.object(download_size, "_get_json") as got:
            for bad in ("qwen3:7b?x=1", "qwen3:7b#x", "qwen3:7b x", "qwen3:7b..x"):
                self.assertIsNone(download_size.ollama_registry_size(bad), bad)
        got.assert_not_called()

    def test_all_ten_valid_rows_are_sized_after_three_invalid_ones(self):
        rows = [{"repo": "bad"}, {"repo": ""}, {"repo": "a/b/c"}] + [{"repo": f"u/m{i}"} for i in range(10)]
        info = {"gb": 4.0, "quant": "Q4_K_M", "source": "hugging face"}
        with mock.patch.object(run, "hf_menu_search", return_value=rows),                 mock.patch.object(download_size, "hf_quant_size", return_value=info) as sized:
            run.hf_menu_search_sized("x", 24.0, 32.0, limit=10)
        self.assertEqual(sized.call_count, 10)


if __name__ == "__main__":
    unittest.main()
