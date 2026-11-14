"""run.py bootstrap fixes: CLI parsing, model matching, pull failure, honest demo, bounded shell loop."""
import asyncio
import contextlib
import io
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import run  # noqa: E402


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
        with mock.patch.object(run, "get_hardware_profile", return_value={"ram_gb": 0.0, "vram_gb": 0.0, "gpu_name": "CPU"}), \
                mock.patch.object(run, "get_installed_ollama_models", return_value=set()), \
                mock.patch.object(run.subprocess, "check_call", side_effect=lambda c: calls.append(c)), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run.select_and_pull_model(), "llama3.2:3b")
        self.assertEqual(calls, [["ollama", "pull", "llama3.2:3b"]])

    def test_score_is_capped_at_100(self):
        self.assertLessEqual(run.get_model_capability_score("nanbeige-72b-coder-agent-instruct"), 100.0)


class ModelWizardInRun(unittest.TestCase):
    """The menu only appears on a real terminal; every other path must behave exactly as before."""
    HW = {"ram_gb": 128.0, "vram_gb": 16.0, "gpu_name": "RTX"}

    def sel(self, installed, answers=(), interactive=True, requested=None, env=None, registry=True, hw=None):
        feed = iter(answers)
        pulls = []

        def no_input(_=""):
            raise AssertionError("the menu must not ask on this path")
        ask = (lambda _="": next(feed)) if interactive else no_input
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(run, "PROJECT_DIR", d), \
                mock.patch.dict(run.os.environ, {"LOCAL_LLM_MODEL": env} if env else {}, clear=False), \
                mock.patch.object(run, "get_hardware_profile", return_value=hw or self.HW), \
                mock.patch.object(run, "get_installed_ollama_models", return_value=set(installed)), \
                mock.patch.object(run.model_wizard, "tag_exists", return_value=registry), \
                mock.patch.object(run.subprocess, "check_call", side_effect=lambda c: pulls.append(c)), \
                mock.patch("builtins.input", side_effect=ask), \
                contextlib.redirect_stdout(io.StringIO()):
            if not env:
                run.os.environ.pop("LOCAL_LLM_MODEL", None)
            got = run.select_and_pull_model(requested_model=requested, interactive=interactive)
            envfile = Path(d, ".env")
            wrote = envfile.read_text(encoding="utf-8") if envfile.exists() else ""
        return got, pulls, wrote

    INSTALLED = {"gemma2:27b", "qwen2.5:14b"}

    def row(self, tag):
        menu = run.model_wizard.build_menu(self.INSTALLED, 16.0, 128.0)
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
                self.assertEqual((got, pulls), (auto, auto_pulls))

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

    def test_yes_flag_parses_and_main_passes_non_interactive(self):
        self.assertTrue(run.parse_args(["--yes"]).yes)
        self.assertTrue(run.parse_args(["-y"]).yes)
        seen = {}
        with mock.patch.object(run, "is_in_venv", return_value=True),                 mock.patch.object(run, "check_ollama_service", return_value=True),                 mock.patch.object(run, "select_and_pull_model", side_effect=lambda *a, **k: seen.update(k) or None),                 contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                run.main(["--yes"])
        self.assertIs(seen["interactive"], False)

    def test_piped_stdin_is_never_interactive(self):
        seen = {}
        with mock.patch.object(run, "is_in_venv", return_value=True),                 mock.patch.object(run, "check_ollama_service", return_value=True),                 mock.patch.object(run.sys, "stdin", io.StringIO("")),                 mock.patch.object(run, "select_and_pull_model", side_effect=lambda *a, **k: seen.update(k) or None),                 contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                run.main([])
        self.assertIs(seen["interactive"], False)

    def test_ranking_prefers_newer_families_but_leaves_the_old_order_alone(self):
        score = run.get_model_capability_score
        self.assertGreater(score("qwen3.6:27b"), score("qwen2.5:14b"))
        self.assertGreater(score("qwen2.5:14b"), score("gemma2:27b"))
        self.assertLessEqual(score("qwen3-coder:30b"), 100.0)


class PullFailure(unittest.TestCase):
    def test_failed_pull_returns_none_and_main_exits_nonzero(self):
        with mock.patch.object(run, "get_hardware_profile", return_value={"ram_gb": 32.0, "vram_gb": 0.0, "gpu_name": "x"}), \
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


if __name__ == "__main__":
    unittest.main()
