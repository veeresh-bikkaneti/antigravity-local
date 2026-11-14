"""agent_setup: write pi / OpenCode / Codex config, and launch Claude Code with a child-only environment for the local Ollama model, offline.

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
        # pi's own default provider and model belong to the user. We launch with flags instead (see Launch).
        self.assertFalse((self.home / self.SETTINGS).exists())

    def test_other_providers_models_and_settings_are_kept(self):
        self.write(self.MODELS, json.dumps({"providers": {
            "mine": {"baseUrl": "http://x", "models": [{"id": "m1"}]},
            "ollama": {"baseUrl": "http://old", "models": [{"id": "llama3.1:8b", "contextWindow": 8192}],
                       "compat": {"custom": True}}}}))
        settings = self.write(self.SETTINGS, json.dumps({"theme": "dark", "defaultProvider": "anthropic"}, indent=4))
        settings_before = settings.read_bytes()
        ags.write_config("pi", MODEL, URL, home=self.home)
        data = self.read(self.MODELS)["providers"]
        self.assertEqual(data["mine"], {"baseUrl": "http://x", "models": [{"id": "m1"}]})
        self.assertEqual(data["ollama"]["baseUrl"], URL)
        self.assertEqual([m["id"] for m in data["ollama"]["models"]], ["llama3.1:8b", MODEL])
        self.assertEqual(data["ollama"]["models"][0]["contextWindow"], 8192)  # user tuning untouched
        self.assertTrue(data["ollama"]["compat"]["custom"])
        self.assertFalse(data["ollama"]["compat"]["supportsDeveloperRole"])
        self.assertEqual(settings.read_bytes(), settings_before)  # the user's own pi default is left exactly alone
        self.assertFalse(Path(str(settings) + ".bak-antigravity-local").exists())

    def test_second_run_changes_nothing_and_backup_is_made_once(self):
        self.write(self.MODELS, json.dumps({"providers": {"mine": {"models": []}}}))
        original = (self.home / self.MODELS).read_bytes()
        ags.write_config("pi", MODEL, URL, home=self.home)
        bak = self.home / (self.MODELS + ".bak-antigravity-local")
        self.assertEqual(bak.read_bytes(), original)
        after_first = (self.home / self.MODELS).read_bytes()
        result = ags.write_config("pi", MODEL, URL, home=self.home)
        self.assertEqual(after_first, (self.home / self.MODELS).read_bytes())
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
        self.assertEqual(names, ["models.json"])


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

    def test_a_broken_pi_settings_json_is_neither_read_nor_touched(self):
        # We no longer write settings.json, so a broken one is not our business and must not block setup.
        settings = self.write(".pi/agent/settings.json", "oops")
        ags.write_config("pi", MODEL, URL, home=self.home)
        self.assertEqual(settings.read_text(encoding="utf-8"), "oops")
        self.assertTrue((self.home / ".pi/agent/models.json").exists())


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
        # The shell characters matter on Windows: pi.cmd and opencode.cmd run through cmd.exe, where & | ; < > ^ %
        # are special.
        for bad in ("--oss", "-x", "two words", "tab\tx", "", "  ",
                    "x&calc", "x|y", "q;rm", "a>b", "a<b", "%PATH%", "m^x", "x$(id)", "a\"b", "a'b", "x:"):
            with self.subTest(bad=bad), self.assertRaises(ags.AgentSetupError):
                ags.write_config("pi", bad, URL, home=self.home)
        self.assertEqual(list(self.home.rglob("*")), [])

    def test_normal_tags_pass(self):
        for good in ("qwen3.6:27b", "hf.co/user/repo:Q4_K_M", "llama3.2:3b", "gpt-oss:20b", "Qwen2.5:14B",
                     "qwen2.5-coder:14b", "library/llama3", "a"):
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
        # pi takes the provider and model as flags, so we never rewrite the user's own pi default
        self.assertEqual(argvs["pi"], ["/bin/pi", "--provider", "ollama", "--model", MODEL])


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

    def test_pi_printed_command_matches_what_launch_runs(self):
        # The printed line, write_config's command and launch's argv must all say the same thing.
        result = ags.write_config("pi", MODEL, URL, home=self.home)
        self.assertEqual(result.command, ["pi", "--provider", "ollama", "--model", MODEL])
        _, _, text = self.go("pi", config_only=True)
        self.assertIn(f"pi --provider ollama --model {MODEL}", text)
        launched = []
        ags.launch("pi", MODEL, str(self.home), call=lambda a, **k: launched.append(a) or 0, which=lambda c: c)
        self.assertEqual(launched[0], result.command)

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


class Workspace(Home):
    """Where the agent works. run.sh and run.bat cd into the repo first, so 'the current folder' is often
    antigravity-local itself, and an agent started there would edit this repo's own files."""

    def setUp(self):
        super().setUp()
        self.project = self.home / "antigravity-local"      # stands in for the repo folder
        self.mine = self.home / "my-project"                 # the user's own project
        self.project.mkdir()
        self.mine.mkdir()

    def resolve(self, arg, cwd):
        lines = []
        got = ags.resolve_workspace(arg, str(cwd), str(self.project), out=lines.append)
        return got, "\n".join(lines)

    def test_no_flag_uses_the_folder_you_ran_it_from(self):
        got, text = self.resolve(None, self.mine)
        self.assertEqual(got, str(self.mine.resolve()))
        self.assertIn(str(self.mine.resolve()), text)
        self.assertEqual(len(text.splitlines()), 1)  # one line, as promised

    def test_inside_the_repo_folder_the_agent_gets_workspace_and_is_told_why(self):
        got, text = self.resolve(None, self.project)
        want = self.project.resolve() / "workspace"
        self.assertEqual(got, str(want))
        self.assertTrue(want.is_dir())  # created, same folder the SDK shell uses
        self.assertIn("--workspace", text)  # shows how to aim it at their own project
        self.assertIn(str(want), text)

    def test_existing_workspace_folder_is_reused_not_wiped(self):
        keep = self.project / "workspace" / "keep.txt"
        keep.parent.mkdir()
        keep.write_text("mine", encoding="utf-8")
        self.resolve(None, self.project)
        self.assertEqual(keep.read_text(encoding="utf-8"), "mine")

    def test_comparison_sees_through_a_dotdot_path(self):
        (self.project / "docs").mkdir()
        got, _ = self.resolve(None, self.project / "docs" / "..")
        self.assertEqual(got, str(self.project.resolve() / "workspace"))

    @unittest.skipUnless(sys.platform == "win32", "Windows paths ignore case")
    def test_windows_comparison_is_case_insensitive(self):
        got, _ = self.resolve(None, str(self.project).upper())
        self.assertEqual(Path(got).name, "workspace")

    def test_flag_wins_even_inside_the_repo_folder(self):
        got, text = self.resolve(str(self.mine), self.project)
        self.assertEqual(got, str(self.mine.resolve()))
        self.assertIn(str(self.mine.resolve()), text)
        self.assertFalse((self.project / "workspace").exists())  # no stray folder when told where to go

    def test_a_relative_flag_is_relative_to_where_you_ran_it(self):
        got, _ = self.resolve("my-project", self.home)
        self.assertEqual(got, str(self.mine.resolve()))

    def test_flag_may_point_at_the_repo_folder_on_purpose(self):
        got, _ = self.resolve(str(self.project), self.mine)
        self.assertEqual(got, str(self.project.resolve()))

    def test_missing_folder_is_an_error_with_exit_1_and_names_the_path(self):
        gone = self.home / "nope"
        with self.assertRaises(ags.AgentSetupError) as cm:
            self.resolve(str(gone), self.mine)
        self.assertEqual(cm.exception.code, 1)
        self.assertIn(str(gone), str(cm.exception))
        self.assertIn("not found", str(cm.exception))  # says what is wrong, not "is a file"
        self.assertFalse(gone.exists())  # we never create the user's folder for them

    def test_a_file_is_not_a_workspace(self):
        f = self.write("notes.txt", "x")
        with self.assertRaises(ags.AgentSetupError) as cm:
            self.resolve(str(f), self.mine)
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("a file", str(cm.exception))
        self.assertNotIn("not found", str(cm.exception))


def snapshot(root):
    """{relative path: (bytes, mtime_ns)} for every file under root, to prove nothing was written."""
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted(Path(root).rglob("*")) if p.is_file()}


class ClaudeEnv(Home):
    def env(self, base=URL, environ=None):
        return ags.claude_child_env(MODEL, base, home=self.home, environ=environ if environ is not None else {})

    def test_base_url_loses_v1_and_slashes(self):
        for given, want in ((f"{URL}", "http://localhost:11434"), (f"{URL}/", "http://localhost:11434"),
                            ("http://localhost:11434", "http://localhost:11434"),
                            ("http://lmstudio:1234/v1", "http://lmstudio:1234")):
            with self.subTest(given=given):
                self.assertEqual(self.env(given)["ANTHROPIC_BASE_URL"], want)

    def test_everything_the_spec_names_is_set(self):
        env = self.env()
        self.assertEqual(env["ANTHROPIC_API_KEY"], "")
        self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "ollama")
        self.assertEqual(env["CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST"], "1")
        self.assertEqual(env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"], "1")
        for k in ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"):
            self.assertEqual(env[k], "")
        for k in ("ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
                  "CLAUDE_CODE_SUBAGENT_MODEL"):
            self.assertEqual(env[k], MODEL)
        self.assertEqual(Path(env["CLAUDE_CONFIG_DIR"]), (self.home / ".claude-local").resolve())

    def test_context_follows_what_ollama_runs_with(self):
        self.assertEqual(self.env()["CLAUDE_CODE_MAX_CONTEXT_TOKENS"], "65536")
        self.assertEqual(self.env(environ={"OLLAMA_CONTEXT_LENGTH": "131072"})["CLAUDE_CODE_MAX_CONTEXT_TOKENS"],
                         "131072")
        self.assertEqual(self.env(environ={"OLLAMA_CONTEXT_LENGTH": "8192"})["CLAUDE_CODE_MAX_CONTEXT_TOKENS"],
                         "8192")
        self.assertIsNotNone(ags.claude_context({})[1])                                  # unset: warn
        self.assertIsNotNone(ags.claude_context({"OLLAMA_CONTEXT_LENGTH": "8192"})[1])    # lower: warn
        self.assertIsNone(ags.claude_context({"OLLAMA_CONTEXT_LENGTH": "65536"})[1])      # enough: quiet

    def test_the_parent_environment_is_not_modified(self):
        parent = {"PATH": "x", "ANTHROPIC_API_KEY": "sk-real"}
        before = dict(parent)
        env = self.env(environ=parent)
        self.assertEqual(parent, before)
        self.assertEqual(env["PATH"], "x")
        self.assertEqual(env["ANTHROPIC_API_KEY"], "")  # blanked in the child only


class ClaudeRun(Home):
    def go(self, argv_extra=None, environ=None, which=lambda c: "/bin/" + c, **kw):
        calls, lines = [], []
        real_environ = dict(__import__("os").environ)
        code = ags.run("claude", MODEL, URL, str(self.home), home=self.home, which=which,
                       call=lambda a, **k: calls.append((a, k)) or 0, out=lines.append,
                       environ={} if environ is None else environ, **kw)
        self.assertEqual(dict(__import__("os").environ), real_environ)  # os.environ untouched
        return code, calls, "\n".join(lines)

    def test_launches_claude_with_the_model_flag_and_a_child_only_env(self):
        code, calls, text = self.go()
        self.assertEqual(code, 0)
        (argv, kw), = calls
        self.assertEqual(argv, ["/bin/claude", "--model", MODEL])
        self.assertEqual(kw["env"]["ANTHROPIC_BASE_URL"], "http://localhost:11434")
        self.assertEqual(kw["cwd"], str(self.home))
        self.assertIn("Plain `claude`, VS Code and Claude Desktop still use your subscription", text)
        self.assertIn("delete ~/.claude-local", text)

    def test_only_claude_local_is_created_and_nothing_under_dot_claude_changes(self):
        settings = self.write(".claude/settings.json", json.dumps({"theme": "dark"}))
        self.write(".claude.json", "{}")
        before = snapshot(self.home)
        self.go()
        after = snapshot(self.home)
        for rel, data in before.items():
            self.assertEqual(after[rel], data, rel)
        new = set(after) - set(before)
        self.assertEqual(new, set())                                  # an empty folder only, no files
        self.assertTrue((self.home / ".claude-local").is_dir())
        self.assertEqual(settings.read_text(encoding="utf-8"), json.dumps({"theme": "dark"}))

    def test_a_preset_base_url_in_the_environment_warns_by_name_and_never_prints_the_value(self):
        _, _, text = self.go(environ={"ANTHROPIC_BASE_URL": "http://secret-host", "ANTHROPIC_API_KEY": "sk-abc"})
        self.assertIn("ANTHROPIC_BASE_URL is set in this terminal", text)
        self.assertIn("ANTHROPIC_API_KEY is set in this terminal", text)
        self.assertNotIn("secret-host", text)
        self.assertNotIn("sk-abc", text)

    def test_a_base_url_in_user_settings_warns_and_the_file_stays_byte_identical(self):
        p = self.write(".claude/settings.json", json.dumps({"env": {"ANTHROPIC_BASE_URL": "http://x:1"}}))
        raw, mtime = p.read_bytes(), p.stat().st_mtime_ns
        _, _, text = self.go()
        self.assertIn("ANTHROPIC_BASE_URL is set in the env block of", text)
        self.assertIn("every normal Claude Code session", text)
        self.assertEqual((p.read_bytes(), p.stat().st_mtime_ns), (raw, mtime))

    def test_config_only_never_prints_a_bare_claude_command(self):
        code, calls, text = self.go(config_only=True)
        self.assertEqual(code, 0)
        self.assertEqual(calls, [])
        self.assertNotIn("&& claude", text)
        self.assertFalse((self.home / ".claude-local").exists())

    def test_missing_binary_prints_the_script_and_does_not_install_without_a_y(self):
        for answer in ("", "n", "N"):
            with self.subTest(answer=answer):
                calls, lines = [], []
                code = ags.run("claude", MODEL, URL, str(self.home), home=self.home, which=lambda c: None,
                               input_fn=lambda _="": answer, call=lambda a, **k: calls.append(a) or 0,
                               out=lines.append, environ={})
                self.assertEqual(code, 1)
                self.assertEqual(calls, [])
                self.assertRegex("\n".join(lines), r"install\.(ps1|sh)")

    def test_yes_runs_the_official_script_once(self):
        calls, seen = [], iter([None, "/bin/claude", "/bin/claude"])  # missing, then installed
        code = ags.run("claude", MODEL, URL, str(self.home), home=self.home, which=lambda c: next(seen),
                       input_fn=lambda _="": "y", call=lambda a, **k: calls.append(a) or 0, out=lambda *_: None,
                       environ={})
        self.assertEqual(code, 0)
        self.assertRegex(" ".join(calls[0]), r"claude\.ai/install\.(ps1|sh)")

    def test_continue_local_passes_the_first_prompt_for_every_agent(self):
        for name, wants_flag in (("pi", False), ("opencode", True), ("codex", False), ("claude", False)):
            with self.subTest(agent=name):
                calls = []
                ags.run(name, MODEL, URL, str(self.home), home=self.home, which=lambda c: "/bin/" + c,
                        call=lambda a, **k: calls.append(a) or 0, out=lambda *_: None, environ={},
                        continue_local=True)
                argv = calls[0]
                self.assertIn(ags.CONTINUE_PROMPT, argv)
                self.assertEqual("--prompt" in argv, wants_flag)

    def test_resume_from_forks_the_transcript_and_prints_the_caveats(self):
        t = self.home / "t.jsonl"
        calls = []
        lines = []
        ags.run("claude", MODEL, URL, str(self.home), home=self.home, which=lambda c: "/bin/" + c,
                call=lambda a, **k: calls.append((a, k)) or 0, out=lines.append, environ={},
                resume_from="latest", find_transcript=lambda ident: t)
        (argv, kw), = calls
        self.assertEqual(argv, ["/bin/claude", "--resume", str(t), "--fork-session", "--model", MODEL])
        self.assertEqual(kw["env"]["ANTHROPIC_DEFAULT_SONNET_MODEL"], MODEL)
        text = "\n".join(lines)
        self.assertIn("EXPERIMENTAL", text)
        self.assertIn("thinking blocks", text)
        self.assertIn("109452", text)


class ClaudeCopySettings(Home):
    def test_copies_a_safe_slice_once_and_leaves_the_source_alone(self):
        self.write(".claude/CLAUDE.md", "rules")
        self.write(".claude/skills/a/SKILL.md", "skill")
        self.write(".claude/settings.json", json.dumps(
            {"theme": "dark", "env": {"ANTHROPIC_API_KEY": "x"}, "model": "opus", "apiKeyHelper": "h",
             "modelSettings": {}}))
        before = snapshot(self.home / ".claude")
        with quiet():
            ags.copy_user_settings(self.home)
        self.assertEqual(snapshot(self.home / ".claude"), before)
        self.assertEqual(self.read(".claude-local/settings.json"), {"theme": "dark"})
        self.assertEqual((self.home / ".claude-local" / "CLAUDE.md").read_text(encoding="utf-8"), "rules")
        self.assertTrue((self.home / ".claude-local" / "skills" / "a" / "SKILL.md").is_file())
        (self.home / ".claude-local" / "CLAUDE.md").write_text("edited", encoding="utf-8")
        with quiet():
            self.assertEqual(ags.copy_user_settings(self.home), [])  # second run: left alone
        self.assertEqual((self.home / ".claude-local" / "CLAUDE.md").read_text(encoding="utf-8"), "edited")


class ClaudeDoctor(Home):
    def doctor(self, environ=None, project=None, registry=None, platform="linux"):
        lines = []
        n = ags.claude_doctor(home=self.home, environ=environ or {}, project=project or self.home / "proj",
                              registry=registry or (lambda scope: []), platform=platform, out=lines.append)
        return n, "\n".join(lines)

    def test_clean_machine_reports_nothing(self):
        n, text = self.doctor()
        self.assertEqual(n, 0)
        self.assertIn("Nothing found", text)

    def test_finds_every_place_and_never_prints_a_secret(self):
        self.write(".claude/settings.json", json.dumps(
            {"env": {"ANTHROPIC_AUTH_TOKEN": "tok-SECRET1"}, "apiKeyHelper": "get-key-SECRET2", "model": "qwen3:14b"}))
        self.write("proj/.claude/settings.local.json", json.dumps({"env": {"CLAUDE_CODE_USE_BEDROCK": "1"}}))
        self.write("appdata/Code/User/settings.json",
                   '{ // comment\n "claudeCode.environmentVariables": [{"name":"ANTHROPIC_API_KEY","value":"vs-SECRET3"}],'
                   ' "claudeCode.disableLoginPrompt": true }')
        self.write("local/Claude/claude_desktop_config.json", json.dumps({"deploymentMode": "3p"}))
        env = {"ANTHROPIC_API_KEY": "env-SECRET4", "APPDATA": str(self.home / "appdata"),
               "LOCALAPPDATA": str(self.home / "local"), "CLAUDE_CODE_OAUTH_TOKEN": "oauth-SECRET5"}
        n, text = self.doctor(environ=env, registry=lambda s: ["ANTHROPIC_BASE_URL"] if s == "User" else [],
                              platform="win32")
        self.assertGreaterEqual(n, 9)
        for needle in ("ANTHROPIC_AUTH_TOKEN", "apiKeyHelper", "qwen3:14b", "CLAUDE_CODE_USE_BEDROCK",
                       "claudeCode.environmentVariables", "claudeCode.disableLoginPrompt", "deploymentMode",
                       "ollama launch claude-desktop --restore", "Windows User environment variables",
                       "CLAUDE_CODE_OAUTH_TOKEN"):
            self.assertIn(needle, text)
        self.assertNotRegex(text, r"SECRET\d")

    def test_aliases_and_claude_model_ids_are_fine(self):
        for model in ("sonnet", "claude-sonnet-4-5"):
            self.write(".claude/settings.json", json.dumps({"model": model}))
            self.assertEqual(self.doctor()[0], 0, model)

    def test_writes_nothing(self):
        self.write(".claude/settings.json", json.dumps({"env": {"ANTHROPIC_BASE_URL": "http://x"}}))
        before = snapshot(self.home)
        self.doctor(environ={"ANTHROPIC_BASE_URL": "http://y"})
        self.assertEqual(snapshot(self.home), before)


class ClaudeFlags(unittest.TestCase):
    def bad(self, argv):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            run.parse_args(argv)
        self.assertEqual(cm.exception.code, 2)

    def test_claude_is_a_choice_and_its_flags_parse(self):
        a = run.parse_args(["--agent", "claude", "--doctor", "--copy-user-settings", "--resume-from", "latest"])
        self.assertTrue(a.doctor and a.copy_user_settings)
        self.assertEqual(a.resume_from, "latest")
        self.assertTrue(run.parse_args(["--agent", "pi", "--continue-local"]).continue_local)

    def test_claude_only_flags_are_refused_for_other_agents(self):
        for argv in (["--doctor"], ["--agent", "pi", "--doctor"], ["--agent", "pi", "--copy-user-settings"],
                     ["--agent", "codex", "--resume-from", "latest"], ["--continue-local"],
                     ["--agent", "claude", "--resume-from", "x", "--continue-local"]):
            with self.subTest(argv=argv):
                self.bad(argv)

    def test_doctor_runs_without_the_venv_or_ollama(self):
        import subprocess
        had_venv = (ROOT / "venv").exists()
        r = subprocess.run([sys.executable, str(ROOT / "run.py"), "--agent", "claude", "--doctor"], cwd=ROOT,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"Nothing found|can route normal Claude Code")
        self.assertEqual((ROOT / "venv").exists(), had_venv)

    def test_handoff_subcommand_is_routed_before_argument_parsing(self):
        fake = types.SimpleNamespace(main=mock.Mock(return_value=0))
        with mock.patch.dict(sys.modules, {"handoff": fake}), self.assertRaises(SystemExit) as cm:
            run.main(["handoff", "--transcript", "x"])
        self.assertEqual(cm.exception.code, 0)
        fake.main.assert_called_once_with(["--transcript", "x"])


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

    def test_workspace_flag_parses_with_an_agent(self):
        self.assertEqual(run.parse_args(["--agent", "pi", "--workspace", "x"]).workspace, "x")
        self.assertIsNone(run.parse_args(["--agent", "pi"]).workspace)

    def test_workspace_without_an_agent_or_with_shell_is_a_usage_error(self):
        for argv in (["--workspace", "x"], ["--agent", "shell", "--workspace", "x"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as cm:
                run.parse_args(argv)
            self.assertEqual(cm.exception.code, 2)

    def main_with(self, argv, cwd=None, project=None):
        shell, agent = mock.Mock(), mock.Mock(return_value=0)
        cwd = str(cwd or ROOT.parent)

        async def fake_run_agent(model, base):
            shell(model, base)
        # the real resolver and error type, so the wiring through run.py is tested, not assumed
        fake = types.SimpleNamespace(run=agent, resolve_workspace=ags.resolve_workspace,
                                     AgentSetupError=ags.AgentSetupError)
        with mock.patch.object(run, "is_in_venv", return_value=True), \
                mock.patch.object(run, "check_ollama_service", return_value=True), \
                mock.patch.object(run, "select_and_pull_model", return_value="m:1"), \
                mock.patch.object(run, "check_or_update_memory"), \
                mock.patch.object(run, "run_agent", fake_run_agent), \
                mock.patch.object(run.os, "getcwd", return_value=cwd), \
                mock.patch.object(run, "PROJECT_DIR", str(project or ROOT)), \
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
        with tempfile.TemporaryDirectory() as d:
            shell, agent, code = self.main_with(["--agent", "pi", "--agent-config-only"], cwd=d)
            shell.assert_not_called()
            agent.assert_called_once()
            args, kwargs = agent.call_args
            self.assertEqual(args[0], "pi")
            self.assertEqual(args[1], "m:1")
            self.assertEqual(args[3], str(Path(d).resolve()))  # the resolved workspace, not just getcwd()
            self.assertTrue(kwargs["config_only"])
            self.assertEqual(code, 0)

    def test_run_from_the_repo_folder_hands_over_its_workspace_subfolder(self):
        with tempfile.TemporaryDirectory() as d:
            _, agent, _ = self.main_with(["--agent", "pi"], cwd=d, project=d)
            self.assertEqual(agent.call_args[0][3], str(Path(d).resolve() / "workspace"))

    def test_workspace_flag_reaches_the_agent(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as mine:
            _, agent, _ = self.main_with(["--agent", "pi", "--workspace", mine], cwd=d, project=d)
            self.assertEqual(agent.call_args[0][3], str(Path(mine).resolve()))

    def test_a_bad_workspace_stops_everything_with_exit_1_and_starts_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            shell, agent, code = self.main_with(["--agent", "pi", "--workspace", str(Path(d) / "gone")], cwd=d)
            self.assertEqual(code, 1)
            agent.assert_not_called()
            shell.assert_not_called()

    def test_failing_agent_propagates_its_exit_code(self):
        agent = mock.Mock(return_value=3)
        fake = types.SimpleNamespace(run=agent, resolve_workspace=ags.resolve_workspace,
                                     AgentSetupError=ags.AgentSetupError)

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
