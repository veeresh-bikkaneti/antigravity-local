"""Tests for agl/ui/pick_menu.py (Phase 5c)."""
import unittest
from unittest import mock

import agl.ui.pick_menu as pick_menu


class TestPickMenu(unittest.TestCase):
    def setUp(self):
        pick_menu._WARNED.clear()

    def test_warn_once(self):
        lines = []
        pick_menu._warn_once("key1", "test warning", out=lines.append)
        pick_menu._warn_once("key1", "test warning again", out=lines.append)
        self.assertEqual(len(lines), 1)
        self.assertIn("Warning: test warning", lines[0])

    def test_printable_tag(self):
        self.assertEqual(pick_menu.printable_tag("qwen2.5-coder:7b"), "'qwen2.5-coder:7b'")
        self.assertEqual(pick_menu.printable_tag("hf.co/user/repo:Q4_K_M"), "'hf.co/user/repo:Q4_K_M'")
        unsafe = "bad\ntag; rm -rf /"
        res = pick_menu.printable_tag(unsafe)
        self.assertIn("(unsafe name, shown escaped)", res)

    def test_find_candidate(self):
        pool = [
            {"tag": "qwen2.5-coder:7b"},
            {"tag": "hf.co/bartowski/model:q4_k_m"},
        ]
        self.assertEqual(pick_menu.find_candidate("qwen2.5-coder:7b", pool), pool[0])
        self.assertEqual(pick_menu.find_candidate("bartowski/model:q4_k_m", pool), pool[1])
        self.assertIsNone(pick_menu.find_candidate("nonexistent", pool))

    def test_ledger_warning(self):
        ports = mock.Mock()
        ports.ledger.status.return_value = "fail"
        lines = []
        pick_menu.ledger_warning("failed-model:7b", [], ports=ports, out=lines.append)
        self.assertEqual(len(lines), 1)
        self.assertIn("failed a tool-call probe", lines[0])

        lines.clear()
        ports.ledger.status.return_value = "pass"
        pick_menu.ledger_warning("passed-model:7b", [], ports=ports, out=lines.append)
        self.assertEqual(lines, [])

    def test_refuse_non_chat(self):
        pool = [
            {"tag": "bge-m3:latest", "kind": "embedding"},
            {"tag": "qwen2.5:7b", "kind": "chat"},
        ]
        lines = []
        self.assertTrue(pick_menu.refuse_non_chat("bge-m3:latest", pool, out=lines.append))
        self.assertIn("is an embedding or media model", lines[0])

        lines.clear()
        self.assertFalse(pick_menu.refuse_non_chat("qwen2.5:7b", pool, out=lines.append))
        self.assertEqual(lines, [])

    def test_hf_tag_problem_and_ok(self):
        ports = mock.Mock()
        ports.model_wizard.hf_check.return_value = ("bad_tag", ())
        self.assertIn("is not a Hugging Face tag", pick_menu.hf_tag_problem("bad", ports=ports))
        self.assertFalse(pick_menu.hf_tag_ok("bad", ports=ports, out=lambda s: None))

        ports.model_wizard.hf_check.return_value = ("missing", ())
        self.assertIn("was not found on Hugging Face (404)", pick_menu.hf_tag_problem("hf.co/u/notfound:q4", ports=ports))

        ports.model_wizard.hf_check.return_value = ("ok", ())
        self.assertIsNone(pick_menu.hf_tag_problem("hf.co/u/ok:q4", ports=ports))
        self.assertTrue(pick_menu.hf_tag_ok("hf.co/u/ok:q4", ports=ports, out=lambda s: None))

    def test_typed_tag_problem(self):
        ports = mock.Mock()
        ports.is_model_installed.return_value = True
        self.assertIsNone(pick_menu.typed_tag_problem("installed-tag", ["installed-tag"], ports=ports))

        ports.is_model_installed.return_value = False
        ports.model_wizard.is_hf_tag.return_value = False
        ports.model_wizard.tag_exists.return_value = False
        problem = pick_menu.typed_tag_problem("not-on-registry", [], ports=ports)
        self.assertIn("is not on the Ollama registry", problem)

    def test_select_openai_model_defaults_to_top_ranked(self):
        ports = mock.Mock()
        ports.list_openai_models.return_value = ["model-b", "model-a"]
        ports.capability_rank_key = lambda m: 10 if m == "model-a" else 5
        ports.environ_get.return_value = ""

        lines = []
        chosen = pick_menu.select_openai_model("http://localhost:1234/v1", ports=ports, out=lines.append)
        self.assertEqual(chosen, "model-a")
        self.assertTrue(any("Using 'model-a'" in line for line in lines))
        ports.update_env_model.assert_called_with("model-a")

    def test_select_openai_model_picks_requested(self):
        ports = mock.Mock()
        ports.list_openai_models.return_value = ["Qwen2.5-Coder-7B", "Gemma-2-9B"]

        lines = []
        chosen = pick_menu.select_openai_model("http://localhost:1234/v1", requested_model="qwen2.5-coder-7b", ports=ports, out=lines.append)
        self.assertEqual(chosen, "Qwen2.5-Coder-7B")
        self.assertTrue(any("Using 'Qwen2.5-Coder-7B'" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
