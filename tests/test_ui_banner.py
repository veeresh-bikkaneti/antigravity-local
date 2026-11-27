"""Tests for agl/ui/banner.py (Phase 5c)."""
import unittest
from unittest import mock

import agl.ui.banner as banner


class TestBanner(unittest.TestCase):
    def setUp(self):
        banner.set_plain(False)

    def test_is_plain(self):
        self.assertTrue(banner.is_plain(True))
        ports = mock.Mock()
        ports.environ_get.return_value = "1"
        self.assertTrue(banner.is_plain(False, ports=ports))
        ports.environ_get.return_value = None
        self.assertFalse(banner.is_plain(False, ports=ports))
        banner.set_plain(True)
        self.assertTrue(banner.is_plain(False, ports=ports))

    def test_safe_print_normal(self):
        lines = []
        banner.safe_print("hello world", out=lines.append)
        self.assertEqual(lines, ["hello world"])

    def test_safe_print_unicode_encode_error(self):
        calls = []

        def faulty_out(text, **kwargs):
            if "█" in text and len(calls) == 0:
                calls.append("raised")
                raise UnicodeEncodeError("ascii", text, 0, 1, "ordinal not in range")
            calls.append(text)

        with mock.patch("sys.stdout", mock.Mock(encoding="ascii")):
            banner.safe_print("bar: █", out=faulty_out)
        self.assertIn("raised", calls)
        self.assertTrue(any("bar: ?" in c for c in calls if isinstance(c, str)))

    def test_stage_banner_formatting(self):
        lines = []
        banner.stage(2, 4, "SERVER", "checking service", plain=True, out=lines.append)
        # stage prints an empty line first, then the banner line
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "")
        self.assertIn("STAGE 2/4  SERVER", lines[1])
        self.assertIn("checking service", lines[1])
        self.assertIn("#", lines[1])
        self.assertNotIn("█", lines[1])

    def test_stage_banner_rich(self):
        lines = []
        banner.stage(1, 4, "TEST", "rich test", plain=False, out=lines.append)
        self.assertEqual(len(lines), 2)
        self.assertIn("STAGE 1/4  TEST", lines[1])
        self.assertIn("█", lines[1])

    def test_level_clear(self):
        ports = mock.Mock()
        ports.model_wizard.CATALOG = [("test-model", 4.5, "fast")]
        ports._FACTS = {"source": "test-source"}
        ports.PROJECT_DIR = "/fake/project"
        ports.path_join = lambda *p: "/".join(p)
        ports.runlog.log_path.return_value = "/fake/project/logs/test.log"
        ports.environ_get.return_value = "ollama"
        ports.coding_apps.lines.return_value = ["App Line 1", "App Line 2"]
        ports.config.llm_base_url.return_value = "http://localhost:11434"

        lines = []
        banner.level_clear("test-model", "test-agent", ready="Ready line", ports=ports, out=lines.append)
        combined = "\n".join(lines)
        self.assertIn("LEVEL CLEAR", combined)
        self.assertIn("test-model", combined)
        self.assertIn("4.5 GB (catalog)", combined)
        self.assertIn("test-agent", combined)
        self.assertIn("Ready line", combined)
        self.assertIn("App Line 1", combined)

    def test_context_check_skips_when_no_agent_setup(self):
        ports = mock.Mock()
        ports.agent_setup = None
        lines = []
        banner.context_check(True, ports=ports, out=lines.append)
        self.assertEqual(lines, [])

    def test_context_check_warning_printed(self):
        ports = mock.Mock()
        ports.environ_copy.return_value = {"OLLAMA_CONTEXT_LENGTH": "2048"}
        ports.agent_setup.live_window.return_value = (2048, "env")
        ports.sys.platform = "linux"

        lines = []
        banner.context_check(True, ports=ports, out=lines.append)
        self.assertEqual(lines, [
            "       NOT CHECKED: Ollama is not running, or the model is not loaded yet.",
            "       RED (a guess): 2,048 tokens.",
            "       Source: OLLAMA_CONTEXT_LENGTH in this terminal.",
            "       The real size may be different. Run this again once the model is loaded.",
            "       For more room, raise the context length in the Ollama app settings,",
            "       or start the server with:",
            "       bash:       OLLAMA_CONTEXT_LENGTH=65536 ollama serve",
            "       PowerShell: $env:OLLAMA_CONTEXT_LENGTH=65536; ollama serve",
            "       A bigger window uses more GPU memory; if the model no longer fits, try 32768.",
            "       We do not change your Ollama settings.",
        ])

    def test_print_header_flag_check(self):
        ports = mock.Mock()
        ports.environ_get.return_value = "1"
        lines = []
        banner.print_header(ports=ports, out=lines.append)
        self.assertEqual(lines, [])

        ports.environ_get.return_value = None
        banner.print_header(ports=ports, out=lines.append)
        self.assertEqual(len(lines), 1)
        self.assertIn("Google Antigravity Local", lines[0])


if __name__ == "__main__":
    unittest.main()
