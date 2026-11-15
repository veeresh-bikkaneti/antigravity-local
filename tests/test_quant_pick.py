import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from quant_pick import pick_quant, quant_of  # noqa: E402


def gguf(quant, gb):
    return {"name": f"m-{quant}.gguf", "size": None if gb is None else int(gb * 1e9)}


LADDER = [gguf("Q8_0", 14.1), gguf("Q6_K", 11.9), gguf("Q5_K_M", 10.2), gguf("Q4_K_M", 8.5),
          gguf("Q3_K_M", 6.9), gguf("Q2_K", 5.4)]


class PickQuant(unittest.TestCase):
    def test_16gb_free_vram_picks_largest_under_13_3(self):
        got = pick_quant(LADDER, 16, 0)
        self.assertEqual((got["quant"], got["fit"], got["estimated"]), ("Q6_K", "gpu", False))

    def test_cpu_only_split_fit(self):
        got = pick_quant(LADDER, 0, 128)
        self.assertEqual((got["quant"], got["fit"]), ("Q8_0", "split"))
        self.assertIn("slow", got["why"])

    def test_split_files_sum(self):
        parts = [{"name": f"big-Q4_K_M-0000{i}-of-00003.gguf", "size": 3 * 10**9} for i in (1, 2, 3)]
        got = pick_quant(parts, 16, 0)
        self.assertEqual(got["quant"], "Q4_K_M")
        self.assertAlmostEqual(got["size_gb"], 9.0)

    def test_missing_size_is_estimated(self):
        got = pick_quant([gguf("Q8_0", 8.5), gguf("Q4_K_M", None)], 16, 0, wanted="q4_k_m")
        self.assertTrue(got["estimated"])
        self.assertAlmostEqual(got["size_gb"], 4.5)

    def test_no_sized_file_means_unusable(self):
        self.assertIsNone(pick_quant([gguf("Q4_K_M", None)], 16, 0))

    def test_sub_q3_skipped_unless_wanted(self):
        low = [gguf("Q2_K", 3.0), gguf("IQ2_XS", 2.5)]
        self.assertIsNone(pick_quant(low, 16, 0))
        self.assertEqual(pick_quant(low, 16, 0, wanted="Q2_K")["quant"], "Q2_K")

    def test_nothing_free_gives_none(self):
        self.assertIsNone(pick_quant(LADDER, 0, 0))

    def test_too_big_wanted_is_reported(self):
        self.assertEqual(pick_quant(LADDER, 8, 0, wanted="Q8_0")["fit"], "too big")

    def test_mmproj_and_imatrix_ignored(self):
        extra = [{"name": "mmproj-F16.gguf", "size": 10**9}, {"name": "m-imatrix-Q4_K_M.gguf", "size": 1}]
        self.assertIsNone(pick_quant(extra, 16, 0))


class QuantOf(unittest.TestCase):
    def test_names(self):
        self.assertEqual(quant_of("Llama-3.1-8B-q4_k_m.gguf"), "Q4_K_M")
        self.assertEqual(quant_of("m-BF16-00001-of-00002.gguf"), "BF16")
        self.assertIsNone(quant_of("README.md"))


if __name__ == "__main__":
    unittest.main()
