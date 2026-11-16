"""run.py bootstrap fixes: CLI parsing, model matching, pull failure, honest demo, bounded shell loop."""
import asyncio
import builtins
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import model_wizard  # noqa: E402
import run  # noqa: E402


os.environ["ANTIGRAVITY_NO_RUN_LOG"] = "1"  # tests must not write into the real logs/ folder


def free_of(hw, disk_free=1000.0, disk_total=2000.0):
    """A fake hardware.free_resources() that says 'everything in hw is free', so no test probes this PC."""
    return {"free_vram_gb": hw["vram_gb"], "gpu_known": hw["vram_gb"] > 0, "free_ram_gb": hw["ram_gb"],
            "free_disk_gb": disk_free, "disk_total_gb": disk_total, "models_dir": "x"}


HF_INFO = {"status": "ok", "gated": False, "license": "apache-2.0"}


class _Tty(io.StringIO):
    """A StringIO that says it is a terminal, so run.main's isatty() checks have something real to read."""
    def isatty(self):
        return True


class Cli(unittest.TestCase):
    def run_py(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "run.py"), *args], cwd=ROOT,
                              capture_output=True, text=True, timeout=60)

    def test_help_exits_zero_without_touching_venv_or_pip(self):
        had_venv = (ROOT / "venv").exists()
        r = self.run_py("--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--serve", r.stdout)
        self.assertNotIn("Virtual Environment", r.stdout)
        self.assertEqual((ROOT / "venv").exists(), had_venv)

    def test_unknown_flag_exits_two(self):
        self.assertEqual(self.run_py("--bogus").returncode, 2)

    def test_known_flags_parse(self):
        a = run.parse_args(["--serve", "--port", "8123", "qwen2.5:7b"])
        self.assertEqual((a.serve, a.port, a.model), (True, 8123, "qwen2.5:7b"))
        self.assertTrue(run.parse_args(["--sync-memory"]).sync_memory)

    def test_serve_gets_port(self):
        fake = types.SimpleNamespace(main=mock.Mock())
        with mock.patch.dict(sys.modules, {"serve": fake}), mock.patch.object(run, "is_in_venv", return_value=True), \
                contextlib.redirect_stdout(io.StringIO()):
            run.main(["--serve", "--port", "9"])
        fake.main.assert_called_once_with(["--port", "9"])


class ModelMatching(unittest.TestCase):
    def test_empty_is_never_installed(self):
        self.assertFalse(run.is_model_installed("", {"qwen2.5:7b", ""}))
        self.assertFalse(run.is_model_installed("   ", {"qwen2.5:7b"}))

    def test_bare_family_and_substrings_do_not_match_other_tags(self):
        self.assertFalse(run.is_model_installed("qwen2.5-coder", {"qwen2.5-coder:14b"}))
        self.assertFalse(run.is_model_installed("qwen2.5:14b", {"qwen2.5:14b-instruct-q4_k_m"}))
        self.assertFalse(run.is_model_installed("qwen", {"qwen2.5:14b"}))

    def test_exact_and_implicit_latest_match(self):
        self.assertTrue(run.is_model_installed("Qwen2.5:14b", {"qwen2.5:14b"}))
        self.assertTrue(run.is_model_installed("llama3", {"llama3:latest"}))
        self.assertTrue(run.is_model_installed("hf.co/u/m:q4", {"m:q4"}))

    def test_inventory_has_no_bare_family_entries(self):
        out = "NAME ID\nqwen2.5-coder:14b abc\n"
        with mock.patch.object(run.urllib.request, "urlopen", side_effect=OSError), \
                mock.patch.object(run.shutil, "which", return_value="ollama"), \
                mock.patch.object(run.subprocess, "check_output", return_value=out):
            self.assertEqual(run.get_installed_ollama_models(), {"qwen2.5-coder:14b"})


class Hardware(unittest.TestCase):
    def test_ram_detection_failure_is_not_invented(self):
        with mock.patch.object(run.subprocess, "check_output", side_effect=OSError), \
                mock.patch("builtins.open", side_effect=OSError):
            self.assertEqual(run.get_system_ram_gb(), 0.0)

    def test_unknown_ram_picks_the_smallest_model(self):
        calls = []
        hw = {"ram_gb": 0.0, "vram_gb": 0.0, "gpu_name": "CPU"}
        with mock.patch.object(run, "get_hardware_profile", return_value=hw), \
                mock.patch.object(run, "get_free_resources", return_value=free_of(hw)), \
                mock.patch.object(run, "get_installed_details", return_value={}), \
                mock.patch.object(run, "get_ledger_entries", return_value=[]), \
                mock.patch.object(run, "get_media_rows", return_value=[]), \
                mock.patch.object(run, "get_installed_ollama_models", return_value=set()), \
                mock.patch.object(run.subprocess, "check_call", side_effect=lambda c: calls.append(c)), \
                mock.patch("builtins.input", side_effect=["", "y"]), \
                contextlib.redirect_stdout(io.StringIO()):
            # Enter at the model menu keeps llama3.2:3b, then "y" answers "Download? [y/N]"
            self.assertEqual(run.select_and_pull_model(interactive=True), "llama3.2:3b")
        self.assertEqual(calls, [["ollama", "pull", "llama3.2:3b"]])

    def test_score_is_capped_at_100(self):
        self.assertLessEqual(run.get_model_capability_score("nanbeige-72b-coder-agent-instruct"), 100.0)


class ModelWizardInRun(unittest.TestCase):
    """The menu only appears on a real terminal; every other path must behave exactly as before."""
    HW = {"ram_gb": 128.0, "vram_gb": 16.0, "gpu_name": "RTX"}

    def sel(self, installed, answers=(), interactive=True, requested=None, env=None, registry=True, hw=None,
            env_text=None, pull_error=None, gate="y", free=None, hf_files=(), details=None, entries=None, media=()):
        """Returns (model, pull commands, final .env text). The printed menu is left in self.printed."""
        feed = iter(answers)
        pulls = []

        def fake_pull(cmd):
            if pull_error:
                raise pull_error
            pulls.append(cmd)
        out = io.StringIO()

        def no_input(_=""):
            raise AssertionError("the menu must not ask on this path")
        self.gate_asked = []

        def interactive_ask(prompt=""):
            if prompt.startswith("Download?"):
                self.gate_asked.append(prompt)
                if isinstance(gate, BaseException):
                    raise gate
                return gate
            return next(feed)
        ask = interactive_ask if interactive else no_input
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(run, "PROJECT_DIR", d), \
                mock.patch.dict(run.os.environ, {"LOCAL_LLM_MODEL": env} if env else {}, clear=False), \
                mock.patch.object(run, "get_hardware_profile", return_value=hw or self.HW), \
                mock.patch.object(run, "get_free_resources", return_value=free or free_of(hw or self.HW)), \
                mock.patch.object(run, "get_installed_details", return_value=details or {}), \
                mock.patch.object(run, "get_ledger_entries", return_value=entries or []), \
                mock.patch.object(run, "get_media_rows", return_value=list(media)), \
                mock.patch.object(run.model_wizard, "hf_repo_info", return_value=HF_INFO), \
                mock.patch.object(run.model_wizard, "hf_tree_files", return_value=list(hf_files)), \
                mock.patch.object(run, "get_installed_ollama_models", return_value=set(installed)), \
                mock.patch.object(run.model_wizard, "tag_exists", return_value=registry), \
                mock.patch.object(run.subprocess, "check_call", side_effect=fake_pull), \
                mock.patch("builtins.input", side_effect=ask), \
                contextlib.redirect_stdout(out):
            if env_text is not None:
                Path(d, ".env").write_text(env_text, encoding="utf-8")
            if not env:
                run.os.environ.pop("LOCAL_LLM_MODEL", None)
            got = run.select_and_pull_model(requested_model=requested, interactive=interactive)
            envfile = Path(d, ".env")
            wrote = envfile.read_text(encoding="utf-8") if envfile.exists() else ""
        self.printed = out.getvalue()
        return got, pulls, wrote

    INSTALLED = {"gemma2:27b", "qwen2.5:14b"}

    def row(self, tag, installed=None):
        menu = run.model_wizard.build_menu(installed or self.INSTALLED, 16.0, 128.0)
        return str([m["tag"] for m in menu].index(tag) + 1)

    def test_not_interactive_is_the_old_automatic_pick_and_never_asks(self):
        got, pulls, _ = self.sel(self.INSTALLED, interactive=False)
        self.assertEqual((got, pulls), ("qwen2.5:14b", []))

    def test_enter_keeps_the_configured_model_without_a_download(self):
        got, pulls, _ = self.sel(self.INSTALLED, [""], env="qwen2.5:14b")
        self.assertEqual((got, pulls), ("qwen2.5:14b", []))

    def test_enter_with_nothing_configured_keeps_the_top_ranked_installed(self):
        got, pulls, _ = self.sel(self.INSTALLED, [""])
        self.assertEqual((got, pulls), ("qwen2.5:14b", []))

    def test_picking_another_installed_model_switches_without_download_and_updates_env(self):
        got, pulls, _ = self.sel(self.INSTALLED, [self.row("gemma2:27b")], env="qwen2.5:14b")
        self.assertEqual((got, pulls), ("gemma2:27b", []))

    def test_picking_a_new_model_pulls_exactly_that_tag(self):
        got, pulls, _ = self.sel(self.INSTALLED, [self.row("devstral-small-2:24b")])
        self.assertEqual(got, "devstral-small-2:24b")
        self.assertEqual(pulls, [["ollama", "pull", "devstral-small-2:24b"]])

    def test_a_newly_downloaded_pick_is_saved_to_env(self):
        got, pulls, wrote = self.sel({"qwen2.5:14b"}, [self.row("devstral-small-2:24b", {"qwen2.5:14b"})],
                                     env_text="LOCAL_LLM_MODEL=qwen2.5:14b\n")
        self.assertEqual((got, len(pulls)), ("devstral-small-2:24b", 1))
        self.assertIn("LOCAL_LLM_MODEL=devstral-small-2:24b", wrote)
        self.assertNotIn("LOCAL_LLM_MODEL=qwen2.5:14b", wrote)

    def test_a_failed_download_leaves_env_alone(self):
        text = "LOCAL_LLM_MODEL=qwen2.5:14b\n"
        got, _, wrote = self.sel({"qwen2.5:14b"}, [self.row("devstral-small-2:24b", {"qwen2.5:14b"})], env_text=text,
                                 pull_error=OSError("boom"))
        self.assertIsNone(got)
        self.assertEqual(wrote, text)

    def test_cli_model_that_needs_a_download_is_saved_to_env_too(self):
        got, pulls, wrote = self.sel({"qwen2.5:14b"}, interactive=True, requested="devstral-small-2:24b",
                                     env_text="LOCAL_LLM_MODEL=qwen2.5:14b\n")
        self.assertEqual((got, len(pulls)), ("devstral-small-2:24b", 1))
        self.assertIn("LOCAL_LLM_MODEL=devstral-small-2:24b", wrote)

    HF = "hf.co/mradermacher/nanbeige4.1-3b-gguf:q4_k_m"

    def sel_hf(self, status, detail=None, **kw):
        with mock.patch.object(run.model_wizard, "hf_check", return_value=(status, detail)) as check:
            got, pulls, wrote = self.sel(self.INSTALLED, [self.HF], **kw)
        return got, pulls, wrote, check

    def test_typed_hf_tag_that_exists_is_pulled_as_typed_and_saved(self):
        got, pulls, wrote, check = self.sel_hf("ok", env_text="LOCAL_LLM_MODEL=qwen2.5:14b\n")
        self.assertEqual((got, pulls), (self.HF, [["ollama", "pull", self.HF]]))
        self.assertIn("LOCAL_LLM_MODEL=" + self.HF, wrote)
        check.assert_called_once_with(self.HF)

    def test_typed_hf_tag_that_is_a_404_is_refused_and_nothing_is_pulled(self):
        got, pulls, _, _ = self.sel_hf("missing")
        self.assertEqual((got, pulls), ("qwen2.5:14b", []))
        self.assertIn("not found on Hugging Face", self.printed)

    def test_typed_hf_tag_while_offline_is_allowed(self):
        got, pulls, _, _ = self.sel_hf("unknown")
        self.assertEqual((got, pulls), (self.HF, [["ollama", "pull", self.HF]]))

    def test_typed_hf_tag_with_a_missing_quant_warns_with_the_quants_that_exist_then_lets_ollama_decide(self):
        got, pulls, _, _ = self.sel_hf("no_quant", ["Q4_K_M", "Q8_0"])
        self.assertEqual(got, self.HF)
        self.assertIn("Quants it has: Q4_K_M, Q8_0", self.printed)

    def test_cli_hf_model_is_vetted_too(self):
        with mock.patch.object(run.model_wizard, "hf_check", return_value=("missing", None)):
            got, pulls, _ = self.sel(self.INSTALLED, interactive=False, requested="hf.co/nobody/nothing:q4_k_m")
        self.assertEqual((got, pulls), (None, []))

    def test_the_ollama_menu_offers_the_hf_row_and_nanbeige(self):
        self.sel(self.INSTALLED, [""], env="qwen2.5:14b")
        self.assertIn("Hugging Face model (type hf.co/user/repo:quant)", self.printed)
        self.assertIn(self.HF, self.printed)

    def test_typed_tag_missing_from_registry_falls_back_without_pulling(self):
        got, pulls, _ = self.sel(self.INSTALLED, ["nanbeige4.1:3b"], registry=False)
        self.assertEqual((got, pulls), ("qwen2.5:14b", []))

    def test_offline_registry_check_does_not_block_a_typed_tag(self):
        got, pulls, _ = self.sel(self.INSTALLED, ["some-new:9b"], registry=None)
        self.assertEqual((got, pulls), ("some-new:9b", [["ollama", "pull", "some-new:9b"]]))

    # R13: this replaces test_empty_machine_enter_pulls_a_model_that_fits_the_gpu (16 GB / 128 GB, expected
    # gpt-oss:20b). That test locked in a menu default that differs from the automatic path and, on smaller
    # PCs, picked a model that does not fit. Enter on an empty machine must equal the automatic hardware pick.
    TIERS = [(16.0, 128.0, "qwen2.5-coder:14b"), (8.0, 32.0, "qwen2.5-coder:14b"),
             (0.0, 32.0, "qwen2.5-coder:7b"), (0.0, 8.0, "llama3.2:3b")]

    def test_empty_machine_enter_pulls_the_hardware_tier_pick_same_as_automatic(self):
        for vram, ram, want in self.TIERS:
            hw = {"ram_gb": ram, "vram_gb": vram, "gpu_name": "x"}
            with self.subTest(vram=vram, ram=ram):
                got, pulls, _ = self.sel(set(), [""], hw=hw)
                auto, auto_pulls, _ = self.sel(set(), interactive=False, hw=hw)
                self.assertEqual((got, pulls), (want, [["ollama", "pull", want]]))
                self.assertEqual((auto, auto_pulls), (None, []))  # --yes / piped: never downloads
                self.assertIn(f"ollama pull {want}", self.printed)

    def test_every_pull_asks_first_even_a_small_one(self):
        got, pulls, _ = self.sel(set(), [""], hw={"ram_gb": 8.0, "vram_gb": 0.0, "gpu_name": "x"})
        self.assertEqual(got, "llama3.2:3b")
        self.assertEqual(len(self.gate_asked), 1)

    def test_only_a_typed_y_downloads(self):
        for answer in ("", "n", "N", "no", "maybe", "yy", " "):
            with self.subTest(answer=answer):
                got, pulls, _ = self.sel(set(), [""], gate=answer)
                self.assertEqual((got, pulls), (None, []))
        for answer in ("y", "Y", "yes", "YES"):
            with self.subTest(answer=answer):
                got, pulls, _ = self.sel(set(), [""], gate=answer)
                self.assertEqual(len(pulls), 1)

    def test_eof_at_the_prompt_downloads_nothing(self):
        got, pulls, _ = self.sel(set(), [""], gate=EOFError())
        self.assertEqual((got, pulls), (None, []))

    def test_ctrl_c_at_the_prompt_stops_and_downloads_nothing(self):
        with self.assertRaises(KeyboardInterrupt):
            self.sel(set(), [""], gate=KeyboardInterrupt())

    def test_full_disk_refuses_before_any_pull(self):
        full = free_of(self.HW, disk_free=20.0, disk_total=1000.0)  # a 9 GB model would leave 11 GB: under 10%
        got, pulls, _ = self.sel(set(), [""], free=full)
        self.assertEqual((got, pulls, self.gate_asked), (None, [], []))
        self.assertIn("Not enough disk", self.printed)

    def test_yes_with_a_cli_model_that_is_not_installed_downloads_nothing(self):
        got, pulls, _ = self.sel({"qwen2.5:14b"}, interactive=False, requested="devstral-small-2:24b")
        self.assertEqual((got, pulls), (None, []))
        self.assertIn("ollama pull devstral-small-2:24b", self.printed)

    def test_typed_hf_repo_gets_the_largest_quant_that_fits_free_vram(self):
        files = [{"name": f"m-{q}.gguf", "size": int(gb * 1e9)}
                 for q, gb in (("Q8_0", 14.1), ("Q6_K", 11.9), ("Q4_K_M", 8.5), ("Q2_K", 5.4))]
        got, pulls, _ = self.sel(set(), [""], hf_files=files, requested="hf.co/u/m",
                                 hw={"ram_gb": 128.0, "vram_gb": 16.0, "gpu_name": "x"}, interactive=True)
        self.assertEqual((got, pulls), ("hf.co/u/m:Q6_K", [["ollama", "pull", "hf.co/u/m:Q6_K"]]))
        self.assertIn("fits 16 GB free VRAM", self.printed)

    def test_typed_hf_repo_where_nothing_fits_downloads_nothing_and_says_why(self):
        files = [{"name": "m-Q4_K_M.gguf", "size": 90_000_000_000}, {"name": "m-Q8_0.gguf", "size": 170_000_000_000}]
        got, pulls, _ = self.sel(set(), [""], hf_files=files, requested="hf.co/u/m", interactive=True,
                                 hw={"ram_gb": 16.0, "vram_gb": 8.0, "gpu_name": "x"})
        self.assertEqual((got, pulls, self.gate_asked), (None, [], []))
        self.assertIn("No quant in u/m fits", self.printed)

    def test_typed_hf_repo_that_does_not_exist_is_refused_before_the_prompt(self):
        missing = {"status": "missing", "gated": False, "license": None}
        with mock.patch.object(run.model_wizard, "hf_repo_info", return_value=missing), \
                mock.patch("builtins.input", side_effect=AssertionError("must not ask for a repo that is not there")), \
                mock.patch.object(run.subprocess, "check_call", side_effect=AssertionError("must not pull")), \
                contextlib.redirect_stdout(io.StringIO()) as shown:
            got = run._pull_with_gate("hf.co/nobody/nothing", True, self.HW, free_of(self.HW))
        self.assertIsNone(got)
        self.assertIn("was not found on Hugging Face", shown.getvalue())

    def test_typed_hf_quant_the_repo_lacks_downloads_nothing(self):
        files = [{"name": "m-Q4_K_M.gguf", "size": 8_500_000_000}]
        got, pulls, _ = self.sel(set(), [""], hf_files=files, requested="hf.co/u/m:Q5_K_S", interactive=True)
        self.assertEqual((got, pulls), (None, []))
        self.assertIn("No Q5_K_S file", self.printed)

    def test_gated_repo_is_skipped_with_its_page(self):
        plan_out = io.StringIO()
        info = {"status": "ok", "gated": True, "license": "llama3"}
        with mock.patch.object(run.model_wizard, "hf_repo_info", return_value=info), \
                mock.patch("builtins.input", side_effect=AssertionError("must not ask for a gated repo")), \
                mock.patch.object(run.subprocess, "check_call", side_effect=AssertionError("must not pull")), \
                contextlib.redirect_stdout(plan_out):
            got = run._pull_with_gate("hf.co/meta/llama", True, self.HW, free_of(self.HW))
        self.assertIsNone(got)
        self.assertIn("https://huggingface.co/meta/llama", plan_out.getvalue())

    def test_empty_machine_menu_shows_the_tier_pick_as_recommended_and_default(self):
        tier = run.hardware_tier_model(0.0, 32.0)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            menu = run.model_wizard.build_menu(set(), 0.0, 32.0, recommended=tier)
            run.model_wizard.choose(menu, tier, input_fn=lambda _="": "")
        text = out.getvalue()
        self.assertIn("qwen2.5-coder:7b", text)
        self.assertIn("recommended for this PC", text)
        self.assertIn("size unknown", text)

    def test_empty_machine_menu_printed_by_run_marks_the_tier_pick(self):
        """Goes through run.select_and_pull_model, so dropping recommended= in run.py fails this."""
        hw = {"ram_gb": 32.0, "vram_gb": 0.0, "gpu_name": "x"}
        import download_size
        download_size.reset_cache()
        with mock.patch.object(download_size, "_get_json", return_value=None):  # offline: no registry answer
            self.sel(set(), [""], hw=hw)
        download_size.reset_cache()
        lines = self.printed.splitlines()
        rows = [ln for ln in lines if "qwen2.5-coder:7b" in ln]
        self.assertTrue(rows, self.printed)
        self.assertIn("recommended for this PC", rows[0])
        self.assertIn("~3.9 GB download (estimate)", rows[0])  # 7b x 4.5 bits: sized, and labelled as an estimate
        self.assertIn("*", rows[0])
        self.assertRegex(rows[0].strip(), r"^\* 1\. qwen2\.5-coder:7b")  # row 1, and it carries the default mark

    def test_hardware_tier_helper_matches_the_old_inline_thresholds(self):
        edge = [(15.0, 0.0, "qwen2.5-coder:14b"), (8.0, 31.9, "qwen2.5-coder:7b"),
                (0.0, 16.0, "qwen2.5-coder:7b"), (0.0, 0.0, "llama3.2:3b")]
        for vram, ram, want in self.TIERS + edge:
            self.assertEqual(run.hardware_tier_model(vram, ram), want, (vram, ram))

    def test_ranking_puts_new_families_above_qwen25_coder_and_small_ones_below(self):
        base = "qwen2.5-coder:14b"
        above = ["qwen3.6:27b", "qwen3.8:27b", "gpt-oss:20b", "devstral-small-2:24b",
                 "qwen3-coder:30b", "laguna-xs.2:latest"]
        below = ["qwen3:8b", "qwen3:4b", "qwen3:0.6b"]
        ranked = sorted([base] + above + below, key=run.capability_rank_key, reverse=True)
        self.assertEqual(set(ranked[:len(above)]), set(above))
        self.assertEqual(ranked[len(above)], base)
        for name in above + below + [base]:
            self.assertLessEqual(run.get_model_capability_score(name), 100.0, name)

    def test_embedding_and_reranker_models_never_outrank_a_chat_model(self):
        chat = run.capability_rank_key("qwen2.5-coder:7b")
        for name in ("qwen3-embedding:8b", "qwen3-reranker:4b", "nomic-embed-text:latest", "bge-m3:latest"):
            self.assertLess(run.capability_rank_key(name), chat, name)
        got, pulls, _ = self.sel({"qwen3-embedding:8b", "qwen2.5-coder:7b"}, interactive=False)
        self.assertEqual((got, pulls), ("qwen2.5-coder:7b", []))

    def test_automatic_pick_prefers_a_new_family_over_qwen25_coder(self):
        got, pulls, _ = self.sel({"qwen2.5-coder:14b", "qwen3.6:27b"}, interactive=False)
        self.assertEqual((got, pulls), ("qwen3.6:27b", []))

    def test_menu_default_is_the_new_family_when_both_are_installed(self):
        got, pulls, _ = self.sel({"qwen2.5-coder:14b", "qwen3.6:27b"}, [""])
        self.assertEqual((got, pulls), ("qwen3.6:27b", []))

    def test_explicit_cli_model_skips_the_menu(self):
        got, pulls, _ = self.sel(self.INSTALLED, interactive=False, requested="gemma2:27b")
        self.assertEqual((got, pulls), ("gemma2:27b", []))
        got, pulls, _ = self.sel(self.INSTALLED, requested="gemma2:27b", interactive=False)
        self.assertEqual(got, "gemma2:27b")

    def interactive_seen(self, argv, stdin, stdout):
        """What run.main hands select_and_pull_model as interactive=, given these stdin/stdout."""
        seen = {}
        with mock.patch.object(run, "is_in_venv", return_value=True), \
                mock.patch.object(run, "check_ollama_service", return_value=True), \
                mock.patch.object(run.sys, "stdin", stdin), \
                mock.patch.object(run.sys, "stdout", stdout), \
                mock.patch.object(run, "select_and_pull_model", side_effect=lambda *a, **k: seen.update(k) or None):
            with self.assertRaises(SystemExit):
                run.main(argv)
        return seen["interactive"]

    def test_two_terminals_and_no_flag_is_interactive(self):
        self.assertIs(self.interactive_seen([], _Tty(), _Tty()), True)

    def test_yes_flag_parses_and_main_passes_non_interactive(self):
        self.assertTrue(run.parse_args(["--yes"]).yes)
        self.assertTrue(run.parse_args(["-y"]).yes)
        self.assertIs(self.interactive_seen(["--yes"], _Tty(), _Tty()), False)

    def test_piped_stdin_is_never_interactive(self):
        self.assertIs(self.interactive_seen([], io.StringIO(""), _Tty()), False)

    def test_ctrl_c_at_the_menu_cancels_with_130_and_downloads_nothing(self):
        def ctrl_c(_=""):
            raise KeyboardInterrupt
        pulls = []
        out = _Tty()
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(run, "PROJECT_DIR", d), \
                mock.patch.object(run, "is_in_venv", return_value=True), \
                mock.patch.object(run, "check_ollama_service", return_value=True), \
                mock.patch.object(run, "get_hardware_profile", return_value={"ram_gb": 32.0, "vram_gb": 0.0, "gpu_name": "x"}), \
                mock.patch.object(run, "get_free_resources", return_value=free_of({"ram_gb": 32.0, "vram_gb": 0.0})), \
                mock.patch.object(run, "get_installed_details", return_value={}), \
                mock.patch.object(run, "get_ledger_entries", return_value=[]), \
                mock.patch.object(run, "get_media_rows", return_value=[]), \
                mock.patch.object(run, "get_installed_ollama_models", return_value=set()), \
                mock.patch.object(run.model_wizard, "tag_exists", return_value=True), \
                mock.patch.object(run.subprocess, "check_call", side_effect=lambda c: pulls.append(c)), \
                mock.patch.object(run.sys, "stdin", _Tty()), \
                mock.patch.object(run.sys, "stdout", out), \
                mock.patch("builtins.input", side_effect=ctrl_c):
            with self.assertRaises(SystemExit) as cm:
                run.main([])
        self.assertEqual(cm.exception.code, 130)
        self.assertEqual(pulls, [])
        self.assertIn("Cancelled", out.getvalue())

    def test_ranking_prefers_newer_families_but_leaves_the_old_order_alone(self):
        score = run.get_model_capability_score
        self.assertGreater(score("qwen3.6:27b"), score("qwen2.5:14b"))
        self.assertGreater(score("qwen2.5:14b"), score("gemma2:27b"))
        self.assertLessEqual(score("qwen3-coder:30b"), 100.0)


class _Server:
    """Pretend HTTP for urlopen: URLs in `routes` (url -> body text) answer 200, everything else is refused."""
    def __init__(self, routes):
        self.routes, self.seen = routes, []

    def __call__(self, url, timeout=None):
        u = url if isinstance(url, str) else url.full_url
        self.seen.append(u)
        if u in self.routes:
            resp = mock.MagicMock()
            resp.status = 200
            resp.read.return_value = self.routes[u].encode("utf-8")
            resp.__enter__.return_value = resp
            return resp
        raise urllib.error.URLError("refused")


LM = "http://localhost:1234/v1"
LM_MODELS = json.dumps({"data": [{"id": "qwen2.5-coder-7b-instruct"}, {"id": "gemma-2-27b"}]})
OLLAMA_TAGS = "http://localhost:11434/api/tags"


class AnyBackend(unittest.TestCase):
    """run.py works with Ollama, or any OpenAI-compatible server (LM Studio, llama.cpp, vLLM) with no download."""

    def detect(self, base, routes):
        with mock.patch.object(run.urllib.request, "urlopen", _Server(routes)):
            return run.detect_backend(base)

    def test_ollama_answering_wins_even_though_it_also_serves_v1_models(self):
        both = {OLLAMA_TAGS: "{}", "http://localhost:11434/v1/models": LM_MODELS}
        self.assertEqual(self.detect("http://localhost:11434/v1", both), "ollama")

    def test_only_v1_models_answering_is_an_openai_compatible_server(self):
        self.assertEqual(self.detect(LM, {LM + "/models": LM_MODELS}), "openai")

    def test_a_base_url_without_v1_still_finds_the_models_list(self):
        self.assertEqual(self.detect("http://localhost:8080", {"http://localhost:8080/v1/models": LM_MODELS}), "openai")

    def test_nothing_answering_is_none(self):
        self.assertIsNone(self.detect(LM, {}))

    def test_a_models_reply_without_a_data_list_is_not_an_openai_server(self):
        self.assertIsNone(self.detect(LM, {LM + "/models": json.dumps({"error": "nope"})}))
        self.assertIsNone(self.detect(LM, {LM + "/models": "<html>not json</html>"}))

    def test_only_the_default_address_counts_as_the_default_ollama_url(self):
        self.assertTrue(run.is_default_ollama_url("http://localhost:11434/v1"))
        self.assertTrue(run.is_default_ollama_url("http://127.0.0.1:11434"))
        self.assertFalse(run.is_default_ollama_url(LM))

    def test_list_openai_models_returns_the_ids(self):
        with mock.patch.object(run.urllib.request, "urlopen", _Server({LM + "/models": LM_MODELS})):
            self.assertEqual(run.list_openai_models(LM), ["qwen2.5-coder-7b-instruct", "gemma-2-27b"])

    def main_with(self, base, routes, argv=("--yes",), env_extra=None, **patches):
        """run.main against pretend servers. Returns (exit code or None, printed text, what run_agent got)."""
        boom = AssertionError("Ollama must not be touched on an OpenAI-compatible server")
        ran, out = {}, io.StringIO()

        async def fake_agent(model, base_url):
            ran.update(model=model, base=base_url, backend=run.os.environ.get("LOCAL_LLM_BACKEND"))
        env = {"LOCAL_LLM_BASE_URL": base} if base else {}
        env.update(env_extra or {})
        code = None
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(run.os.environ, env), \
                mock.patch.object(run, "PROJECT_DIR", d), mock.patch.object(run, "is_in_venv", return_value=True), \
                mock.patch.object(run.urllib.request, "urlopen", _Server(routes)), \
                mock.patch.object(run, "check_or_update_memory"), mock.patch.object(run, "run_agent", fake_agent), \
                mock.patch.object(run.sys, "stdin", io.StringIO("")), contextlib.redirect_stdout(out):
            if not base:
                run.os.environ.pop("LOCAL_LLM_BASE_URL", None)
            for name, value in patches.items():
                value = value if value is not None else boom
                mock.patch.object(run, name, **({"side_effect": value} if isinstance(value, BaseException) else {"new": value})).start()
            try:
                run.main(list(argv))
            except SystemExit as e:
                code = e.code
            finally:
                mock.patch.stopall()
        return code, out.getvalue(), ran

    def test_openai_server_runs_without_touching_ollama_and_downloads_nothing(self):
        boom = AssertionError("Ollama must not be touched on an OpenAI-compatible server")
        with mock.patch.object(run.subprocess, "check_call") as pull, mock.patch.object(run.subprocess, "Popen") as start, \
                mock.patch.object(run.shutil, "which") as find, mock.patch.object(run, "get_hardware_profile") as hw:
            code, text, ran = self.main_with(LM, {LM + "/models": LM_MODELS}, check_ollama_service=boom)
        for call in (pull, start, find, hw):  # no `ollama pull`, no `ollama serve`, no PATH hunt, no hardware probe
            call.assert_not_called()
        self.assertIsNone(code, text)
        self.assertEqual((ran["model"], ran["base"], ran["backend"]), ("qwen2.5-coder-7b-instruct", LM, "openai"))
        self.assertIn(f"Found an OpenAI-compatible server at {LM}", text)

    def test_openai_server_with_no_model_loaded_says_so_and_exits_1(self):
        code, text, ran = self.main_with(LM, {LM + "/models": json.dumps({"data": []})})
        self.assertEqual(code, 1)
        self.assertIn("Load a model in your server, then re-run", text)
        self.assertEqual(ran, {})

    def test_requested_model_the_server_does_not_have_exits_1_instead_of_downloading(self):
        boom = AssertionError("never download")
        with mock.patch.object(run.subprocess, "check_call", side_effect=boom):
            code, text, _ = self.main_with(LM, {LM + "/models": LM_MODELS}, argv=("--yes", "llama3:8b"))
        self.assertEqual(code, 1)
        self.assertIn("is not loaded on this server", text)

    def test_unreachable_custom_url_exits_1_naming_the_url_and_never_starts_ollama(self):
        code, text, _ = self.main_with("http://localhost:9999/v1", {}, check_ollama_service=None)
        self.assertEqual(code, 1)
        self.assertIn("http://localhost:9999/v1", text)

    def test_default_url_with_nothing_running_still_goes_through_the_ollama_start_path(self):
        called = []
        code, text, ran = self.main_with(None, {}, check_ollama_service=lambda host: called.append(host) or True,
                                         select_and_pull_model=lambda *a, **k: "qwen2.5:14b")
        self.assertEqual(called, ["http://localhost:11434"])
        self.assertIsNone(code, text)
        self.assertEqual((ran["model"], ran["backend"]), ("qwen2.5:14b", None))

    def test_a_stale_openai_marker_does_not_leak_into_an_ollama_run(self):
        code, text, ran = self.main_with(None, {OLLAMA_TAGS: "{}"}, env_extra={"LOCAL_LLM_BACKEND": "openai"},
                                         check_ollama_service=lambda host: True,
                                         select_and_pull_model=lambda *a, **k: "qwen2.5:14b")
        self.assertIsNone(ran["backend"])

    def pick(self, ids, requested=None, interactive=False, answers=(), env=None, env_text=None):
        feed, out = iter(answers), io.StringIO()
        body = json.dumps({"data": [{"id": i} for i in ids]})
        with tempfile.TemporaryDirectory() as d, mock.patch.object(run, "PROJECT_DIR", d), \
                mock.patch.dict(run.os.environ, {"LOCAL_LLM_MODEL": env} if env else {}), \
                mock.patch.object(run.urllib.request, "urlopen", _Server({LM + "/models": body})), \
                mock.patch("builtins.input", side_effect=lambda _="": next(feed)), contextlib.redirect_stdout(out):
            if not env:
                run.os.environ.pop("LOCAL_LLM_MODEL", None)
            if env_text is not None:
                Path(d, ".env").write_text(env_text, encoding="utf-8")
            got = run.select_openai_model(LM, requested, interactive=interactive)
            envfile = Path(d, ".env")
            wrote = envfile.read_text(encoding="utf-8") if envfile.exists() else ""
        self.printed = out.getvalue()
        return got, wrote

    IDS = ["gemma-2-27b", "qwen2.5-coder-7b-instruct"]

    def test_picks_the_top_ranked_loaded_model_when_nothing_is_configured(self):
        self.assertEqual(self.pick(self.IDS)[0], "qwen2.5-coder-7b-instruct")

    def test_configured_model_wins_when_the_server_lists_it_and_is_ignored_when_it_does_not(self):
        self.assertEqual(self.pick(self.IDS, env="gemma-2-27b")[0], "gemma-2-27b")
        self.assertEqual(self.pick(self.IDS, env="not-loaded")[0], "qwen2.5-coder-7b-instruct")

    def test_requested_model_matches_case_insensitively_and_the_servers_spelling_is_used(self):
        self.assertEqual(self.pick(["Qwen2.5-Coder-7B"], requested="qwen2.5-coder-7b")[0], "Qwen2.5-Coder-7B")

    def test_the_pick_is_saved_to_env(self):
        _, wrote = self.pick(self.IDS, env_text="LOCAL_LLM_MODEL=old\n")
        self.assertIn("LOCAL_LLM_MODEL=qwen2.5-coder-7b-instruct", wrote)

    def test_interactive_menu_lists_only_what_the_server_has(self):
        got, _ = self.pick(self.IDS, interactive=True, answers=["1"])
        self.assertEqual(got, "gemma-2-27b")
        for gone in ("Hugging Face", "GB download", "Ollama tag", "nanbeige"):
            self.assertNotIn(gone, self.printed)
        self.assertIn("loaded, no download", self.printed)

    def test_interactive_typed_id_the_server_does_not_have_keeps_the_default(self):
        got, _ = self.pick(self.IDS, interactive=True, answers=["hf.co/user/repo:q4_k_m"])
        self.assertEqual(got, "qwen2.5-coder-7b-instruct")
        self.assertIn("is not loaded on this server", self.printed)


class PullFailure(unittest.TestCase):
    def test_failed_pull_returns_none_and_main_exits_nonzero(self):
        with mock.patch.object(run, "get_hardware_profile", return_value={"ram_gb": 32.0, "vram_gb": 0.0, "gpu_name": "x"}), \
                mock.patch.object(run, "get_free_resources", return_value=free_of({"ram_gb": 32.0, "vram_gb": 0.0})), \
                mock.patch.object(run, "get_installed_details", return_value={}), \
                mock.patch.object(run, "get_ledger_entries", return_value=[]), \
                mock.patch.object(run, "get_media_rows", return_value=[]), \
                mock.patch.object(run, "get_installed_ollama_models", return_value=set()), \
                mock.patch.object(run.subprocess, "check_call", side_effect=OSError("boom")), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(run.select_and_pull_model())
        with mock.patch.object(run, "is_in_venv", return_value=True), \
                mock.patch.object(run, "check_ollama_service", return_value=True), \
                mock.patch.object(run, "select_and_pull_model", return_value=None), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                run.main([])
        self.assertEqual(cm.exception.code, 1)


DARK_PAGE = "<html><body><button id='t'>dark mode</button><script>classList.toggle('dark-mode')</script></body></html>"


def fake_sdk(writes_file, chat_raises=False, content=DARK_PAGE):
    class FakeAgent:
        n = 0

        def __init__(self, config):
            self.workspace = config.workspaces[0]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def chat(self, prompt):
            FakeAgent.n += 1
            if chat_raises and FakeAgent.n > 1:  # call 1 is the demo
                raise RuntimeError("backend down")
            if writes_file:
                Path(self.workspace, "index.html").write_text(content, encoding="utf-8")

            async def gen():
                yield "ok"
            return gen()

    class Cfg:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    mods = {k: types.ModuleType(k) for k in
            ["google", "google.antigravity", "google.antigravity.hooks", "google.antigravity.types"]}
    mods["google.antigravity"].Agent = FakeAgent
    mods["google.antigravity"].LocalOpenAIAgentConfig = Cfg
    mods["google.antigravity.hooks"].policy = types.SimpleNamespace(allow_all=lambda: None)
    mods["google.antigravity.types"].CapabilitiesConfig = Cfg
    return mods, FakeAgent


class RunAgent(unittest.TestCase):
    def setUp(self):
        # main() sets run._SETUP_ONLY for no-terminal runs and never resets it; keep other tests on the shell path.
        saved = run._SETUP_ONLY
        run._SETUP_ONLY = False
        self.addCleanup(setattr, run, "_SETUP_ONLY", saved)
        # A small context window would ask a question first; these tests feed the chat its answers.
        env = mock.patch.dict(run.os.environ, {"OLLAMA_CONTEXT_LENGTH": "65536"})
        env.start()
        self.addCleanup(env.stop)

    def go(self, writes_file, chat_raises=False, inputs=("exit",), content=DARK_PAGE):
        mods, agent_cls = fake_sdk(writes_file, chat_raises, content)
        feed = iter(inputs)
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(sys.modules, mods), \
                mock.patch.object(run, "PROJECT_DIR", d), \
                mock.patch("builtins.input", side_effect=lambda _="": next(feed)):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                asyncio.run(run.run_agent("m"))
        return buf.getvalue(), agent_cls.n

    def test_demo_without_a_file_warns_instead_of_claiming_success(self):
        out, _ = self.go(writes_file=False)
        self.assertNotIn("Demonstration complete", out)
        self.assertIn("did not write a dark-mode page", out)

    def test_demo_with_a_file_reports_success(self):
        out, _ = self.go(writes_file=True)
        self.assertIn("Demonstration complete", out)

    def test_demo_with_unrelated_html_does_not_claim_success(self):
        # A file that changed but has no dark-mode toggle is not what the demo asked for.
        out, _ = self.go(writes_file=True, content="<html><body>Antigravity Lab</body></html>")
        self.assertNotIn("Demonstration complete", out)

    def test_demo_sets_a_stale_index_aside_so_create_can_succeed(self):
        # The SDK refuses to create over an existing file; a leftover from the last run caused that.
        mods, _ = fake_sdk(writes_file=False)
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(sys.modules, mods), \
                mock.patch.object(run, "PROJECT_DIR", d), \
                mock.patch("builtins.input", side_effect=lambda _="": "exit"):
            ws = Path(d, "workspace")
            ws.mkdir(exist_ok=True)
            (ws / "index.html").write_text("old run", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                asyncio.run(run.run_agent("m"))
            self.assertFalse((ws / "index.html").exists())
            self.assertEqual((ws / "index.html.prev").read_text(encoding="utf-8"), "old run")

    def test_shell_stops_after_three_consecutive_errors(self):
        # 10 inputs available; the loop must give up long before using them all.
        out, calls = self.go(writes_file=False, chat_raises=True, inputs=["hi"] * 10)
        self.assertEqual(calls, 1 + run.MAX_SHELL_FAILURES)
        self.assertIn("Stopping after 3 errors", out)

    def test_setup_only_prints_ready_and_never_builds_the_agent(self):
        # --yes, piped input and CI have no terminal: stop after setup instead of starting the demo.
        mods, _ = fake_sdk(writes_file=True)
        agent_built = mock.Mock(side_effect=AssertionError("agent built in setup-only mode"))
        mods["google.antigravity"].Agent = agent_built
        saved = run._SETUP_ONLY
        run._SETUP_ONLY = True
        try:
            buf = io.StringIO()
            with mock.patch.dict(sys.modules, mods), \
                    mock.patch("builtins.input", side_effect=AssertionError("no prompt in setup-only")), \
                    contextlib.redirect_stdout(buf):
                asyncio.run(run.run_agent("m"))
        finally:
            run._SETUP_ONLY = saved
        self.assertIn("Ready: m at http://localhost:11434/v1. Run python run.py in a terminal to chat.", buf.getvalue())
        self.assertNotIn("Launching", buf.getvalue())
        agent_built.assert_not_called()


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

    def offer(self, answer=None, now=None, installed=("llama3.2:3b",)):
        ask = (mock.MagicMock(return_value=answer) if answer is not None
               else mock.MagicMock(side_effect=AssertionError("must not prompt")))
        with mock.patch.object(builtins, "input", ask), \
                contextlib.redirect_stdout(io.StringIO()):
            tag = run.offer_upgrade(set(installed), HW, 24.0, 64.0, now=self.now if now is None else now)
        return tag, ask

    def test_enter_stays_and_never_returns_a_pull(self):
        tag, ask = self.offer(answer="")
        self.assertIsNone(tag)
        self.assertEqual(ask.call_count, 1)
        with open(self.state, encoding="utf-8") as f:
            self.assertAlmostEqual(json.load(f)["stay_until"]["llama3.2:3b"], self.now + 7 * DAY)

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

    def test_a_stay_on_one_model_still_offers_when_another_model_is_current(self):
        self.offer(answer="")  # stay on llama3.2:3b
        _, ask = self.offer(answer="", installed=("tinyllama:1b",))
        self.assertEqual(ask.call_count, 1)
        with open(self.state, encoding="utf-8") as f:
            self.assertIn("llama3.2:3b", json.load(f)["stay_until"])

    def test_an_old_bare_number_state_file_is_no_stay_and_does_not_crash(self):
        with open(self.state, "w", encoding="utf-8") as f:
            json.dump({"stay_until": self.now + 7 * DAY}, f)
        tag, ask = self.offer(answer="")
        self.assertIsNone(tag)
        self.assertEqual(ask.call_count, 1)
        with open(self.state, encoding="utf-8") as f:
            self.assertEqual(list(json.load(f)["stay_until"]), ["llama3.2:3b"])

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


class SharedMemory(unittest.TestCase):
    def test_pi_hand_off_indexes_memory_before_the_agent_starts(self):
        import agent_setup
        order = []
        with tempfile.TemporaryDirectory() as d,                 mock.patch.object(run, "PROJECT_DIR", d),                 mock.patch.object(run, "is_in_venv", return_value=True),                 mock.patch.object(run, "check_ollama_service", return_value=True),                 mock.patch.object(run, "detect_backend", return_value="ollama"),                 mock.patch.object(run, "select_and_pull_model", return_value="m"),                 mock.patch.object(run, "check_or_update_memory", side_effect=lambda: order.append("index")),                 mock.patch.object(agent_setup, "run", side_effect=lambda *a, **k: order.append("agent") or 0),                 contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                run.main(["--agent", "pi", "--yes"])
        self.assertEqual(order, ["index", "agent"])

    def test_a_raising_indexer_prints_the_skip_line(self):
        fake = types.SimpleNamespace(MemoryDatabase=mock.Mock(side_effect=RuntimeError("no sqlite")),
                                     EmbeddingProvider=mock.Mock(), MemoryIndexer=mock.Mock())
        buf = io.StringIO()
        with mock.patch.dict(sys.modules, {"memory": fake}), contextlib.redirect_stdout(buf):
            run.check_or_update_memory()  # must not raise
        self.assertIn("Memory index skipped: no sqlite", buf.getvalue())

    def test_a_failed_env_write_prints_one_line_and_does_not_raise(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, ".env").write_text("LOCAL_LLM_MODEL=old\n", encoding="utf-8")
            buf = io.StringIO()
            with mock.patch.object(run, "PROJECT_DIR", d),                     mock.patch("builtins.open", side_effect=PermissionError("locked")),                     contextlib.redirect_stdout(buf):
                run.update_env_model("new")  # must not raise
        self.assertIn("Couldn't update .env: locked", buf.getvalue())

    def test_hand_off_prompt_has_project_memory_and_stays_small(self):
        import agent_setup
        prompt = agent_setup.CONTINUE_PROMPT
        self.assertIn("Project memory", prompt)
        self.assertIn("memory.py search", prompt)
        self.assertLess(len(prompt), 6000)


class StageWizard(unittest.TestCase):
    def test_stage_banner_has_number_name_and_next_line(self):
        buf = io.StringIO()
        with mock.patch.dict(run.os.environ, {}, clear=False), contextlib.redirect_stdout(buf):
            run.stage(2, 4, "SERVER", "make sure Ollama is answering")
        out = buf.getvalue()
        self.assertIn("STAGE 2/4  SERVER", out)
        self.assertIn("next: make sure Ollama is answering", out)

    def test_no_colour_or_block_art_when_no_color_is_set(self):
        buf = io.StringIO()
        with mock.patch.dict(run.os.environ, {"NO_COLOR": "1"}), contextlib.redirect_stdout(buf):
            run.stage(1, 4, "ENVIRONMENT", "x")
        out = buf.getvalue()
        self.assertIn("STAGE 1/4  ENVIRONMENT", out)
        self.assertNotIn("[", out)
        self.assertNotIn("█", out)
        out.encode("ascii")  # plain output is ASCII only

    def test_a_cp1252_console_does_not_raise(self):
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp1252", write_through=True)
        with contextlib.redirect_stdout(stream):
            run._safe_print("✅ Model pulled")  # a check mark cp1252 cannot encode
            run.stage(3, 4, "MODEL", "pick a model")
        stream.flush()
        self.assertIn(b"Model pulled", raw.getvalue())

    def test_level_clear_names_model_agent_and_log_and_keeps_the_ready_line(self):
        ready = "Ready: m at http://x/v1. Run python run.py in a terminal to chat."
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run.level_clear("m", "built-in shell", ready=ready)
        out = buf.getvalue()
        self.assertIn("LEVEL CLEAR", out)
        self.assertIn("built-in shell", out)
        self.assertIn("logs", out)
        self.assertIn(ready, out)

    def test_yes_run_never_builds_the_agent_and_prints_ready_inside_the_summary(self):
        fake_agent = mock.Mock(side_effect=AssertionError("agent built on a --yes run"))
        mods, _ = fake_sdk(writes_file=True)
        mods["google.antigravity"].Agent = fake_agent
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(sys.modules, mods), \
                mock.patch.object(run, "PROJECT_DIR", d), \
                mock.patch.object(run, "is_in_venv", return_value=True), \
                mock.patch.object(run, "check_ollama_service", return_value=True), \
                mock.patch.object(run, "detect_backend", return_value="ollama"), \
                mock.patch.object(run, "select_and_pull_model", return_value="m"), \
                mock.patch.object(run, "check_or_update_memory"), \
                mock.patch.object(run.sys, "stdin", io.StringIO("")), \
                contextlib.redirect_stdout(out):
            run.main(["--yes"])
        text = out.getvalue()
        self.assertIn("Ready: m at", text)
        self.assertIn("LEVEL CLEAR", text)
        fake_agent.assert_not_called()


class WizardD2(unittest.TestCase):
    def yes_run(self, argv, agent=None):
        """main() on a no-terminal run with the server and network stubbed. Returns the printed text."""
        fake_agent = mock.Mock(side_effect=AssertionError("agent built on a --yes run"))
        mods, _ = fake_sdk(writes_file=True)
        mods["google.antigravity"].Agent = fake_agent
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(sys.modules, mods), \
                mock.patch.object(run, "PROJECT_DIR", d), \
                mock.patch.object(run, "is_in_venv", return_value=True), \
                mock.patch.object(run, "check_ollama_service", return_value=True), \
                mock.patch.object(run, "detect_backend", return_value="ollama"), \
                mock.patch.object(run, "select_and_pull_model", return_value="m"), \
                mock.patch.object(run, "check_or_update_memory"), \
                mock.patch.dict(run.os.environ, {}, clear=False), \
                mock.patch.object(run.sys, "stdin", io.StringIO("")), \
                contextlib.redirect_stdout(out):
            run.main(argv)
        self.fake_agent = fake_agent
        return out.getvalue()

    def test_stage_banner_is_flushed_so_the_venv_child_cannot_jump_ahead(self):
        with mock.patch("builtins.print") as printed:
            run.stage(1, 5, "ENVIRONMENT", "x")
        self.assertTrue(printed.call_args_list)
        for call in printed.call_args_list:
            self.assertTrue(call.kwargs.get("flush"), call)

    def test_context_unset_and_interactive_asks_then_y_prints_the_powershell_line(self):
        asked, out = [], []
        with mock.patch.dict(run.os.environ, {}, clear=True), mock.patch.object(run.sys, "platform", "win32"):
            run.context_check(True, ask=lambda p: asked.append(p) or "y", out=out.append)
        self.assertTrue(asked)
        self.assertIn("OLLAMA_CONTEXT_LENGTH is not set", "\n".join(out))
        self.assertIn("$env:OLLAMA_CONTEXT_LENGTH=65536; ollama serve", "\n".join(out))

    def test_context_on_a_yes_run_prints_one_line_and_asks_nothing(self):
        out = []
        def no_question(prompt):
            raise AssertionError("asked a question on a --yes run")
        with mock.patch.dict(run.os.environ, {}, clear=True):
            run.context_check(False, ask=no_question, out=out.append)
        self.assertEqual(len(out), 1)
        self.assertIn("OLLAMA_CONTEXT_LENGTH is not set", out[0])

    def test_context_is_skipped_for_an_openai_compatible_server(self):
        out = []
        env = {"LOCAL_LLM_BACKEND": "openai"}  # LM Studio, llama.cpp, vLLM: OLLAMA_CONTEXT_LENGTH does not apply
        with mock.patch.dict(run.os.environ, env, clear=True):
            run.context_check(True, ask=lambda p: self.fail("asked on an openai server"), out=out.append)
        self.assertEqual(out, [])

    def test_context_at_or_above_65536_prints_nothing(self):
        out = []
        with mock.patch.dict(run.os.environ, {"OLLAMA_CONTEXT_LENGTH": "65536"}, clear=True):
            run.context_check(True, ask=lambda p: "y", out=out.append)
        self.assertEqual(out, [])

    def test_plain_flag_gives_hash_bars_not_block_characters(self):
        text = self.yes_run(["--plain", "--yes"])
        self.assertIn("STAGE 5/5  LAUNCH", text)
        self.assertIn("#", text)
        self.assertNotIn("\u2588", text)
        self.fake_agent.assert_not_called()

    def test_yes_run_prints_ready_inside_level_clear_and_never_builds_the_agent(self):
        text = self.yes_run(["--yes"])
        self.assertLess(text.index("LEVEL CLEAR"), text.index("Ready: m at"))
        self.fake_agent.assert_not_called()

    def test_level_clear_is_printed_before_the_agent_hand_off(self):
        order = []
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(run, "PROJECT_DIR", d), \
                mock.patch.object(run, "is_in_venv", return_value=True), \
                mock.patch.object(run, "check_ollama_service", return_value=True), \
                mock.patch.object(run, "detect_backend", return_value="ollama"), \
                mock.patch.object(run, "select_and_pull_model", return_value="m"), \
                mock.patch.object(run, "check_or_update_memory", side_effect=lambda: order.append("index")), \
                mock.patch.object(run, "level_clear", side_effect=lambda *a, **k: order.append("box")), \
                mock.patch.object(run.sys, "stdin", io.StringIO("")), \
                contextlib.redirect_stdout(io.StringIO()):
            import agent_setup
            with mock.patch.object(agent_setup, "run", side_effect=lambda *a, **k: order.append("agent") or 0):
                with self.assertRaises(SystemExit):
                    run.main(["--agent", "pi", "--yes"])
        self.assertEqual(order, ["index", "box", "agent"])


if __name__ == "__main__":
    unittest.main()
