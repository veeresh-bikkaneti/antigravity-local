"""Tests for agl/platform/ollama_live.py (Homeport slice 1). Fake get_json only; no real server."""

import unittest

from agl.platform import ollama_live


def _fake_get_json(payload):
    def get_json(url, *, timeout, **kwargs):
        get_json.seen_url = url
        return payload
    return get_json


class TestLoadedModels(unittest.TestCase):
    def test_rows_become_five_key_dicts(self):
        payload = {"models": [{"name": "m", "size": 100, "size_vram": 100,
                               "context_length": 8192, "expires_at": "2026-01-01T00:00:00Z", "extra": 1}]}
        get_json = _fake_get_json(payload)
        rows = ollama_live.loaded_models("http://host:1/", get_json=get_json)
        self.assertEqual(get_json.seen_url, "http://host:1/api/ps")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], {"name": "m", "size": 100, "size_vram": 100,
                                   "context_length": 8192, "expires_at": "2026-01-01T00:00:00Z"})

    def test_error_returns_empty(self):
        def boom(url, *, timeout, **kwargs):
            raise RuntimeError("server down")
        self.assertEqual(ollama_live.loaded_models(get_json=boom), [])

    def test_bad_payloads_return_empty(self):
        self.assertEqual(ollama_live.loaded_models(get_json=_fake_get_json({})), [])
        self.assertEqual(ollama_live.loaded_models(get_json=_fake_get_json({"models": "x"})), [])
        self.assertEqual(ollama_live.loaded_models(get_json=_fake_get_json([1, 2])), [])

    def test_empty_models_list(self):
        self.assertEqual(ollama_live.loaded_models(get_json=_fake_get_json({"models": []})), [])


if __name__ == "__main__":
    unittest.main()
