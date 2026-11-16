"""--check-upgrades (report only), the interactive upgrade offer, and the same-host registry and Hub fixes."""
import builtins
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import model_wizard  # noqa: E402
import run  # noqa: E402

HW = {"ram_gb": 64.0, "vram_gb": 24.0, "gpu_name": "test gpu"}
DAY = 24 * 3600


class CheckUpgradesCommand(unittest.TestCase):
    def run_cmd(self, installed, reachable=True, argv=("--check-upgrades",)):
        out = io.StringIO()
        with mock.patch.object(model_wizard, "registry_reachable", return_value=reachable), \
                mock.patch.object(run, "get_hardware_profile", return_value=HW), \
                mock.patch.object(run, "get_free_resources", return_value={}), \
                mock.patch.object(run, "_free_for_fit", return_value=(24.0, 64.0)), \
                mock.patch.object(run, "get_installed_ollama_models", return_value=set(installed)), \
                mock.patch.object(run.download_size, "resolve", return_value=None), \
                contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as cm:
                run._main(list(argv))
        return cm.exception.code, out.getvalue()

    def test_prints_the_better_fitting_models_and_exits_0_without_pulling(self):
        with mock.patch.object(run.subprocess, "check_call", side_effect=AssertionError("must not pull")):
            code, text = self.run_cmd({"llama3.2:3b"})
        self.assertEqual(code, 0)
        self.assertIn("Best installed model: llama3.2:3b", text)
        self.assertIn("gpt-oss:20b  14.0 GB (catalog)", text)
        self.assertIn("fits your GPU", text)
        self.assertIn("Report only", text)

    def test_offline_prints_couldnt_check_and_exits_0(self):
        code, text = self.run_cmd({"llama3.2:3b"}, reachable=False)
        self.assertEqual(code, 0)
        self.assertIn("couldn't check", text)

    def test_an_exception_still_exits_0(self):
        with mock.patch.object(model_wizard, "registry_reachable", side_effect=RuntimeError("boom")), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(run.run_check_upgrades(), 0)
        self.assertIn("couldn't check", out.getvalue())


class InteractiveOffer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = os.path.join(self.tmp.name, "state.json")
        patch = mock.patch.object(run, "UPGRADE_STATE_FILE", self.state)
        patch.start()
        self.addCleanup(patch.stop)
        self.now = 1_800_000_000.0

    def offer(self, answer=None, now=None):
        ask = (mock.MagicMock(return_value=answer) if answer is not None
               else mock.MagicMock(side_effect=AssertionError("must not prompt")))
        with mock.patch.object(builtins, "input", ask), \
                contextlib.redirect_stdout(io.StringIO()):
            tag = run.offer_upgrade({"llama3.2:3b"}, HW, 24.0, 64.0, now=self.now if now is None else now)
        return tag, ask

    def test_enter_stays_and_never_returns_a_pull(self):
        tag, ask = self.offer(answer="")
        self.assertIsNone(tag)
        self.assertEqual(ask.call_count, 1)
        with open(self.state, encoding="utf-8") as f:
            self.assertAlmostEqual(json.load(f)["stay_until"], self.now + 7 * DAY)

    def test_upgrade_now_returns_the_top_pick(self):
        tag, _ = self.offer(answer="upgrade now")
        self.assertIn(tag, [t for t, _, _ in model_wizard.CATALOG])

    def test_stay_is_remembered_for_seven_days(self):
        self.offer(answer="")
        tag, ask = self.offer(answer=None, now=self.now + 6 * DAY)
        self.assertIsNone(tag)
        ask.assert_not_called()

    def test_the_prompt_returns_after_seven_days(self):
        self.offer(answer="")
        tag, ask = self.offer(answer="", now=self.now + 8 * DAY)
        self.assertIsNone(tag)
        self.assertEqual(ask.call_count, 1)

    def test_no_installed_model_means_no_offer(self):
        with mock.patch.object(builtins, "input", side_effect=AssertionError("must not ask")):
            self.assertIsNone(run.offer_upgrade(set(), HW, 24.0, 64.0, now=self.now))


class SameHostRegistry(unittest.TestCase):
    def test_a_cross_host_redirect_is_not_followed(self):
        req = urllib.request.Request("https://registry.ollama.ai/v2/library/x/manifests/latest", method="HEAD")
        handler = model_wizard._SameHostOnly()
        self.assertIsNone(handler.redirect_request(req, None, 302, "Found", {}, "https://elsewhere.example/blob"))

    def test_tag_exists_is_unknown_when_the_registry_redirects_away(self):
        redirect = urllib.error.HTTPError("https://registry.ollama.ai/v2/x", 302, "Found", {}, None)
        with mock.patch.object(model_wizard._REGISTRY_OPENER, "open", side_effect=redirect), \
                mock.patch.object(urllib.request, "urlopen", side_effect=AssertionError("must use the same-host opener")):
            self.assertIsNone(model_wizard.tag_exists("qwen3.6:27b"))

    def test_hf_repo_info_goes_through_the_same_host_opener(self):
        missing = urllib.error.HTTPError("https://huggingface.co/api/models/u/r", 404, "Not Found", {}, None)
        with mock.patch.object(model_wizard._HF_OPENER, "open", side_effect=missing), \
                mock.patch.object(urllib.request, "urlopen", side_effect=AssertionError("must use the same-host opener")):
            self.assertEqual(model_wizard.hf_repo_info("u", "r")["status"], "missing")
            self.assertEqual(model_wizard.hf_check("hf.co/u/r:Q4_K_M")[0], "missing")


class CatalogRefresh(unittest.TestCase):
    def test_refreshed_sizes_and_new_entries(self):
        sizes = {t: s for t, s, _ in model_wizard.CATALOG}
        self.assertEqual(model_wizard.CATALOG_VERIFIED, "2026-11-15")
        self.assertEqual(sizes["gpt-oss:20b"], 14.0)
        self.assertEqual(sizes["qwen3-coder:30b"], 19.0)
        self.assertEqual(sizes["devstral-small-2:24b"], 15.0)
        self.assertEqual(sizes["glm-4.7-flash:q4_K_M"], 19.0)
        self.assertEqual(sizes["qwen3-coder-next:q4_K_M"], 52.0)


if __name__ == "__main__":
    unittest.main()
