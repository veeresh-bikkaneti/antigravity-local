"""Tests for agl/app/homeport.py (Homeport slice 1). SimpleNamespace ports with fakes only."""

import json
import types
import unittest

from agl.app import homeport


class FakeOllama:
    def __init__(self, up, rows):
        self._up = up
        self._rows = rows

    def check_service(self, base_url=None):
        return self._up

    def loaded_models(self, base_url=None, *, timeout=3, get_json=None):
        return list(self._rows)

    def installed_details(self, base_url=None, opener=None, timeout=3):
        return {}


class FakeGpu:
    def read_gpu(self, check_output=None, which=None, on_wsl=None):
        return {"util_pct": 10.0, "vram_used_mb": 1.0, "vram_total_mb": 2.0,
                "temp_c": 3.0, "power_w": 4.0, "source": "nvidia-smi"}


class FakeStore:
    def __init__(self, saved=None):
        self._saved = saved or {}

    def load(self, path=None):
        return dict(self._saved)

    def save(self, values, path=None):
        pass


def _ports(up, rows, saved=None):
    return types.SimpleNamespace(ollama=FakeOllama(up, rows), gpu=FakeGpu(), store=FakeStore(saved))


def _row(size=100, size_vram=100):
    return {"name": "m", "size": size, "size_vram": size_vram,
            "context_length": 8192, "expires_at": "2026-01-01T00:00:00Z"}


class TestSnapshot(unittest.TestCase):
    def _check(self, up, rows, expected_state, saved=None):
        snap = homeport.snapshot(_ports(up, rows, saved))
        self.assertEqual(snap["state"], expected_state)
        self.assertEqual(snap["service_up"], up)
        json.dumps(snap)  # must be JSON-safe
        self.assertEqual(set(snap), {"state", "service_up", "model", "vram",
                                     "context_fill", "gpu", "settings", "captions"})
        self.assertTrue(snap["captions"])
        return snap

    def test_stopped(self):
        self._check(False, [], "STOPPED")

    def test_unloaded(self):
        self._check(True, [], "UNLOADED")

    def test_loading(self):
        snap = self._check(True, [_row(size=100, size_vram=0)], "LOADING")
        self.assertEqual(snap["vram"], {"gpu_pct": 0, "spills": True})

    def test_idle_fits(self):
        snap = self._check(True, [_row()], "IDLE")
        self.assertEqual(snap["vram"], {"gpu_pct": 100, "spills": False})
        self.assertEqual(snap["model"]["name"], "m")

    def test_settings_merged_from_store(self):
        snap = self._check(True, [], "UNLOADED", saved={"theme": "dark", "nope": 1})
        self.assertEqual(snap["settings"]["theme"], "dark")
        self.assertNotIn("nope", snap["settings"])


if __name__ == "__main__":
    unittest.main()
