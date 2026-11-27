"""C1b PR A: the window this GPU can hold, the /api/show read, and stage 4's target (docs/mockups/real-window.md)."""

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import agent_setup as ags  # noqa: E402

from agl.core import window_fit as fit  # noqa: E402
from agl.platform import ollama  # noqa: E402

GIB = 2 ** 30
QWEN = {"general.architecture": "qwen2", "qwen2.block_count": 48, "qwen2.attention.head_count": 40,
        "qwen2.attention.head_count_kv": 8, "qwen2.embedding_length": 5120, "qwen2.context_length": 131072}


class KvBytesTests(unittest.TestCase):
    def test_qwen_shape_from_the_mockup(self):
        self.assertEqual(fit.kv_bytes_per_token(QWEN), 196608)  # 48 x 8 x (128 + 128) x 2

    def test_gemma_two_check_from_llama_cpp(self):
        info = {"general.architecture": "gemma2", "gemma2.block_count": 42, "gemma2.attention.head_count_kv": 8,
                "gemma2.attention.key_length": 256, "gemma2.attention.value_length": 256}
        self.assertEqual(fit.kv_bytes_per_token(info) * 3072, 1008 * 2 ** 20)  # 1008 MiB at 3072 tokens

    def test_per_layer_heads_are_summed(self):
        info = dict(QWEN, **{"qwen2.block_count": 2, "qwen2.attention.head_count_kv": [8, 4]})
        self.assertEqual(fit.kv_bytes_per_token(info), 12 * 256 * 2)

    def test_cache_type(self):
        self.assertEqual(fit.kv_bytes_per_token(QWEN, "q8_0"), 196608 * 1.0625 / 2)
        self.assertEqual(fit.kv_bytes_per_token(QWEN, "Q4_0 "), 196608 * 0.5625 / 2)
        self.assertIsNone(fit.kv_bytes_per_token(QWEN, "f8"))

    def test_missing_shape(self):
        for info in (None, {}, {"general.architecture": "qwen2"},
                     dict(QWEN, **{"qwen2.block_count": True}), dict(QWEN, **{"qwen2.attention.head_count_kv": [8, "x"]})):
            self.assertIsNone(fit.kv_bytes_per_token(info), repr(info))


class TargetTests(unittest.TestCase):
    def target(self, card_gib, weights_gib=9.0, loaded=0):
        room = fit.room_gib(card_gib, weights_gib * GIB, loaded)
        return fit.target_window(room, fit.kv_bytes_per_token(QWEN), 131072)

    def test_the_mockup_table(self):
        self.assertEqual(self.target(8), 0)
        self.assertEqual(self.target(12), 0)  # room 1.2 < 1.5
        self.assertEqual(self.target(16), 16384)
        self.assertEqual(self.target(24), 64000)  # 65536 fits, then the 64000 cap

    def test_decimal_gb_fork(self):
        self.assertEqual(self.target(12, weights_gib=9e9 / GIB), 8192)  # the inferred fork in section 4

    def test_loaded_model_is_not_counted_twice(self):
        self.assertEqual(self.target(7.0, loaded=9 * GIB), self.target(16))  # 7 free + 9 already in use = 16

    def test_trained_max_caps_the_rung(self):
        room = fit.room_gib(24, 9 * GIB)
        self.assertEqual(fit.target_window(room, fit.kv_bytes_per_token(QWEN), 32768), 32768)
        self.assertEqual(fit.target_window(room, fit.kv_bytes_per_token(QWEN), 4096), 0)

    def test_missing_readings(self):
        self.assertIsNone(fit.room_gib(None, GIB))
        self.assertIsNone(fit.room_gib(16, None))
        self.assertIsNone(fit.room_gib(True, GIB))
        self.assertIsNone(fit.target_window(None, 100))
        self.assertIsNone(fit.target_window(5.0, None))

    def test_copy_name(self):
        for tokens, name in ((8192, "m-ctx8k"), (16384, "m-ctx16k"), (32768, "m-ctx32k"), (64000, "m-ctx64k")):
            self.assertEqual(fit.copy_name("m", tokens), name)


class ShowTests(unittest.TestCase):
    def test_returns_the_dict(self):
        with mock.patch.object(ollama.http, "get_json", return_value={"parameters": "num_ctx 8192"}) as get:
            self.assertEqual(ollama.show("demo:1b", "http://x/"), {"parameters": "num_ctx 8192"})
        self.assertEqual(get.call_args.args[0], "http://x/api/show")

    def test_none_on_error_or_junk(self):
        with mock.patch.object(ollama.http, "get_json", side_effect=OSError("refused")):
            self.assertIsNone(ollama.show("demo:1b"))
        with mock.patch.object(ollama.http, "get_json", return_value=["not", "a", "dict"]):
            self.assertIsNone(ollama.show("demo:1b"))


class WindowTargetTests(unittest.TestCase):
    def run_target(self, free, known=True, size=9 * GIB, rows=()):
        with mock.patch.object(ags.ollama, "show", return_value={"model_info": QWEN}), \
                mock.patch.object(ags.ollama, "installed_info", return_value={"qwen2.5:14b": {"size_gb": size / 1e9}}), \
                mock.patch.object(ags.ollama_live, "loaded_models", return_value=list(rows)), \
                mock.patch.object(ags.hardware, "get_free_vram_gb", return_value=(free, known)):
            return ags.window_target("qwen2.5:14b", "", {})

    def test_sixteen_gib_card(self):
        self.assertEqual(self.run_target(16.0), (16384, 131072))

    def test_unknown_gpu_gives_no_target(self):
        self.assertEqual(self.run_target(0.0, known=False), (None, 131072))

    def test_loaded_model_adds_its_share_back(self):
        rows = [{"name": "qwen2.5:14b", "size_vram": int(9 * GIB)}, {"name": "other:1b", "size_vram": int(4 * GIB)}]
        self.assertEqual(self.run_target(7.0, rows=rows), (16384, 131072))


if __name__ == "__main__":
    unittest.main()
