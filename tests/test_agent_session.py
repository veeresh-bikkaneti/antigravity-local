"""Phase 6c: the one model/base-url resolver in agl/app/agent_session.py, and one pure core hand-off decision."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agl.app.agent_session import resolve_model  # noqa: E402
from agl.core.handoff import merge_hooks  # noqa: E402


class ResolveModel(unittest.TestCase):
    def test_cli_flag_beats_the_env_and_the_env_beats_none(self):
        env = {"LOCAL_LLM_MODEL": "env:1", "LOCAL_LLM_BASE_URL": "http://env/v1"}
        self.assertEqual(resolve_model("cli:1", environ=env, default_base_url="http://default/v1"),
                         ("cli:1", "http://env/v1"))
        self.assertEqual(resolve_model(None, environ=env, default_base_url="http://default/v1"),
                         ("env:1", "http://env/v1"))

    def test_base_url_falls_back_to_the_default_and_the_model_to_none(self):
        self.assertEqual(resolve_model(None, environ={}, default_base_url="http://default/v1"),
                         (None, "http://default/v1"))
        self.assertEqual(resolve_model(None, environ={}, default_base_url=None), (None, None))


class MergeHooks(unittest.TestCase):
    def test_our_hooks_are_added_and_everything_else_is_kept(self):
        settings = {"permissions": {"allow": ["Bash(ls)"]}, "hooks": {}}
        merged = merge_hooks(settings, "python3 run.py handoff")
        self.assertEqual(merged["permissions"], {"allow": ["Bash(ls)"]})
        self.assertEqual([e["matcher"] for e in merged["hooks"]["StopFailure"]], ["rate_limit"])
        self.assertEqual(merged["hooks"]["PreCompact"][0]["hooks"][0]["command"], "python3 run.py handoff")

    def test_merging_twice_changes_nothing(self):
        once = merge_hooks({"hooks": {}}, "cmd")
        self.assertEqual(merge_hooks(once, "cmd"), once)


if __name__ == "__main__":
    unittest.main()
