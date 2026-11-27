import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import agent_setup as ags  # noqa: E402

from agl.app import agent  # noqa: E402
from agl.core import agent_config as core_config  # noqa: E402
from agl.core.context_guard import band, model_window, real_window, same_model, trained_max  # noqa: E402
from agl.ui import banner  # noqa: E402


def row(name, context_length):
    return {"name": name, "size": 1, "size_vram": 1, "context_length": context_length, "expires_at": None}


class LoadedWindowTests(unittest.TestCase):
    def test_loaded_rows_report_their_context(self):
        rows = [row("demo:1b", 8192), row("demo:2b", 16384), row("demo:3b", 32768), row("demo:4b", 65536)]
        self.assertEqual(real_window(rows, "demo:1b", None, 8), (8192, "loaded"))
        self.assertEqual(real_window(rows, "demo:2b", None, 8), (16384, "loaded"))
        self.assertEqual(real_window(rows, "demo:3b", None, 8), (32768, "loaded"))
        self.assertEqual(real_window(rows, "demo:4b", None, 8), (65536, "loaded"))

    def test_missing_model_falls_through_to_default(self):
        rows = [row("demo:1b", 8192)]
        self.assertEqual(real_window(rows, "demo:9b", None, 24), (32768, "default"))

    def test_ollama_down_uses_env_then_default(self):
        self.assertEqual(real_window([], "demo:1b", "8192", 8), (8192, "env"))
        self.assertEqual(real_window([], "demo:1b", None, 8), (4096, "default"))

    def test_latest_tag_matches_bare_name_both_ways(self):
        self.assertEqual(real_window([row("demo", 8192)], "demo:latest", None, 8), (8192, "loaded"))
        self.assertEqual(real_window([row("demo:latest", 8192)], "demo", None, 8), (8192, "loaded"))

    def test_other_tags_do_not_match(self):
        self.assertEqual(real_window([row("demo:1b", 8192)], "demo", None, 8), (4096, "default"))

    def test_first_usable_matching_row_wins(self):
        rows = [row("demo:1b", None), row("demo:1b", 8192), row("demo:1b", 16384)]
        self.assertEqual(real_window(rows, "demo:1b", None, 8), (8192, "loaded"))

    def test_junk_rows_and_values_are_ignored(self):
        junk = [
            row("demo:1b", True),
            row("demo:1b", "8192"),
            row("demo:1b", 0),
            row("demo:1b", -5),
            row("demo:1b", None),
            row("demo:1b", 8.5),
            "demo:1b",
            None,
            {"name": None, "context_length": 8192},
        ]
        self.assertEqual(real_window(junk, "demo:1b", None, 8), (4096, "default"))

    def test_non_list_rows_never_raise(self):
        for rows in (None, "demo:1b", {"name": "demo:1b", "context_length": 8192}, 42):
            self.assertEqual(real_window(rows, "demo:1b", None, 8), (4096, "default"))


class EnvWindowTests(unittest.TestCase):
    def test_plain_positive_integer_is_used(self):
        self.assertEqual(real_window([], "demo:1b", " 2048 ", 8), (2048, "env"))

    def test_everything_else_falls_through(self):
        for env in ("0", "-1", "abc", "", "²", "8192.0", None, 8192):
            self.assertEqual(real_window([], "demo:1b", env, 8), (4096, "default"), repr(env))


class VramDefaultTests(unittest.TestCase):
    def test_below_24_gib_is_small(self):
        self.assertEqual(real_window([], "demo:1b", None, 23.9), (4096, "default"))

    def test_24_up_to_48_gib_is_medium(self):
        self.assertEqual(real_window([], "demo:1b", None, 24), (32768, "default"))
        self.assertEqual(real_window([], "demo:1b", None, 47.9), (32768, "default"))

    def test_48_gib_and_up_is_large(self):
        self.assertEqual(real_window([], "demo:1b", None, 48), (262144, "default"))
        self.assertEqual(real_window([], "demo:1b", None, 80), (262144, "default"))

    def test_junk_vram_counts_as_small(self):
        for vram in (None, "48", True, float("nan"), float("inf"), []):
            self.assertEqual(real_window([], "demo:1b", None, vram), (4096, "default"), repr(vram))


class BandTests(unittest.TestCase):
    def test_band_edges(self):
        self.assertEqual(band(16383), "red")
        self.assertEqual(band(16384), "amber")
        self.assertEqual(band(65535), "amber")
        self.assertEqual(band(65536), "green")


class LiveWindowWiringTests(unittest.TestCase):
    """The window the apps are told: pi's contextWindow, opencode's limit, Claude Code's window variables."""

    def test_pi_models_corrects_an_existing_window_and_keeps_other_keys(self):
        data = {"providers": {"ollama": {"models": [{"id": "m1", "contextWindow": 4096, "name": "keep me"}]}}}
        core_config.pi_models(data, "m1", "http://h:11434/v1", "models.json", 65536, source="loaded")
        entry = data["providers"]["ollama"]["models"][0]
        self.assertEqual(entry["contextWindow"], 65536)
        self.assertEqual(entry["name"], "keep me")

    def test_claude_child_env_sets_both_window_variables_and_never_disables_compact(self):
        with tempfile.TemporaryDirectory() as home:
            env = ags.claude_child_env("m1", "http://h:11434", home=home, environ={}, window=8192)
        self.assertEqual(env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"], "8192")
        self.assertEqual(env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"], "8192")
        self.assertNotIn("DISABLE_COMPACT", env)

    def test_opencode_adds_limit_context_and_keeps_user_output(self):
        data = {"provider": {"ollama": {"models": {"m1": {"name": "m1", "limit": {"output": 1000}}}}}}
        core_config.opencode(data, "m1", "http://h:11434/v1", "opencode.json", "schema", 32768)
        limit = data["provider"]["ollama"]["models"]["m1"]["limit"]
        self.assertEqual(limit["context"], 32768)
        self.assertEqual(limit["output"], 1000)

    def test_default_guess_keeps_an_existing_window(self):
        pi = {"providers": {"ollama": {"models": [{"id": "m1", "contextWindow": 65536}]}}}
        core_config.pi_models(pi, "m1", "http://h:11434/v1", "models.json", 4096, source="default")
        self.assertEqual(pi["providers"]["ollama"]["models"][0]["contextWindow"], 65536)
        oc = {"provider": {"ollama": {"models": {"m1": {"name": "m1", "limit": {"context": 65536}}}}}}
        core_config.opencode(oc, "m1", "http://h:11434/v1", "opencode.json", "schema", 4096, source="default")
        self.assertEqual(oc["provider"]["ollama"]["models"]["m1"]["limit"]["context"], 65536)

    def test_loaded_or_env_window_replaces_the_existing_one(self):
        for source in ("loaded", "env"):
            pi = {"providers": {"ollama": {"models": [{"id": "m1", "contextWindow": 65536}]}}}
            core_config.pi_models(pi, "m1", "http://h:11434/v1", "models.json", 8192, source=source)
            self.assertEqual(pi["providers"]["ollama"]["models"][0]["contextWindow"], 8192, source)
            oc = {"provider": {"ollama": {"models": {"m1": {"name": "m1", "limit": {"context": 65536}}}}}}
            core_config.opencode(oc, "m1", "http://h:11434/v1", "opencode.json", "schema", 8192, source=source)
            self.assertEqual(oc["provider"]["ollama"]["models"]["m1"]["limit"]["context"], 8192, source)

    def test_opencode_output_is_clamped_to_the_window(self):
        big = {"provider": {"ollama": {"models": {"m1": {"name": "m1", "limit": {"output": 50000}}}}}}
        core_config.opencode(big, "m1", "http://h:11434/v1", "opencode.json", "schema", 8192, source="loaded")
        self.assertEqual(big["provider"]["ollama"]["models"]["m1"]["limit"]["output"], 8192)
        fresh = {"provider": {"ollama": {}}}
        core_config.opencode(fresh, "m1", "http://h:11434/v1", "opencode.json", "schema", 1024, source="loaded")
        self.assertEqual(fresh["provider"]["ollama"]["models"]["m1"]["limit"]["output"], 256)
        # the window the app really uses is the 65536 already in the file, so 50000 still fits
        kept = {"provider": {"ollama": {"models": {"m1": {"name": "m1", "limit": {"context": 65536, "output": 50000}}}}}}
        core_config.opencode(kept, "m1", "http://h:11434/v1", "opencode.json", "schema", 4096, source="default")
        self.assertEqual(kept["provider"]["ollama"]["models"]["m1"]["limit"]["output"], 50000)

    def test_setup_run_passes_the_source_to_the_pi_file(self):
        for source, window, expected in (("default", 4096, 65536), ("loaded", 8192, 8192)):
            with tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                models = home / ".pi" / "agent" / "models.json"
                models.parent.mkdir(parents=True)
                models.write_text(json.dumps({"providers": {"ollama": {"models": [{"id": "m1", "contextWindow": 65536}]}}}),
                                  encoding="utf-8")
                code = ags.run("pi", "m1", "http://h:11434/v1", tmp, config_only=True, home=home, environ={},
                               out=lambda *a: None, window_of=lambda *a: (window, source))
                written = json.loads(models.read_text(encoding="utf-8"))
            self.assertEqual(code, 0)
            self.assertEqual(written["providers"]["ollama"]["models"][0]["contextWindow"], expected, source)


class ToldOnlyWhenWrittenTests(unittest.TestCase):
    """Never say an app "is told" the window when this run gives it no number."""

    CASES = [("pi", False, True), ("opencode", True, True), ("claude", False, True),
             ("claude", True, False), ("codex", False, False), ("codex", True, False)]

    def test_stage_4_banner_is_told_only_for_apps_that_get_the_number(self):
        for name, config_only, told in self.CASES:
            ports = mock.MagicMock()
            args = SimpleNamespace(agent=name, workspace=None, agent_config_only=config_only, resume_from=None)
            agent.handle_agent(args, "m1", "http://h:11434/v1", False, ports=ports, out=lambda *a: None)
            self.assertIs(ports.context_check.call_args.kwargs["told"], told, (name, config_only))

    def test_setup_run_context_line_only_for_apps_that_get_the_number(self):
        for name, told in (("pi", True), ("codex", False), ("claude", False)):
            lines = []
            with tempfile.TemporaryDirectory() as tmp:
                code = ags.run(name, "m1", "http://h:11434/v1", tmp, config_only=True, home=Path(tmp), environ={},
                               out=lines.append, window_of=lambda *a: (8192, "loaded"))
            self.assertEqual(code, 0)
            self.assertIs(any("is told" in line for line in lines), told, name)


class BannerTextTests(unittest.TestCase):
    """The stage 4 lines match docs/mockups/real-window.md word for word."""

    def test_running_window_already_covers_the_target(self):
        self.assertEqual(banner._context_lines("qwen2.5:14b-omb-32k", 32768, "model", 16384, 131072, False), [
            "qwen2.5:14b-omb-32k runs with a 32,768 token window.",
            "That covers the 16,384 this GPU can give. No copy needed.",
        ])

    def test_running_window_is_the_trained_max(self):
        self.assertEqual(banner._context_lines("qwen2.5:14b", 8192, "loaded", 8192, 8192, False), [
            "qwen2.5:14b runs with an 8,192 token window.",
            "That is as high as this model goes. A bigger copy will not help.",
        ])

    def test_default_is_under_the_target(self):
        self.assertEqual(banner._context_lines("qwen2.5:14b", 4096, "default", 16384, 131072, False), [
            "qwen2.5:14b runs with Ollama's default 4,096 tokens.",
            "Coding agents want about 16,384 on this GPU.",
        ])

    def test_no_rung_fits(self):
        self.assertEqual(banner._context_lines("qwen2.5:14b", 4096, "default", 0, 131072, False), [
            "qwen2.5:14b runs with Ollama's default 4,096 tokens.",
            "This GPU cannot fit an 8,192 window on top of the weights.",
            "No copy. A long prompt can use /steps.",
        ])

    def test_target_not_read(self):
        lines = banner._context_lines("qwen2.5:14b", 4096, "default", None, None, True)
        self.assertEqual(lines[1], "Free GPU memory or the model's shape was not read, so there is no target.")
        self.assertEqual(lines[2], "The coding app we set up is told: 4,096.")

    def test_no_server_restart_or_band_words(self):
        for target in (0, None, 16384):
            text = "\n".join(banner._context_lines("m", 4096, "default", target, None, False))
            for word in ("OLLAMA_CONTEXT_LENGTH", "ollama serve", "RED", "AMBER", "GREEN", "65536", "65,536"):
                self.assertNotIn(word, text, (target, word))

    def test_article_before_the_number(self):
        for tokens, word in ((8192, "an"), (11000, "an"), (18000, "an"), (80000, "an"),
                             (16384, "a"), (32768, "a"), (1000, "a")):
            self.assertEqual(banner._article(tokens), word, tokens)


class ModelWindowTests(unittest.TestCase):
    """The model's own num_ctx sits between the loaded row and the env var (Ollama's read order)."""

    SHOWN = {"parameters": "stop \"<|im_end|>\"\nnum_ctx 32768\ntemperature 0.7"}

    def test_model_num_ctx_beats_env_and_default(self):
        self.assertEqual(real_window([], "demo:1b", "8192", 8, self.SHOWN), (32768, "model"))

    def test_loaded_row_beats_model_num_ctx(self):
        rows = [{"name": "demo:1b", "context_length": 16384}]
        self.assertEqual(real_window(rows, "demo:1b", None, 8, self.SHOWN), (16384, "loaded"))

    def test_no_num_ctx_falls_through(self):
        shown = {"parameters": "temperature 0.7"}
        self.assertEqual(real_window([], "demo:1b", "8192", 8, shown), (8192, "env"))
        self.assertEqual(real_window([], "demo:1b", None, 8, {}), (4096, "default"))
        self.assertEqual(real_window([], "demo:1b", None, 8, None), (4096, "default"))

    def test_junk_num_ctx_is_ignored(self):
        for params in ("num_ctx", "num_ctx abc", "num_ctx -5", "num_ctx 0", "num_ctx 1.5", "num_ctx \u0663", 7, None):
            self.assertIsNone(model_window({"parameters": params}), repr(params))
        self.assertIsNone(model_window("not a dict"))

    def test_trained_max(self):
        self.assertEqual(trained_max({"model_info": {"qwen2.context_length": 131072}}), 131072)
        for info in ({}, {"qwen2.context_length": "131072"}, {"qwen2.context_length": True}, None, [1]):
            self.assertIsNone(trained_max({"model_info": info}), repr(info))
        self.assertIsNone(trained_max(None))

    def test_same_model(self):
        self.assertTrue(same_model("demo", "demo:latest"))
        self.assertFalse(same_model("demo:1b", "demo"))
        self.assertFalse(same_model(None, None))


if __name__ == "__main__":
    unittest.main()
