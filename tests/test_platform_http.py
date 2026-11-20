"""Narrow tests for the platform HTTP helper: the timeout the caller passes reaches the open
call, a redirect to another host is refused, and a reply whose body is not JSON raises
ValueError. Offline: every reply is a fake; nothing opens a socket."""
import sys
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from agl.platform import http  # noqa: E402


class _Reply:
    """The smallest context-manager reply: a byte body and a status, nothing else."""

    def __init__(self, body=b"{}"):
        self._body = body
        self.status = 200

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class GetJson(unittest.TestCase):
    def test_the_timeout_the_caller_passes_reaches_the_open_call(self):
        seen = []

        def fake_urlopen(request, timeout=None):
            seen.append(timeout)
            return _Reply()

        with mock.patch.object(http, "_urlopen", fake_urlopen):
            http.get_json("http://127.0.0.1:11434/api/tags", timeout=7)
            http.get_json("http://127.0.0.1:11434/v1/models", timeout=0.5)
        self.assertEqual(seen, [7, 0.5])

    def test_a_reply_whose_body_is_not_json_raises_value_error(self):
        fake = lambda request, timeout=None: _Reply(b"<html>not json</html>")  # noqa: E731
        with mock.patch.object(http, "_urlopen", fake):
            with self.assertRaises(ValueError):
                http.get_json("http://127.0.0.1:11434/api/tags", timeout=3)


class SameHostOnly(unittest.TestCase):
    def _redirect(self, newurl):
        handler = http._SameHostOnly()
        req = urllib.request.Request("https://registry.ollama.ai/v2/library/llama/manifests/latest")
        return handler.redirect_request(req, None, 302, "Found", {}, newurl)

    def test_a_redirect_to_another_host_is_refused(self):
        self.assertIsNone(self._redirect("https://evil.example/v2/library/llama/manifests/latest"))

    def test_a_redirect_to_the_same_host_is_followed(self):
        self.assertIsNotNone(self._redirect("https://registry.ollama.ai/v2/llama/manifests/latest"))


if __name__ == "__main__":
    unittest.main()
