"""Tests for agl/platform/gpu.py (Homeport slice 1). Fake check_output/which only; no real GPU."""

import subprocess
import unittest

from agl.platform import gpu


def _which_ok(name):
    return f"/usr/bin/{name}"


def _none_out():
    return {"util_pct": None, "vram_used_mb": None, "vram_total_mb": None,
            "temp_c": None, "power_w": None, "source": "none"}


class TestReadGpu(unittest.TestCase):
    def test_parse_csv_line(self):
        seen = {}

        def fake_check_output(cmd, **kwargs):
            seen["cmd"] = cmd
            seen["kwargs"] = kwargs
            return "75, 4096, 16376, 62, 120.5\n"

        out = gpu.read_gpu(check_output=fake_check_output, which=_which_ok, on_wsl=False)
        self.assertEqual(out["util_pct"], 75.0)
        self.assertEqual(out["vram_used_mb"], 4096.0)
        self.assertEqual(out["vram_total_mb"], 16376.0)
        self.assertEqual(out["temp_c"], 62.0)
        self.assertEqual(out["power_w"], 120.5)
        self.assertEqual(out["source"], "nvidia-smi")
        self.assertEqual(seen["cmd"][0], "nvidia-smi")
        self.assertIn(gpu.NVIDIA_SMI_FIELDS, seen["cmd"][1])
        self.assertEqual(seen["kwargs"].get("timeout"), 10)
        self.assertTrue(seen["kwargs"].get("text"))

    def test_wsl_uses_exe_binary(self):
        seen = {}

        def fake_check_output(cmd, **kwargs):
            seen["cmd"] = cmd
            return "1, 2, 3, 4, 5"

        out = gpu.read_gpu(check_output=fake_check_output, which=_which_ok, on_wsl=True)
        self.assertTrue(seen["cmd"][0].endswith("nvidia-smi.exe"))
        self.assertEqual(out["source"], "nvidia-smi.exe")
        self.assertEqual(out["util_pct"], 1.0)

    def test_no_binary_gives_none_source_none(self):
        out = gpu.read_gpu(check_output=lambda *a, **k: "", which=lambda name: None, on_wsl=False)
        self.assertEqual(out, _none_out())

    def test_junk_output_gives_all_none(self):
        out = gpu.read_gpu(check_output=lambda *a, **k: "junk", which=_which_ok, on_wsl=False)
        for key in ("util_pct", "vram_used_mb", "vram_total_mb", "temp_c", "power_w"):
            self.assertIsNone(out[key])
        self.assertEqual(out["source"], "nvidia-smi")

    def test_partial_junk_fields_become_none(self):
        out = gpu.read_gpu(check_output=lambda *a, **k: "N/A, 4096", which=_which_ok, on_wsl=False)
        self.assertIsNone(out["util_pct"])
        self.assertEqual(out["vram_used_mb"], 4096.0)
        self.assertIsNone(out["vram_total_mb"])

    def test_timeout_never_raises(self):
        def boom(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=10)

        out = gpu.read_gpu(check_output=boom, which=_which_ok, on_wsl=False)
        for key in ("util_pct", "vram_used_mb", "vram_total_mb", "temp_c", "power_w"):
            self.assertIsNone(out[key])

    def test_raising_which_never_raises(self):
        def bad_which(name):
            raise RuntimeError("boom")

        self.assertEqual(gpu.read_gpu(check_output=lambda *a, **k: "", which=bad_which), _none_out())


if __name__ == "__main__":
    unittest.main()
