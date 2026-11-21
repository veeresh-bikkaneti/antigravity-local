"""Tests for agl/core/usage.py (Homeport slice 1). Pure functions; no I/O."""

import re
import unittest

from agl.core import usage


class TestVramSplit(unittest.TestCase):
    def test_fits_fully(self):
        self.assertEqual(usage.vram_split(1000, 1000), {"gpu_pct": 100, "spills": False})

    def test_spills(self):
        self.assertEqual(usage.vram_split(1000, 500), {"gpu_pct": 50, "spills": True})

    def test_zero_size(self):
        self.assertEqual(usage.vram_split(0, 0), {"gpu_pct": 0, "spills": False})
        self.assertEqual(usage.vram_split(0, 500), {"gpu_pct": 0, "spills": False})


class TestContextFill(unittest.TestCase):
    def test_none_or_bad_context(self):
        self.assertIsNone(usage.context_fill(10, None))
        self.assertIsNone(usage.context_fill(10, 0))
        self.assertIsNone(usage.context_fill(10, -5))

    def test_value_and_clamps(self):
        self.assertEqual(usage.context_fill(50, 100), 50)
        self.assertEqual(usage.context_fill(200, 100), 100)
        self.assertEqual(usage.context_fill(None, 100), 0)


class TestState(unittest.TestCase):
    def test_stopped(self):
        self.assertEqual(usage.state(False, None), "STOPPED")
        self.assertEqual(usage.state(False, {"size": 1, "size_vram": 1}), "STOPPED")

    def test_unloaded(self):
        self.assertEqual(usage.state(True, None), "UNLOADED")
        self.assertEqual(usage.state(True, []), "UNLOADED")

    def test_loading(self):
        self.assertEqual(usage.state(True, {"size": 100, "size_vram": 0}), "LOADING")

    def test_idle(self):
        self.assertEqual(usage.state(True, {"size": 100, "size_vram": 100}), "IDLE")
        self.assertEqual(usage.state(True, {"size": 100, "size_vram": 40}), "IDLE")

    def test_gen_defined_but_never_returned(self):
        self.assertEqual(usage.GEN, "GEN")
        for up in (True, False):
            for loaded in (None, [], {}, {"size": 1, "size_vram": 0}, {"size": 1, "size_vram": 1}):
                self.assertNotEqual(usage.state(up, loaded), usage.GEN)


class TestCaptions(unittest.TestCase):
    def _snap(self, st, spills=False):
        return {"state": st, "vram": {"gpu_pct": 100, "spills": spills}}

    def test_every_state_covered_without_digits(self):
        snaps = [self._snap("STOPPED"), self._snap("UNLOADED"), self._snap("LOADING"),
                 self._snap("IDLE", spills=False), self._snap("IDLE", spills=True)]
        for snap in snaps:
            caps = usage.captions(snap)
            self.assertTrue(caps, snap)
            for cap in caps:
                self.assertIsNone(re.search(r"[0-9]", cap), cap)
                self.assertIsNone(re.search(r"[0-9]\s*(GB|%)", cap, re.IGNORECASE), cap)

    def test_fit_and_spill_wording(self):
        self.assertIn("The model fits on your graphics card.", usage.captions(self._snap("IDLE")))
        spills = usage.captions(self._snap("IDLE", spills=True))
        self.assertTrue(any("spills into system memory" in c for c in spills))


if __name__ == "__main__":
    unittest.main()
