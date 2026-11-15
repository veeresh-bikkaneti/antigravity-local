"""The fail ledger: append-only, latest entry wins, never raises, never touches the real home."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ledger  # noqa: E402

T0 = 1_800_000_000.0  # a fixed clock: 2027-01-15


class Ledger(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def add(self, ref, verdict, reason="r", now=T0, **kw):
        return ledger.append(ref, verdict, reason, home=self.home, env={}, now=now, host="box", **kw)

    def entries(self):
        return ledger.read(home=self.home, env={})

    def test_one_compact_line_per_entry_with_the_spec_fields(self):
        self.assertEqual(self.add("qwen3:8b", "fail", "no tool call", evidence_key="e1"), (True, ""))
        raw = ledger.ledger_path(self.home, {}).read_text(encoding="utf-8")
        self.assertEqual(raw.count("\n"), 1)
        self.assertNotIn(", ", raw)  # compact separators
        item = json.loads(raw)
        self.assertEqual(list(item), ["timestampUtc", "host", "modelRef", "runtime", "harness", "evidenceKey", "reason", "verdict"])
        self.assertEqual((item["host"], item["modelRef"], item["runtime"], item["harness"], item["verdict"]),
                         ("box", "qwen3:8b", "ollama", "probe", "fail"))
        self.assertTrue(item["timestampUtc"].endswith("Z") and item["timestampUtc"].startswith("2027-01-15"))

    def test_evidence_key_is_left_out_when_not_given(self):
        self.add("a:1", "pass")
        self.assertNotIn("evidenceKey", self.entries()[0])

    def test_reason_is_capped_at_500_characters(self):
        self.add("a:1", "fail", "x" * 900)
        self.assertEqual(len(self.entries()[0]["reason"]), 500)

    def test_appending_never_rewrites_earlier_lines(self):
        self.add("a:1", "fail", "first")
        before = ledger.ledger_path(self.home, {}).read_text(encoding="utf-8")
        self.add("a:1", "pass", "second")
        after = ledger.ledger_path(self.home, {}).read_text(encoding="utf-8")
        self.assertTrue(after.startswith(before))
        self.assertEqual(len(self.entries()), 2)

    def test_status_latest_entry_wins_and_no_entry_is_unproven(self):
        self.assertEqual(ledger.status("a:1", self.entries()), "unproven")
        self.add("a:1", "fail", now=T0)
        self.assertEqual(ledger.status("a:1", self.entries()), "fail")
        self.add("a:1", "pass", now=T0 + 60)
        self.assertEqual(ledger.status("a:1", self.entries()), "pass")
        self.add("a:1", "fail", now=T0 + 120)
        self.assertEqual(ledger.status("a:1", self.entries()), "fail")
        self.assertEqual(ledger.status("other:2", self.entries()), "unproven")

    def test_names_match_the_way_tags_do(self):
        self.add("Qwen3:Latest", "fail")
        self.assertEqual(ledger.status("qwen3", self.entries()), "fail")  # an implicit :latest is the same model

    def test_a_missing_file_is_just_empty(self):
        self.assertEqual(self.entries(), [])

    def test_corrupt_and_odd_lines_are_skipped_not_fatal(self):
        self.add("a:1", "fail")
        path = ledger.ledger_path(self.home, {})
        with open(path, "a", encoding="utf-8") as f:
            f.write("not json at all\n[1,2]\n{\"verdict\":\"maybe\",\"modelRef\":\"a:1\"}\n{\"verdict\":\"pass\"}\n\n")
        self.add("b:2", "pass")
        got = self.entries()
        self.assertEqual([e["modelRef"] for e in got], ["a:1", "b:2"])

    def test_an_absurdly_nested_line_is_skipped_not_fatal(self):
        self.add("a:1", "fail")
        with open(ledger.ledger_path(self.home, {}), "a", encoding="utf-8") as f:
            f.write("[" * 100000)
        self.assertEqual([e["modelRef"] for e in self.entries()], ["a:1"])

    def test_a_byte_order_mark_does_not_hide_the_first_entry(self):
        path = ledger.ledger_path(self.home, {})
        path.parent.mkdir(parents=True)
        path.write_bytes(b"\xef\xbb\xbf" + b'{"modelRef":"a:1","verdict":"fail"}\n')
        self.assertEqual(ledger.status("a:1", self.entries()), "fail")

    def test_fresh_pass_lasts_five_minutes(self):
        self.add("a:1", "pass", now=T0)
        e = self.entries()
        self.assertTrue(ledger.fresh_pass("a:1", e, now=T0 + 299))
        self.assertTrue(ledger.fresh_pass("a:1", e, now=T0 + 300))
        self.assertFalse(ledger.fresh_pass("a:1", e, now=T0 + 301))
        self.assertFalse(ledger.fresh_pass("a:1", e, now=T0 - 5))  # a clock that went backwards is not trusted
        self.add("a:1", "fail", now=T0 + 10)
        self.assertFalse(ledger.fresh_pass("a:1", self.entries(), now=T0 + 20))  # the latest entry is a fail

    def test_a_bad_verdict_is_refused_without_writing(self):
        ok, message = self.add("a:1", "maybe")
        self.assertFalse(ok)
        self.assertIn("pass or fail", message)
        self.assertFalse(ledger.ledger_path(self.home, {}).exists())

    def test_a_write_that_fails_warns_once_and_does_not_raise(self):
        with tempfile.NamedTemporaryFile() as blocker:  # a file where the folder should be
            ok, message = ledger.append("a:1", "fail", "r", home=blocker.name, env={}, now=T0, host="box")
        self.assertFalse(ok)
        self.assertEqual(message.count("\n"), 0)
        self.assertIn("carrying on", message)

    def test_the_env_override_moves_the_file(self):
        ok, _ = ledger.append("a:1", "pass", "r", env={"ANTIGRAVITY_LOCAL_HOME": str(Path(self.home) / "elsewhere")}, now=T0, host="b")
        self.assertTrue(ok)
        self.assertTrue((Path(self.home) / "elsewhere" / "ledger.jsonl").exists())

    def test_unicode_in_a_reason_survives(self):
        self.add("a:1", "fail", "modèle sans outils — non")
        self.assertIn("modèle", self.entries()[0]["reason"])


if __name__ == "__main__":
    unittest.main()
