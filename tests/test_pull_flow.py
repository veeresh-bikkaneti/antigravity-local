"""The download gate, end to end through run.main: --yes and piped input never download, the run log is written,
and the Ollama server we start listens on this PC only. Everything is faked: no real pull, server or disk."""
import contextlib
import io
import os
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import run  # noqa: E402
import agl.app.agent  # noqa: E402
import agl.app.bootstrap  # noqa: E402
import agl.app.probe  # noqa: E402
import agl.app.server  # noqa: E402
from agl.platform import process  # noqa: E402
from test_run import OLLAMA_TAGS, _Server, _Tty, free_of  # noqa: E402

run.check_ollama_service = lambda base_url="http://localhost:11434": agl.app.server.check_ollama_service(
    base_url, ports=run._PickPorts(), out=run._out
)

HW = {"ram_gb": 128.0, "vram_gb": 16.0, "gpu_name": "RTX"}


class NeverDownloads(unittest.TestCase):
    def main_with(self, argv, stdin, installed=(), env=None, tty_out=False):
        """run.main with a pretend Ollama and no models. Returns (exit code, printed text, pull calls, project dir files)."""
        out, pulls = (_Tty() if tty_out else io.StringIO()), []
        code = None
        with tempfile.TemporaryDirectory() as d:
            patches = [
                mock.patch.dict(run.os.environ, env or {}),
                mock.patch.object(run, "PROJECT_DIR", d),
                mock.patch.object(agl.app.bootstrap, "is_in_venv", return_value=True),
                mock.patch.object(urllib.request, "urlopen", _Server({OLLAMA_TAGS: "{}"})),
                mock.patch.object(agl.app.server, "check_ollama_service", return_value=True),
                mock.patch.object(run, "get_hardware_profile", return_value=HW),
                mock.patch.object(run, "get_free_resources", return_value=free_of(HW)),
                mock.patch.object(run, "get_installed_details", return_value={}),
                mock.patch.object(run, "get_ledger_entries", return_value=[]),
                mock.patch.object(run, "get_media_rows", return_value=[]),
                mock.patch.object(run, "get_installed_ollama_models", return_value=set(installed)),
                mock.patch.object(process.subprocess, "check_call", side_effect=lambda c: pulls.append(c)),
                mock.patch.object(agl.app.probe, "check_or_update_memory"),
                mock.patch.object(agl.app.agent, "run_agent"),
                mock.patch.object(run.sys, "stdin", stdin),
                mock.patch.object(run.sys, "stdout", out),
            ]
            with contextlib.ExitStack() as stack:
                for p in patches:
                    stack.enter_context(p)
                run.os.environ.pop("LOCAL_LLM_BASE_URL", None)
                try:
                    run.main(list(argv))
                except SystemExit as e:
                    code = e.code
            logs = sorted(Path(d, "logs").glob("run-*.log")) if Path(d, "logs").exists() else []
            log_text = logs[0].read_text(encoding="utf-8") if logs else None
        return code, out.getvalue(), pulls, log_text

    def test_yes_with_no_installed_model_exits_1_prints_the_command_and_never_pulls(self):
        code, text, pulls, _ = self.main_with(["--yes"], _Tty())
        self.assertEqual((code, pulls), (1, []))
        self.assertIn("ollama pull qwen2.5-coder:14b", text)

    def test_piped_input_with_no_installed_model_exits_1_and_never_pulls(self):
        code, text, pulls, _ = self.main_with([], io.StringIO(""))
        self.assertEqual((code, pulls), (1, []))
        self.assertIn("ollama pull qwen2.5-coder:14b", text)

    def test_yes_with_a_named_model_that_is_not_installed_exits_1_and_never_pulls(self):
        code, text, pulls, _ = self.main_with(["--yes", "devstral-small-2:24b"], _Tty())
        self.assertEqual((code, pulls), (1, []))
        self.assertIn("ollama pull devstral-small-2:24b", text)

    def test_yes_with_an_installed_model_still_just_uses_it(self):
        code, text, pulls, _ = self.main_with(["--yes"], _Tty(), installed={"qwen2.5:14b"})
        self.assertIsNone(code, text)
        self.assertEqual(pulls, [])

    def test_a_terminal_answer_of_n_downloads_nothing_and_exits_1(self):
        with mock.patch("builtins.input", side_effect=["", "n"]):  # Enter at the menu, then "n" at the download prompt
            code, text, pulls, _ = self.main_with([], _Tty(), tty_out=True)
        self.assertEqual((code, pulls), (1, []))
        self.assertIn("Nothing downloaded", text)

    def test_every_printed_line_also_lands_in_the_run_log(self):
        code, text, pulls, log = self.main_with(["--yes"], _Tty(), env={"ANTIGRAVITY_NO_RUN_LOG": ""})
        self.assertIsNotNone(log, "no logs/run-<date>.log was written")
        for line in text.splitlines():
            if line.strip():
                self.assertIn(line, log)


class OllamaServe(unittest.TestCase):
    def start(self, env=None, answering=False):
        """Run check_ollama_service. Returns (Popen calls, printed text, os.environ['OLLAMA_HOST'] afterwards)."""
        started = []
        out = io.StringIO()

        def fake_urlopen(url, timeout=0):
            if answering or started:
                return _Server({url: "{}"})(url, timeout)
            raise urllib.error.URLError("down")

        def fake_popen(cmd, **kw):
            started.append((cmd, kw))

        with mock.patch.dict(run.os.environ, env or {}), \
                mock.patch.object(urllib.request, "urlopen", fake_urlopen), \
                mock.patch.object(run.shutil, "which", return_value="ollama"), \
                mock.patch.object(process.subprocess, "Popen", side_effect=fake_popen), \
                mock.patch.object(time, "sleep"), contextlib.redirect_stdout(out):
            run.os.environ.pop("OLLAMA_HOST", None) if env is None else None
            ok = run.check_ollama_service()
            after = run.os.environ.get("OLLAMA_HOST")
        return ok, started, out.getvalue(), after

    def test_spawned_serve_listens_on_this_pc_only(self):
        ok, started, _, after = self.start()
        self.assertTrue(ok)
        self.assertEqual(len(started), 1)
        cmd, kw = started[0]
        self.assertEqual(cmd, ["ollama", "serve"])
        self.assertEqual(kw["env"]["OLLAMA_HOST"], "127.0.0.1:11434")
        self.assertIsNone(after)  # our own environment was not touched

    def test_a_server_that_already_answers_is_never_restarted(self):
        ok, started, text, _ = self.start(answering=True)
        self.assertTrue(ok)
        self.assertEqual(started, [])
        self.assertIn("Connected to Ollama service", text)

    def test_a_users_own_ollama_host_is_replaced_for_the_child_only_and_we_say_so(self):
        ok, started, text, after = self.start(env={"OLLAMA_HOST": "0.0.0.0:11434"})
        self.assertEqual(started[0][1]["env"]["OLLAMA_HOST"], "127.0.0.1:11434")
        self.assertEqual(after, "0.0.0.0:11434")
        self.assertIn("listens on 127.0.0.1:11434 only", text)

    def test_a_running_server_on_the_users_own_host_is_left_alone(self):
        ok, started, _, after = self.start(env={"OLLAMA_HOST": "0.0.0.0:11434"}, answering=True)
        self.assertEqual((started, after), ([], "0.0.0.0:11434"))


if __name__ == "__main__":
    unittest.main()
