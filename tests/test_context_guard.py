import unittest

from agl.core.context_guard import band, real_window


def row(name, context_length):
    return {"name": name, "size": 1, "size_vram": 1, "context_length": context_length, "expires_at": None}


class LoadedWindowTests(unittest.TestCase):
    def test_loaded_rows_report_their_context(self):
        rows = [row("demo:1b", 8192), row("demo:2b", 16384), row("demo:3b", 32768), row("demo:4b", 65536)]
        self.assertEqual(real_window(rows, "demo:1b", None, 8), (8192, "loaded"))
        self.assertEqual(real_window(rows, "demo:2b", None, 8), (16384, "loaded"))
        self.assertEqual(real_window(rows, "demo:3b", None, 8), (32768, "loaded"))
        self.assertEqual(real_window(rows, "demo:4b", None, 8), (65536, "loaded"))

    def test_missing_model_falls_through_to_default(self):
        rows = [row("demo:1b", 8192)]
        self.assertEqual(real_window(rows, "demo:9b", None, 24), (32768, "default"))

    def test_ollama_down_uses_env_then_default(self):
        self.assertEqual(real_window([], "demo:1b", "8192", 8), (8192, "env"))
        self.assertEqual(real_window([], "demo:1b", None, 8), (4096, "default"))

    def test_latest_tag_matches_bare_name_both_ways(self):
        self.assertEqual(real_window([row("demo", 8192)], "demo:latest", None, 8), (8192, "loaded"))
        self.assertEqual(real_window([row("demo:latest", 8192)], "demo", None, 8), (8192, "loaded"))

    def test_other_tags_do_not_match(self):
        self.assertEqual(real_window([row("demo:1b", 8192)], "demo", None, 8), (4096, "default"))

    def test_first_usable_matching_row_wins(self):
        rows = [row("demo:1b", None), row("demo:1b", 8192), row("demo:1b", 16384)]
        self.assertEqual(real_window(rows, "demo:1b", None, 8), (8192, "loaded"))

    def test_junk_rows_and_values_are_ignored(self):
        junk = [
            row("demo:1b", True),
            row("demo:1b", "8192"),
            row("demo:1b", 0),
            row("demo:1b", -5),
            row("demo:1b", None),
            row("demo:1b", 8.5),
            "demo:1b",
            None,
            {"name": None, "context_length": 8192},
        ]
        self.assertEqual(real_window(junk, "demo:1b", None, 8), (4096, "default"))

    def test_non_list_rows_never_raise(self):
        for rows in (None, "demo:1b", {"name": "demo:1b", "context_length": 8192}, 42):
            self.assertEqual(real_window(rows, "demo:1b", None, 8), (4096, "default"))


class EnvWindowTests(unittest.TestCase):
    def test_plain_positive_integer_is_used(self):
        self.assertEqual(real_window([], "demo:1b", " 2048 ", 8), (2048, "env"))

    def test_everything_else_falls_through(self):
        for env in ("0", "-1", "abc", "", "²", "8192.0", None, 8192):
            self.assertEqual(real_window([], "demo:1b", env, 8), (4096, "default"), repr(env))


class VramDefaultTests(unittest.TestCase):
    def test_below_24_gib_is_small(self):
        self.assertEqual(real_window([], "demo:1b", None, 23.9), (4096, "default"))

    def test_24_up_to_48_gib_is_medium(self):
        self.assertEqual(real_window([], "demo:1b", None, 24), (32768, "default"))
        self.assertEqual(real_window([], "demo:1b", None, 47.9), (32768, "default"))

    def test_48_gib_and_up_is_large(self):
        self.assertEqual(real_window([], "demo:1b", None, 48), (262144, "default"))
        self.assertEqual(real_window([], "demo:1b", None, 80), (262144, "default"))

    def test_junk_vram_counts_as_small(self):
        for vram in (None, "48", True, float("nan"), float("inf"), []):
            self.assertEqual(real_window([], "demo:1b", None, vram), (4096, "default"), repr(vram))


class BandTests(unittest.TestCase):
    def test_band_edges(self):
        self.assertEqual(band(16383), "red")
        self.assertEqual(band(16384), "amber")
        self.assertEqual(band(65535), "amber")
        self.assertEqual(band(65536), "green")


if __name__ == "__main__":
    unittest.main()
