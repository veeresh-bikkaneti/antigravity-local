"""Ranking order table: each level beats every level below it, even when all of those favour the rival."""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ranking  # noqa: E402


def cand(tag="m", **over):
    base = {"tag": tag, "kind": "chat", "fit": "gpu", "badges": ("tools",), "installed": False,
            "ledger": "unproven", "last_modified": "2026-01-01T00:00:00Z", "downloads": 10,
            "size_gb": 5.0, "name_score": 1.0}
    base.update(over)
    return base


# Each row: (label, winner overrides, loser overrides). Every lower level favours the loser.
TABLE = [
    ("fit gpu beats split",
     dict(fit="gpu", badges=("tools?",), installed=False, ledger="unproven"),
     dict(fit="split", badges=("tools",), installed=True, ledger="pass", name_score=99.0)),
    ("fit split beats too big",
     dict(fit="split", badges=(), ledger="unproven"),
     dict(fit="too big", badges=("tools",), installed=True, ledger="pass")),
    ("fit unknown counts like split, beats too big",
     dict(fit=None, badges=(), ledger="unproven"),
     dict(fit="too big", badges=("tools",), installed=True, ledger="pass")),
    ("not failed beats a ledger fail",
     dict(ledger="unproven", badges=(), installed=False),
     dict(ledger="fail", badges=("tools",), installed=True, last_modified="2026-11-01T00:00:00Z")),
    ("confirmed tools beats tools?",
     dict(badges=("tools",), installed=False),
     dict(badges=("tools?",), installed=True, ledger="pass")),
    ("tools? beats known no tools",
     dict(badges=("tools?",), installed=False),
     dict(badges=("vision",), installed=True, ledger="pass")),
    ("installed beats not installed",
     dict(installed=True, ledger="unproven", last_modified=None, downloads=0, size_gb=1.0),
     dict(installed=False, ledger="pass", last_modified="2026-11-01T00:00:00Z", downloads=999, size_gb=70.0)),
    ("probe pass beats unproven",
     dict(ledger="pass", last_modified=None, downloads=0, size_gb=1.0),
     dict(ledger="unproven", last_modified="2026-11-01T00:00:00Z", downloads=999, size_gb=70.0, name_score=99.0)),
    ("newer last_modified beats older",
     dict(last_modified="2026-06-01T00:00:00Z", downloads=1, size_gb=1.0),
     dict(last_modified="2026-05-01T00:00:00Z", downloads=999, size_gb=70.0, name_score=99.0)),
    ("same date: more downloads wins",
     dict(downloads=500, size_gb=1.0),
     dict(downloads=100, size_gb=70.0, name_score=99.0)),
    ("same date and downloads: larger size wins",
     dict(size_gb=30.0),
     dict(size_gb=7.0, name_score=99.0)),
    ("name_score decides only on a full tie",
     dict(name_score=5.0),
     dict(name_score=4.0)),
]


class RankingTable(unittest.TestCase):
    def test_each_level_beats_everything_below_it(self):
        for label, win, lose in TABLE:
            with self.subTest(label):
                w, l = cand("winner", **win), cand("loser", **lose)
                self.assertGreater(ranking.rank_key(w), ranking.rank_key(l))
                for order in ((w, l), (l, w)):
                    self.assertEqual(ranking.best_for_agent(list(order))["tag"], "winner")

    def test_unknown_badges_tie_with_tools_guess(self):
        self.assertEqual(ranking.rank_key(cand(badges=None)), ranking.rank_key(cand(badges=("tools?",))))

    def test_unknown_badges_rank_above_known_no_tools(self):
        self.assertGreater(ranking.rank_key(cand(badges=None)), ranking.rank_key(cand(badges=())))

    def test_ledger_fail_ranks_below_unproven(self):
        self.assertLess(ranking.rank_key(cand(ledger="fail")), ranking.rank_key(cand(ledger="unproven")))
        self.assertEqual(ranking.best_for_agent([cand("f", ledger="fail"), cand("u")])["tag"], "u")

    def test_model_without_tools_ranks_below_one_with_it(self):
        self.assertEqual(ranking.best_for_agent([cand("no", badges=("vision",)), cand("yes")])["tag"], "yes")

    def test_a_failed_model_is_still_returned_when_it_is_all_there_is(self):
        self.assertEqual(ranking.best_for_agent([cand("only", ledger="fail")])["tag"], "only")


class Filtering(unittest.TestCase):
    def test_embedding_only_is_filtered(self):
        only = [cand("nomic-embed-text", kind="embedding")]
        self.assertEqual(ranking.agent_candidates(only), [])
        self.assertIsNone(ranking.best_for_agent(only))

    def test_media_only_is_filtered(self):
        only = [cand("x/flux2-klein", kind="media"), cand("sdxl", kind="media")]
        self.assertEqual(ranking.agent_candidates(only), [])
        self.assertIsNone(ranking.best_for_agent(only))

    def test_embedding_and_media_never_beat_a_weaker_chat_model(self):
        strong = dict(installed=True, ledger="pass", downloads=10 ** 6, name_score=99.0)
        pool = [cand("e", kind="embedding", **strong), cand("m", kind="media", **strong),
                cand("chat", fit="too big", badges=(), ledger="fail")]
        self.assertEqual(ranking.best_for_agent(pool)["tag"], "chat")

    def test_unknown_kind_with_embed_name_is_filtered(self):
        self.assertIsNone(ranking.best_for_agent([cand("bge-m3", kind="unknown")]))
        self.assertIsNone(ranking.best_for_agent([cand("nomic-embed-text", kind="unknown")]))

    def test_unknown_kind_with_chat_name_stays(self):
        self.assertEqual(ranking.best_for_agent([cand("qwen3:8b", kind="unknown")])["tag"], "qwen3:8b")

    def test_empty_input(self):
        self.assertIsNone(ranking.best_for_agent([]))


class Epoch(unittest.TestCase):
    def test_offsets_parse(self):
        z = ranking.epoch("2026-11-14T20:00:00Z")
        self.assertEqual(z, ranking.epoch("2026-11-14T20:00:00+00:00"))
        self.assertEqual(ranking.epoch("2026-11-14T14:00:00-06:00"), z)
        self.assertGreater(z, 0)

    def test_mixed_offsets_compare_correctly(self):
        # 14:30-06:00 is 20:30Z, so it is 30 minutes LATER than 20:00Z even though 14:30 < 20:00 as text.
        later = ranking.epoch("2026-11-14T14:30:00-06:00")
        earlier = ranking.epoch("2026-11-14T20:00:00Z")
        self.assertEqual(later - earlier, 1800)

    def test_mixed_offsets_decide_ranking(self):
        newer = cand("newer", last_modified="2026-11-14T14:30:00-06:00")
        older = cand("older", last_modified="2026-11-14T20:00:00Z")
        self.assertEqual(ranking.best_for_agent([older, newer])["tag"], "newer")

    def test_garbage_is_zero(self):
        for bad in (None, "", "   ", "yesterday", "2026-13-45T99:00:00Z", 12345, ["x"]):
            with self.subTest(bad=bad):
                self.assertEqual(ranking.epoch(bad), 0)


class Robustness(unittest.TestCase):
    def test_missing_keys_do_not_crash(self):
        for sparse in ({}, {"tag": "x"}, {"tag": "x", "kind": "chat"}, {"kind": "chat", "badges": None}):
            with self.subTest(sparse=sparse):
                self.assertIsInstance(ranking.rank_key(sparse), tuple)
        self.assertEqual(ranking.best_for_agent([{"tag": "x"}])["tag"], "x")

    def test_none_and_junk_values_count_as_zero(self):
        a = cand(downloads=None, size_gb=None, last_modified=None, name_score=None)
        b = cand(downloads="lots", size_gb="big", last_modified="soon", name_score="high")
        self.assertEqual(ranking.rank_key(a), ranking.rank_key(b))

    def test_nan_and_inf_count_as_zero_so_they_cannot_win_by_position_or_size(self):
        for field in ("name_score", "size_gb", "downloads"):
            for bad in (float("nan"), float("inf"), float("-inf")):
                with self.subTest(field=field, bad=bad):
                    ok, odd = cand("ok"), cand("odd", **{field: bad})
                    self.assertEqual(ranking.rank_key(odd), ranking.rank_key(cand("zero", **{field: 0})))
                    self.assertEqual(ranking.best_for_agent([odd, ok])["tag"], "ok")
                    self.assertEqual(ranking.best_for_agent([ok, odd])["tag"], "ok")

    def test_string_numbers_and_bool_downloads_do_not_crash_or_win(self):
        pool = [cand("text", downloads="500"), cand("flag", downloads=True), cand("real", downloads=5)]
        self.assertEqual(ranking.best_for_agent(pool)["tag"], "real")
        self.assertEqual(ranking.best_for_agent(pool[::-1])["tag"], "real")

    def test_an_unhashable_fit_or_ledger_is_just_unknown(self):
        self.assertEqual(ranking.rank_key(cand(fit=["gpu"], ledger=["fail"]))[:2], (1, 1))

    def test_lowercase_z_timestamps_parse(self):
        self.assertEqual(ranking.epoch("2026-11-01T00:00:00z"), ranking.epoch("2026-11-01T00:00:00Z"))

    def test_the_exact_default_key_for_an_empty_candidate(self):
        self.assertEqual(ranking.rank_key({}), (1, 1, 1, 0, 0, (0, 0, 0), 0))

    def test_full_tie_first_in_input_order_wins(self):
        a, b, c = cand("a"), cand("b"), cand("c")
        self.assertEqual(ranking.best_for_agent([a, b, c])["tag"], "a")
        self.assertEqual(ranking.best_for_agent([c, b, a])["tag"], "c")

    def test_does_not_mutate_input(self):
        pool = [cand("a", kind="embedding"), cand("b", installed=True), cand("c", ledger="fail")]
        before = copy.deepcopy(pool)
        ranking.best_for_agent(pool)
        ranking.agent_candidates(pool)
        self.assertEqual(pool, before)

    def test_returns_the_same_dict_object(self):
        pool = [cand("a")]
        self.assertIs(ranking.best_for_agent(pool), pool[0])


if __name__ == "__main__":
    unittest.main()
