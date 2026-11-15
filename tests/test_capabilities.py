"""Badge mapping per source: what Ollama says for sure, what Hugging Face only hints, and what the catalog carries."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import capabilities as cap  # noqa: E402
import model_wizard  # noqa: E402
import userdata  # noqa: E402


class OllamaBadges(unittest.TestCase):
    def test_each_documented_value_maps_or_is_quiet(self):
        self.assertEqual(cap.ollama_badges(["completion", "tools", "thinking"]), ("tools", "thinking"))
        self.assertEqual(cap.ollama_badges(["completion", "vision"]), ("vision",))
        self.assertEqual(cap.ollama_badges(["embedding"]), ("embedding",))
        self.assertEqual(cap.ollama_badges(["image"]), ("image",))
        self.assertEqual(cap.ollama_badges(["audio", "speech"]), ("audio",))  # both fold into one badge
        self.assertEqual(cap.ollama_badges(["completion", "insert", "decision"]), ())  # no badge, still a chat model

    def test_unknown_values_are_ignored_not_a_crash(self):
        self.assertEqual(cap.ollama_badges(["tools", "teleport", 7, None]), ("tools",))

    def test_no_capabilities_field_is_unknown_not_empty(self):
        self.assertIsNone(cap.ollama_badges(None))
        self.assertEqual(cap.ollama_badges([]), ())
        self.assertEqual(cap.ollama_badges("tools"), ())  # a string where a list belongs: nothing, no crash


class HfBadges(unittest.TestCase):
    def test_pipeline_tags(self):
        cases = {"image-text-to-text": "vision", "feature-extraction": "embedding", "text-to-image": "image",
                 "image-to-image": "image", "text-to-video": "video", "image-to-video": "video",
                 "automatic-speech-recognition": "audio", "text-to-speech": "audio"}
        for tag, badge in cases.items():
            with self.subTest(tag=tag):
                self.assertEqual(cap.hf_badges(tag), (badge,))
        self.assertEqual(cap.hf_badges("text-generation"), ())

    def test_template_hints_carry_a_question_mark(self):
        self.assertEqual(cap.hf_badges("text-generation", "{% if tools %}...{% endif %}"), ("tools?",))
        self.assertEqual(cap.hf_badges("text-generation", "<think>reason</think>"), ("thinking?",))
        self.assertEqual(cap.hf_badges("text-generation", "{{ tools }} <think>"), ("tools?", "thinking?"))

    def test_a_plain_template_or_no_template_gives_no_hint(self):
        self.assertEqual(cap.hf_badges("text-generation", "{{ messages }}"), ())
        self.assertEqual(cap.hf_badges("text-generation", None), ())
        self.assertEqual(cap.hf_badges("text-generation", 123), ())

    def test_only_the_head_of_a_huge_template_is_read(self):
        self.assertEqual(cap.hf_badges("text-generation", "x" * 5000 + " tools"), ())


class Kinds(unittest.TestCase):
    def test_ollama_kinds(self):
        self.assertEqual(cap.kind_from_ollama(["completion", "tools"]), "chat")
        self.assertEqual(cap.kind_from_ollama(["embedding"]), "embedding")
        self.assertEqual(cap.kind_from_ollama(["image"]), "media")
        self.assertEqual(cap.kind_from_ollama(["completion", "vision", "audio"]), "chat")  # multimodal chat model
        self.assertEqual(cap.kind_from_ollama(None), "unknown")
        self.assertEqual(cap.kind_from_ollama([]), "unknown")

    def test_hf_kinds(self):
        self.assertEqual(cap.kind_from_hf("feature-extraction"), "embedding")
        self.assertEqual(cap.kind_from_hf("text-to-video"), "media")
        self.assertEqual(cap.kind_from_hf("text-generation"), "chat")
        self.assertEqual(cap.kind_from_hf(None), "chat")

    def test_unknown_falls_back_to_the_name(self):
        self.assertEqual(cap.resolve_kind("unknown", "nomic-embed-text:latest"), "embedding")
        self.assertEqual(cap.resolve_kind("unknown", "qwen2.5-coder:7b"), "chat")
        self.assertEqual(cap.resolve_kind("chat", "bge-m3"), "chat")  # a known kind beats the name


class ToolsLevel(unittest.TestCase):
    def test_confirmed_beats_a_guess_beats_nothing(self):
        self.assertEqual([cap.tools_level(b) for b in (("tools",), ("tools?",), (), None)], [2, 1, 0, 1])

    def test_a_passing_probe_drops_the_question_mark_on_tools_only(self):
        self.assertEqual(cap.confirm_tools(("tools?", "thinking?")), ("tools", "thinking?"))
        self.assertIsNone(cap.confirm_tools(None))

    def test_format(self):
        self.assertEqual(cap.format_badges(("tools", "thinking?")), "tools, thinking?")
        self.assertEqual(cap.format_badges(()), "")
        self.assertEqual(cap.format_badges(None), "")


class Catalog(unittest.TestCase):
    def test_every_catalog_tag_has_badges_and_only_native_tool_callers_are_confirmed(self):
        for tag, _size, _note in model_wizard.CATALOG:
            with self.subTest(tag=tag):
                self.assertIsNotNone(cap.catalog_badges(tag))
        self.assertIn("tools", cap.catalog_badges("gpt-oss:20b"))
        self.assertIn("tools?", cap.catalog_badges("qwen3.8:27b"))  # the note says tool calling is new and unproven

    def test_names(self):
        self.assertEqual(cap.coding_badge("qwen2.5-coder:7b"), "coding")
        self.assertIsNone(cap.coding_badge("llama3.2:3b"))


class DataDir(unittest.TestCase):
    def test_env_override_wins_then_home(self):
        self.assertEqual(userdata.data_dir(env={"ANTIGRAVITY_LOCAL_HOME": "/x/y"}), Path("/x/y"))
        self.assertEqual(userdata.data_dir(home="/h", env={}), Path("/h") / ".antigravity-local")
        self.assertEqual(userdata.data_dir(home="/h", env={"ANTIGRAVITY_LOCAL_HOME": "  "}), Path("/h") / ".antigravity-local")

    def test_it_does_not_create_the_folder(self):
        with tempfile.TemporaryDirectory() as d:
            userdata.data_dir(home=d, env={})
            self.assertEqual(os.listdir(d), [])


if __name__ == "__main__":
    unittest.main()
