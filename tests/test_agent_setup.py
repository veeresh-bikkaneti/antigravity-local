"""agent_setup: write pi / OpenCode / Codex config for the local Ollama model, offline.

Every test points HOME at a temp dir and mocks `which`, input and subprocess, so nothing here can touch the
real ~/.pi or ~/.config/opencode, install anything, or start an agent.
"""
import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import agent_setup as ags  # noqa: E402
import run  # noqa: E402

URL = "http://localhost:11434/v1"
MODEL = "qwen2.5-coder:14b"


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


class Home(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)

    def read(self, rel):
        return json.loads((self.home / rel).read_text(encoding="utf-8"))

    def write(self, rel, text):
        p = self.home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p


class Pi(Home):
    MODELS = ".pi/agent/models.json"
    SETTINGS = ".pi/agent/settings.json"

    def test_fresh_write_matches_the_documented_shape(self):
        ags.write_config("pi", MODEL, URL, home=self.home)
        self.assertEqual(self.read(self.MODELS), {"providers": {"ollama": {
            "baseUrl": URL, "api": "openai-completions", "apiKey": "ollama",
            "compat": {"supportsDeveloperRole": False, "supportsReasoningEffort": False},
            "models": [{"id": MODEL, "contextWindow": 65536}]}}})
        self.assertEqual(self.read(self.SETTINGS), {"defaultProvider": "ollama", "defaultModel": MODEL})

    def test_other_providers_models_and_settings_are_kept(self):
        self.write(self.MODELS, json.dumps({"providers": {
            "mine": {"baseUrl": "http://x", "models": [{"id": "m1"}]},
            "ollama": {"baseUrl": "http://old", "models": [{"id": "llama3.1:8b", "contextWindow": 8192}],
                       "compat": {"custom": True}}}}))
        self.write(self.SETTINGS, json.dumps({"theme": "dark", "defaultModel": "old"}))
        ags.write_config("pi", MODEL, URL, home=self.home)
        data = self.read(self.MODELS)["providers"]
        self.assertEqual(data["mine"], {"baseUrl": "http://x", "models": [{"id": "m1"}]})
        self.assertEqual(data["ollama"]["baseUrl"], URL)
        self.assertEqual([m["id"] for m in data["ollama"]["models"]], ["llama3.1:8b", MODEL])
        self.assertEqual(data["ollama"]["models"][0]["contextWindow"], 8192)  # user tuning untouched
        self.assertTrue(data["ollama"]["compat"]["custom"])
        self.assertFalse(data["ollama"]["compat"]["supportsDeveloperRole"])
        self.assertEqual(self.read(self.SETTINGS), {"theme": "dark", "defaultProvider": "ollama", "defaultModel": MODEL})

    def test_second_run_changes_nothing_and_backup_is_made_once(self):
        self.write(self.MODELS, json.dumps({"providers": {"mine": {"models": []}}}))
        original = (self.home / self.MODELS).read_bytes()
        ags.write_config("pi", MODEL, URL, home=self.home)
        bak = self.home / (self.MODELS + ".bak-antigravity-local")
        self.assertEqual(bak.read_bytes(), original)
        after_first = {p: (self.home / p).read_bytes() for p in (self.MODELS, self.SETTINGS)}
        result = ags.write_config("pi", MODEL, URL, home=self.home)
        self.assertEqual(after_first, {p: (self.home / p).read_bytes() for p in (self.MODELS, self.SETTINGS)})
        self.assertFalse(result.changed)
        self.assertEqual(bak.read_bytes(), original)  # not overwritten by the second run

    def test_existing_backup_is_never_overwritten(self):
        self.write(self.MODELS, json.dumps({"providers": {}}))
        bak = self.write(self.MODELS + ".bak-antigravity-local", "FIRST BACKUP")
        ags.write_config("pi", MODEL, URL, home=self.home)
        self.assertEqual(bak.read_text(encoding="utf-8"), "FIRST BACKUP")

    def test_a_second_model_is_appended_not_replaced(self):
        ags.write_config("pi", MODEL, URL, home=self.home)
        ags.write_config("pi", "gpt-oss:20b", URL, home=self.home)
        ids = [m["id"] for m in self.read(self.MODELS)["providers"]["ollama"]["models"]]
        self.assertEqual(ids, [MODEL, "gpt-oss:20b"])
        self.assertEqual(self.read(self.SETTINGS)["defaultModel"], "gpt-oss:20b")

    def test_custom_endpoint_comes_from_the_base_url_argument(self):
        ags.write_config("pi", MODEL, "http://localhost:1234/v1", home=self.home)
        self.assertEqual(self.read(self.MODELS)["providers"]["ollama"]["baseUrl"], "http://localhost:1234/v1")

    def test_output_is_two_space_utf8_with_trailing_newline(self):
        ags.write_config("pi", MODEL, URL, home=self.home)
        text = (self.home / self.MODELS).read_text(encoding="utf-8")
        self.assertTrue(text.endswith("}\n"))
        self.assertIn('\n  "providers"', text)

    def test_no_temp_files_are_left_behind(self):
        ags.write_config("pi", MODEL, URL, home=self.home)
        names = sorted(p.name for p in (self.home / ".pi/agent").iterdir())
        self.assertEqual(names, ["models.json", "settings.json"])


class OpenCode(Home):
    CFG = ".config/opencode/opencode.json"

    def test_fresh_write_matches_the_documented_shape(self):
        ags.write_config("opencode", MODEL, URL, home=self.home)
        self.assertEqual(self.read(self.CFG), {
            "$schema": "https://opencode.ai/config.json",
            "provider": {"ollama": {"npm": "@ai-sdk/openai-compatible", "name": "Ollama (local)",
                                    "options": {"baseURL": URL}, "models": {MODEL: {"name": MODEL}}}}})

    def test_other_keys_providers_and_models_are_kept_and_schema_not_duplicated(self):
        self.write(self.CFG, json.dumps({
            "$schema": "https://example.invalid/own.json", "theme": "tokyo",
            "provider": {"other": {"npm": "x"}, "ollama": {"models": {"llama3.1:8b": {"name": "L"}},
                                                           "options": {"timeout": 5}}}}))
        ags.write_config("opencode", MODEL, URL, home=self.home)
        data = self.read(self.CFG)
        self.assertEqual(data["$schema"], "https://example.invalid/own.json")
        self.assertEqual(data["theme"], "tokyo")
        self.assertEqual(data["provider"]["other"], {"npm": "x"})
        self.assertEqual(set(data["provider"]["ollama"]["models"]), {"llama3.1:8b", MODEL})
        self.assertEqual(data["provider"]["ollama"]["options"], {"timeout": 5, "baseURL": URL})
        self.assertNotIn("model", data)  # we never change the user's default model in their file

    def test_second_run_changes_nothing_and_backup_is_made_once(self):
        self.write(self.CFG, json.dumps({"theme": "x"}))
        original = (self.home / self.CFG).read_bytes()
        ags.write_config("opencode", MODEL, URL, home=self.home)
        first = (self.home / self.CFG).read_bytes()
        self.assertEqual((self.home / (self.CFG + ".bak-antigravity-local")).read_bytes(), original)
        result = ags.write_config("opencode", MODEL, URL, home=self.home)
        self.assertEqual((self.home / self.CFG).read_bytes(), first)
        self.assertFalse(result.changed)


class InvalidConfig(Home):
    def test_invalid_json_is_left_untouched_and_names_the_file(self):
        p = self.write(".pi/agent/models.json", "{ not json")
        with self.assertRaises(ags.AgentSetupError) as cm:
            ags.write_config("pi", MODEL, URL, home=self.home)
        self.assertEqual(p.read_text(encoding="utf-8"), "{ not json")
        self.assertIn(str(p), str(cm.exception))
        self.assertEqual(cm.exception.code, 1)
        self.assertFalse((self.home / ".pi/agent/settings.json").exists())  # nothing half-written
        self.assertFalse(Path(str(p) + ".bak-antigravity-local").exists())

    def test_valid_json_of_the_wrong_shape_is_also_refused(self):
        for rel, text in ((".config/opencode/opencode.json", "[1, 2]"),
                          (".pi/agent/models.json", '{"providers": []}')):
            p = self.write(rel, text)
            name = "opencode" if "opencode" in rel else "pi"
            with self.assertRaises(ags.AgentSetupError):
                ags.write_config(name, MODEL, URL, home=self.home)
            self.assertEqual(p.read_text(encoding="utf-8"), text)

    def test_broken_settings_does_not_leave_models_changed(self):
        self.write(".pi/agent/settings.json", "oops")
        with self.assertRaises(ags.AgentSetupError):
            ags.write_config("pi", MODEL, URL, home=self.home)
        self.assertFalse((self.home / ".pi/agent/models.json").exists())


class Codex(Home):
    def test_no_file_is_written_and_command_is_right(self):
        result = ags.write_config("codex", MODEL, URL, home=self.home)
        self.assertEqual(result.command, ["codex", "--oss", "-m", MODEL])
        self.assertEqual(result.files, [])
        self.assertEqual(list(self.home.rglob("*")), [])

    def test_a_non_default_endpoint_is_called_out_not_silently_ignored(self):
        result = ags.write_config("codex", MODEL, "http://localhost:1234/v1", home=self.home)
        self.assertTrue(any("11434" in n for n in result.notes))


class ModelTag(Home):
    def test_bad_tags_are_rejected_before_anything_is_written(self):
        for bad in ("--oss", "-x", "two words", "tab\tx", "", "  "):
            with self.subTest(bad=bad), self.assertRaises(ags.AgentSetupError):
                ags.write_config("pi", bad, URL, home=self.home)
        self.assertEqual(list(self.home.rglob("*")), [])

    def test_normal_tags_pass(self):
        for good in ("qwen3.6:27b", "hf.co/user/repo:Q4_K_M", "llama3.2:3b", "gpt-oss:20b"):
            ags.validate_model_tag(good)


class EnsureAgent(unittest.TestCase):
    def ensure(self, name="pi", have=None, answer="", node="v26.13.0", npm=True, installed_after=True):
        have = dict(have or {})
        calls = []

        def which(cmd):
            return have.get(cmd)

        def call(argv, **kw):
            calls.append(argv)
            if installed_after:
                have[name] = f"/bin/{name}"
            return 0
        out = io.StringIO()
        if npm:
            have.setdefault("npm", "/bin/npm")
            have.setdefault("node", "/bin/node")
        with contextlib.redirect_stdout(out):
            try:
                path = ags.ensure_agent(name, which=which, input_fn=lambda _="": answer, call=call,
                                        node_version=lambda: node)
                err = None
            except ags.AgentSetupError as e:
                path, err = None, e
        return path, calls, out.getvalue(), err

    def test_found_binary_is_returned_without_asking(self):
        path, calls, text, err = self.ensure(have={"pi": "/bin/pi"}, answer="would-crash-if-asked")
        self.assertEqual((path, calls, err), ("/bin/pi", [], None))

    def test_missing_binary_prints_the_exact_command_and_does_not_install_on_n_or_empty(self):
        for answer in ("n", "", "N", "no", "  "):
            with self.subTest(answer=answer):
                path, calls, text, err = self.ensure(answer=answer)
                self.assertEqual(calls, [])
                self.assertIn("npm install -g @earendil-works/pi-coding-agent", text)
                self.assertIsNotNone(err)
                self.assertEqual(err.code, 1)

    def test_only_y_installs_and_it_uses_a_list_argv(self):
        for answer in ("y", "Y", "yes"):
            with self.subTest(answer=answer):
                path, calls, text, err = self.ensure(answer=answer)
                self.assertEqual(calls, [["/bin/npm", "install", "-g", "@earendil-works/pi-coding-agent"]])
                self.assertIsNone(err)

    def test_each_agent_has_its_own_package(self):
        want = {"pi": "@earendil-works/pi-coding-agent", "opencode": "opencode-ai", "codex": "@openai/codex"}
        for name, pkg in want.items():
            _, calls, _, _ = self.ensure(name=name, answer="y")
            self.assertEqual(calls[0][-1], pkg)

    def test_old_node_blocks_pi_but_not_the_others(self):
        _, calls, text, err = self.ensure(name="pi", answer="y", node="v20.11.0")
        self.assertEqual(calls, [])
        self.assertIn("22.19", text)
        self.assertEqual(err.code, 1)
        _, calls, _, err = self.ensure(name="opencode", answer="y", node="v20.11.0")
        self.assertEqual(len(calls), 1)

    def test_node_22_18_is_too_old_and_22_19_is_fine(self):
        self.assertFalse(ags.node_ok("v22.18.9"))
        self.assertTrue(ags.node_ok("v22.19.0"))
        self.assertTrue(ags.node_ok("v26.13.0"))
        self.assertFalse(ags.node_ok("garbage"))

    def test_no_npm_points_at_nodejs_and_exits_1(self):
        path, calls, text, err = self.ensure(npm=False, answer="y")
        self.assertEqual(calls, [])
        self.assertIn("https://nodejs.org", text)
        self.assertEqual(err.code, 1)

    def test_install_that_does_not_put_the_binary_on_path_is_reported_not_ignored(self):
        _, calls, text, err = self.ensure(answer="y", installed_after=False)
        self.assertEqual(len(calls), 1)
        self.assertIsNotNone(err)
        self.assertIn("PATH", text + str(err))


class Launch(Home):
    def test_launch_uses_a_list_argv_the_workspace_and_returns_the_exit_code(self):
        seen = {}

        def call(argv, **kw):
            seen["argv"], seen["kw"] = argv, kw
            return 7
        code = ags.launch("pi", MODEL, str(self.home), call=call, which=lambda c: "/bin/" + c)
        self.assertEqual(code, 7)
        self.assertIsInstance(seen["argv"], list)
        self.assertEqual(seen["argv"][0], "/bin/pi")
        self.assertEqual(seen["kw"]["cwd"], str(self.home))
        self.assertNotIn("shell", seen["kw"])

    def test_each_agent_is_pointed_at_the_chosen_model(self):
        argvs = {}
        for name in ("pi", "opencode", "codex"):
            ags.launch(name, MODEL, str(self.home), call=lambda a, **k: argvs.setdefault(name, a) and 0,
                       which=lambda c: "/bin/" + c)
        self.assertEqual(argvs["opencode"][1:], ["--model", "ollama/" + MODEL])
        self.assertEqual(argvs["codex"][1:], ["--oss", "-m", MODEL])
        self.assertEqual(argvs["pi"], ["/bin/pi"])  # pi reads defaultProvider/defaultModel from settings.json


class Run(Home):
    def go(self, name, config_only=False, answer="y"):
        launched = []
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = ags.run(name, MODEL, URL, str(self.home / "proj"), config_only=config_only, home=self.home,
                           which=lambda c: "/bin/" + c, input_fn=lambda _="": answer,
                           call=lambda a, **k: launched.append((a, k)) or 0, node_version=lambda: "v26.13.0")
        return code, launched, out.getvalue()

    def test_config_only_writes_prints_the_command_and_never_launches(self):
        code, launched, text = self.go("pi", config_only=True)
        self.assertEqual((code, launched), (0, []))
        self.assertTrue((self.home / ".pi/agent/models.json").exists())
        self.assertIn("pi", text)
        self.assertIn("cd ", text)  # the command to run, in the right folder

    def test_banner_names_agent_model_endpoint_file_and_that_settings_were_kept(self):
        _, _, text = self.go("opencode", config_only=True)
        for needle in ("opencode", MODEL, URL, "opencode.json", "other settings were kept", "64k"):
            self.assertIn(needle, text)

    def test_codex_banner_does_not_claim_a_config_file(self):
        _, _, text = self.go("codex", config_only=True)
        self.assertNotIn("other settings were kept", text)
        self.assertIn("codex --oss -m " + MODEL, text)

    def test_bad_config_stops_before_launch_with_exit_1(self):
        (self.home / ".pi/agent").mkdir(parents=True)
        (self.home / ".pi/agent/models.json").write_text("{bad", encoding="utf-8")
        code, launched, text = self.go("pi")
        self.assertEqual((code, launched), (1, []))
        self.assertIn("models.json", text)

    def test_full_run_launches_the_agent_and_returns_its_exit_code(self):
        code, launched, _ = self.go("pi")
        self.assertEqual(code, 0)
        self.assertEqual(len(launched), 1)


class RunPyHooks(unittest.TestCase):
    def test_flag_parses_and_defaults_to_shell(self):
        self.assertEqual(run.parse_args([]).agent, "shell")
        self.assertEqual(run.parse_args(["--agent", "pi"]).agent, "pi")
        self.assertTrue(run.parse_args(["--agent", "pi", "--agent-config-only"]).agent_config_only)

    def test_unknown_agent_exits_2(self):
        with quiet(), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            run.parse_args(["--agent", "bogus"])
        self.assertEqual(cm.exception.code, 2)

    def test_config_only_without_an_agent_is_a_usage_error(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            run.parse_args(["--agent-config-only"])
        self.assertEqual(cm.exception.code, 2)

    def main_with(self, argv):
        shell, agent = mock.Mock(), mock.Mock(return_value=0)

        async def fake_run_agent(model, base):
            shell(model, base)
        fake = types.SimpleNamespace(run=agent)
        with mock.patch.object(run, "is_in_venv", return_value=True), \
                mock.patch.object(run, "check_ollama_service", return_value=True), \
                mock.patch.object(run, "select_and_pull_model", return_value="m:1"), \
                mock.patch.object(run, "check_or_update_memory"), \
                mock.patch.object(run, "run_agent", fake_run_agent), \
                mock.patch.dict(sys.modules, {"agent_setup": fake}), quiet():
            try:
                run.main(argv)
                code = None
            except SystemExit as e:
                code = e.code
        return shell, agent, code

    def test_default_still_runs_the_antigravity_shell(self):
        shell, agent, code = self.main_with([])
        shell.assert_called_once()
        agent.assert_not_called()

    def test_explicit_shell_is_the_same_as_the_default(self):
        shell, agent, _ = self.main_with(["--agent", "shell"])
        shell.assert_called_once()
        agent.assert_not_called()

    def test_pi_hands_off_to_agent_setup_and_skips_the_shell(self):
        shell, agent, code = self.main_with(["--agent", "pi", "--agent-config-only"])
        shell.assert_not_called()
        agent.assert_called_once()
        args, kwargs = agent.call_args
        self.assertEqual(args[0], "pi")
        self.assertEqual(args[1], "m:1")
        self.assertTrue(kwargs["config_only"])
        self.assertEqual(code, 0)

    def test_failing_agent_propagates_its_exit_code(self):
        agent = mock.Mock(return_value=3)
        fake = types.SimpleNamespace(run=agent)

        async def noop(*a):
            return None
        with mock.patch.object(run, "is_in_venv", return_value=True), \
                mock.patch.object(run, "check_ollama_service", return_value=True), \
                mock.patch.object(run, "select_and_pull_model", return_value="m:1"), \
                mock.patch.object(run, "check_or_update_memory"), mock.patch.object(run, "run_agent", noop), \
                mock.patch.dict(sys.modules, {"agent_setup": fake}), quiet(), self.assertRaises(SystemExit) as cm:
            run.main(["--agent", "pi"])
        self.assertEqual(cm.exception.code, 3)

    def test_help_lists_the_flag_and_does_not_touch_the_venv(self):
        import subprocess
        had_venv = (ROOT / "venv").exists()
        r = subprocess.run([sys.executable, str(ROOT / "run.py"), "--help"], cwd=ROOT, capture_output=True,
                           text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--agent", r.stdout)
        self.assertIn("pi", r.stdout)
        self.assertEqual((ROOT / "venv").exists(), had_venv)


if __name__ == "__main__":
    unittest.main()
