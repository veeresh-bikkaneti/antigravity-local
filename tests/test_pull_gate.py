import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pull_gate import ask_pull, check_disk  # noqa: E402


def plan(**kw):
    base = {"tag": "hf.co/u/r:Q4_K_M", "quant": "Q4_K_M", "size_gb": 1.0, "license": "apache-2.0",
            "gated": False, "free_disk_gb": 500.0, "disk_total_gb": 1000.0}
    return {**base, **kw}


def run(answer, p=None, interactive=True):
    lines, calls = [], []

    def inp(prompt):
        calls.append(prompt)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    return ask_pull(p or plan(), interactive, inp, lines.append), "\n".join(lines), calls


class CheckDisk(unittest.TestCase):
    def test_exactly_ten_percent_passes(self):
        self.assertTrue(check_disk(plan(free_disk_gb=110.0, size_gb=10.0, disk_total_gb=1000.0))[0])

    def test_one_byte_under_refuses(self):
        self.assertFalse(check_disk(plan(free_disk_gb=110.0 - 1e-9, size_gb=10.0, disk_total_gb=1000.0))[0])


class AskPull(unittest.TestCase):
    def test_only_y_downloads(self):
        for a in ("y", "Y", "yes", "YES"):
            self.assertEqual(run(a)[0], "yes", a)
        for a in ("", "n", "N", "no", "junk", EOFError()):
            self.assertEqual(run(a)[0], "no", repr(a))

    def test_ctrl_c_propagates(self):
        with self.assertRaises(KeyboardInterrupt):
            run(KeyboardInterrupt())

    def test_non_interactive_never_asks(self):
        result, _, calls = run("y", interactive=False)
        self.assertEqual((result, calls), ("non_interactive", []))

    def test_every_size_asks(self):
        self.assertEqual(len(run("n", plan(size_gb=1.0))[2]), 1)

    def test_gated_prints_repo_page(self):
        result, text, calls = run("y", plan(gated=True))
        self.assertEqual(result, "gated")
        self.assertIn("https://huggingface.co/u/r", text)
        self.assertEqual(calls, [])

    def test_disk_refused_before_asking(self):
        result, _, calls = run("y", plan(free_disk_gb=5.0))
        self.assertEqual((result, calls), ("disk_refused", []))

    def test_non_commercial_flagged(self):
        for lic in ("CC-BY-NC-4.0", "Non-Commercial research only"):
            self.assertIn("NON-COMMERCIAL", run("n", plan(license=lic))[1])
        self.assertNotIn("NON-COMMERCIAL", run("n")[1])

    def test_unknown_license(self):
        self.assertIn("license: unknown", run("n", plan(license=None))[1])


class Hostile(unittest.TestCase):
    def test_odd_plan_values_do_not_crash(self):
        got, shown, _ = run("n", plan(license=5, quant=None, size_gb=None))
        self.assertEqual(got, "no")
        self.assertIn("quant: unknown", shown)

    def test_missing_disk_fields_refuse_instead_of_crashing(self):
        got, _, calls = run("y", {"tag": "x", "quant": "Q4_K_M", "size_gb": 1.0})
        self.assertEqual((got, calls), ("disk_refused", []))


class UnknownNumbers(unittest.TestCase):
    def test_an_unknown_size_is_said_out_loud_not_printed_as_zero(self):
        got, shown, _ = run("n", plan(size_gb=None))
        self.assertEqual(got, "no")
        self.assertIn("size: unknown", shown)
        self.assertNotIn("0.0 GB", shown)

    def test_an_unreadable_disk_says_so_instead_of_printing_nonsense(self):
        got, shown, calls = run("y", plan(free_disk_gb=0, disk_total_gb=0))
        self.assertEqual((got, calls), ("disk_refused", []))
        self.assertIn("Could not read the free disk space", shown)
        self.assertNotIn("-", shown.replace("non-commercial", ""))


if __name__ == "__main__":
    unittest.main()
