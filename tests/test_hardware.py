"""Free VRAM, free RAM and free disk, with every probe faked: no GPU, no powershell, no real disk needed."""
import os
import sys
import tempfile
import unittest
from collections import namedtuple
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import hardware  # noqa: E402
from agl.platform import hardware as platform_hardware  # noqa: E402
platform_hw = platform_hardware
hardware.shutil = platform_hardware.shutil


def smi(text=None, raises=False):
    """Fake nvidia-smi: shutil.which finds it, check_output prints `text` (or raises)."""
    def fake(cmd, **kw):
        if raises:
            raise OSError("boom")
        return text
    return mock.patch.multiple(platform_hardware.subprocess, check_output=fake), mock.patch.object(
        hardware.shutil, "which", return_value="nvidia-smi")


class FreeVram(unittest.TestCase):
    def free(self, text=None, raises=False):
        a, b = smi(text, raises)
        with a, b:
            return hardware.get_free_vram_gb()

    def test_reads_mib_as_gb(self):
        self.assertEqual(self.free("16048\n"), (16048 / 1024, True))

    def test_zero_free_vram_is_known_but_empty(self):
        self.assertEqual(self.free("0\n"), (0.0, True))

    def test_two_gpus_use_the_one_with_most_free_memory(self):
        free, known = self.free("2000\n10240\n")
        self.assertEqual((free, known), (10.0, True))

    def test_junk_output_is_unknown(self):
        self.assertEqual(self.free("N/A\nnot a number\n"), (0.0, False))

    def test_nvidia_smi_failing_is_unknown(self):
        self.assertEqual(self.free(raises=True), (0.0, False))

    def test_nvidia_smi_missing_is_unknown(self):
        with mock.patch.object(platform_hw.shutil, "which", return_value=None), \
                mock.patch.object(platform_hw.sys, "platform", "linux"):
            self.assertEqual(hardware.get_free_vram_gb(), (0.0, False))

    def test_apple_unified_memory_uses_free_ram(self):
        with mock.patch.object(platform_hw.shutil, "which", return_value=None), \
                mock.patch.object(platform_hw.sys, "platform", "darwin"), \
                mock.patch.object(platform_hardware, "get_free_ram_gb", return_value=20.0):
            self.assertEqual(hardware.get_free_vram_gb(), (20.0, True))


class Profile(unittest.TestCase):
    def test_total_vram_and_name_still_come_from_nvidia_smi(self):
        a, b = smi("NVIDIA RTX 5000 Ada, 16376\n")
        with a, b, mock.patch.object(platform_hardware, "get_system_ram_gb", return_value=128.0):
            p = hardware.get_hardware_profile()
        self.assertEqual((p["gpu_name"], round(p["vram_gb"], 2), p["ram_gb"]), ("NVIDIA RTX 5000 Ada", 15.99, 128.0))

    def test_no_gpu_is_cpu_only(self):
        with mock.patch.object(platform_hw.shutil, "which", return_value=None), \
                mock.patch.object(platform_hw.sys, "platform", "linux"), \
                mock.patch.object(platform_hardware, "get_system_ram_gb", return_value=16.0):
            self.assertEqual(hardware.get_hardware_profile(), {"ram_gb": 16.0, "vram_gb": 0.0, "gpu_name": "CPU Only"})


class ModelsDir(unittest.TestCase):
    def test_ollama_models_wins(self):
        self.assertEqual(hardware.ollama_models_dir({"OLLAMA_MODELS": "D:/models"}, "/h"), "D:/models")

    def test_default_is_dot_ollama_models_under_home(self):
        self.assertEqual(hardware.ollama_models_dir({}, "/h"), os.path.join("/h", ".ollama", "models"))

    def test_blank_override_falls_back(self):
        self.assertEqual(hardware.ollama_models_dir({"OLLAMA_MODELS": "  "}, "/h"), os.path.join("/h", ".ollama", "models"))


class Disk(unittest.TestCase):
    def test_walks_up_to_a_folder_that_exists(self):
        Usage = namedtuple("Usage", "total used free")
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(platform_hw.shutil, "disk_usage", return_value=Usage(1000 * 1024 ** 3, 0, 250 * 1024 ** 3)) as du:
            free, total = hardware.free_disk_gb(os.path.join(d, "not", "made", "yet"))
        self.assertEqual((free, total), (250.0, 1000.0))
        self.assertEqual(du.call_args[0][0], os.path.abspath(d))

    def test_unreadable_disk_is_unknown(self):
        with mock.patch.object(platform_hw.shutil, "disk_usage", side_effect=OSError):
            self.assertEqual(hardware.free_disk_gb(tempfile.gettempdir()), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
