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
from agl.core.context_guard import band, real_window  # noqa: E402


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
        core_config.pi_models(data, "m1", "http://h:11434/v1", "models.json", 65536)
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


if __name__ == "__main__":
    unittest.main()
