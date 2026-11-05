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


def fake_sdk(writes_file, chat_raises=False):
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
                Path(self.workspace, "index.html").write_text("<html></html>", encoding="utf-8")

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
    def go(self, writes_file, chat_raises=False, inputs=("exit",)):
        mods, agent_cls = fake_sdk(writes_file, chat_raises)
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
        self.assertIn("did not create or change", out)

    def test_demo_with_a_file_reports_success(self):
        out, _ = self.go(writes_file=True)
        self.assertIn("Demonstration complete", out)

    def test_shell_stops_after_three_consecutive_errors(self):
        # 10 inputs available; the loop must give up long before using them all.
        out, calls = self.go(writes_file=False, chat_raises=True, inputs=["hi"] * 10)
        self.assertEqual(calls, 1 + run.MAX_SHELL_FAILURES)
        self.assertIn("Stopping after 3 errors", out)


if __name__ == "__main__":
    unittest.main()
