"""Tests for agl/core/homeport_settings.py (Homeport slice 1). Pure validation; no I/O."""

import unittest

from agl.core import homeport_settings as hs


class TestDefaults(unittest.TestCase):
    def test_expected_keys_and_values(self):
        self.assertEqual(hs.DEFAULTS, {
            "start": "demand", "port": "auto", "keep": "5m", "context": None,
            "refresh_s": 1, "first_drawer": "island", "motion": "auto", "theme": "auto",
            "alert_context_pct": 85, "alert_gpu_c": 84, "alert_spill": "on",
            "log_days": 14, "record_prompts": "off", "metrics_export": "off",
        })


class TestValidate(unittest.TestCase):
    def test_each_default_is_accepted(self):
        for key, raw in hs.DEFAULTS.items():
            ok, value = hs.validate(key, raw)
            self.assertTrue(ok, (key, value))
            self.assertEqual(value, raw)

    def test_rejects_bad_values(self):
        bad = [
            ("port", "abc"), ("port", 0), ("port", 70000), ("port", True),
            ("refresh_s", 0.1), ("refresh_s", 11), ("refresh_s", "1"),
            ("theme", "blue"), ("theme", True),
            ("alert_context_pct", 0), ("alert_context_pct", 101),
            ("alert_gpu_c", 29), ("alert_gpu_c", 111),
            ("log_days", 0), ("log_days", 366),
            ("record_prompts", "yes"), ("record_prompts", True),
            ("keep", "5x"), ("keep", "m"), ("context", -3), ("context", 0),
            ("start", "never"), ("first_drawer", "side"), ("motion", "maybe"),
            ("alert_spill", "yes"), ("metrics_export", 1),
            ("no_such_key", 1),
        ]
        for key, raw in bad:
            ok, err = hs.validate(key, raw)
            self.assertFalse(ok, (key, raw))
            self.assertIsInstance(err, str)

    def test_accepts_good_values(self):
        good = [("port", 8080), ("refresh_s", 0.5), ("refresh_s", 10), ("keep", "30s"),
                ("context", 4096), ("theme", "dark"), ("log_days", 365), ("start", "boot")]
        for key, raw in good:
            ok, value = hs.validate(key, raw)
            self.assertTrue(ok, (key, raw))
            self.assertEqual(value, raw)


class TestMerge(unittest.TestCase):
    def test_merge_keeps_valid_and_drops_the_rest(self):
        merged = hs.merge({"theme": "dark", "log_days": 999, "bogus": 1, "port": 9000})
        self.assertEqual(merged["theme"], "dark")
        self.assertEqual(merged["port"], 9000)
        self.assertEqual(merged["log_days"], hs.DEFAULTS["log_days"])
        self.assertNotIn("bogus", merged)
        self.assertEqual(set(merged), set(hs.DEFAULTS))

    def test_merge_empty_and_non_dict(self):
        self.assertEqual(hs.merge({}), dict(hs.DEFAULTS))
        self.assertEqual(hs.merge(None), dict(hs.DEFAULTS))
        self.assertEqual(hs.merge([1, 2]), dict(hs.DEFAULTS))


if __name__ == "__main__":
    unittest.main()
