"""Tests for agl/app/server.py (Phase 5b)."""
import unittest
from unittest import mock

import agl.app.server


class FakeOllama:
    def __init__(self, responds=True):
        self.responds = responds

    def check_service(self, base_url, timeout=3):
        return self.responds


class FakePorts:
    def __init__(self, responds=True, has_bin=True):
        self.ollama = FakeOllama(responds=responds)
        self.shutil = mock.Mock()
        self.shutil.which.return_value = "/usr/bin/ollama" if has_bin else None
        self.stage = mock.Mock()
        self.IS_WIN = True
        self.sys = mock.Mock()
        self.sys.exit.side_effect = SystemExit(1)
        self.os = mock.Mock()
        self.os.environ = {}
        self.process = mock.Mock()
        self.time = mock.Mock()
        self.LOOPBACK_OLLAMA_HOST = "127.0.0.1:11434"


class TestServer(unittest.TestCase):
    def test_check_ollama_service_connected_returns_true(self):
        fake_ports = FakePorts(responds=True)
        out = mock.Mock()
        result = agl.app.server.check_ollama_service("http://127.0.0.1:11434", ports=fake_ports, out=out)
        self.assertTrue(result)
        out.assert_called_with("       Connected to Ollama service at: http://127.0.0.1:11434")

    def test_check_ollama_service_not_installed_calls_out_error(self):
        fake_ports = FakePorts(responds=False, has_bin=False)
        out = mock.Mock()
        with self.assertRaises(SystemExit):
            agl.app.server.check_ollama_service("http://127.0.0.1:11434", ports=fake_ports, out=out)
        fake_ports.sys.exit.assert_called_with(1)
        calls = [c[0][0] for c in out.call_args_list]
        self.assertTrue(any("Ollama is not installed" in msg for msg in calls))


if __name__ == "__main__":
    unittest.main()
