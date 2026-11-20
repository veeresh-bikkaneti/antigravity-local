"""Phase 6b sanity: the hybrid rank fusion math, offline and without a database."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agl.core import memory as core_memory  # noqa: E402

BOOSTS = {"wiki": 1.35, "code": 1.00}
GATES = {"category_boosts": BOOSTS, "vector_sim_floor": 0.35, "bm25_min_sim": 0.15}
QUERY = [1.0, 0.0]
VEC_HI = "[1.0, 0.0]"  # cosine with QUERY is 1.0
VEC_LO = "[0.0, 1.0]"  # cosine with QUERY is 0.0


def _row(cid, category="code", embedding=None):
    """A chunk row shaped like the two SELECTs, plus a stored vector when it has one."""
    row = {"chunk_id": cid, "doc_id": 1, "start_line": cid, "end_line": cid + 1, "content": f"chunk {cid}",
           "path": f"docs/{cid}.md", "title": f"T{cid}", "category": category}
    if embedding is not None:
        row["embedding"] = embedding
    return row


def _rank(bm25=(), vector=(), limit=5, **overrides):
    opts = dict(GATES)
    opts.update(overrides)
    return core_memory.rank_hits(list(bm25), list(vector), QUERY, limit=limit, **opts)


class MergeOrder(unittest.TestCase):
    def test_a_chunk_in_both_lists_outranks_one_in_a_single_list(self):
        """Two ranks accumulate on chunk 1, so it wins; chunk 2 keeps its BM25 rank and a 0.0 vector."""
        hits = _rank(bm25=[_row(1), _row(2)], vector=[_row(1, embedding=VEC_HI)])
        self.assertEqual([h["chunk_id"] for h in hits], [1, 2])
        self.assertAlmostEqual(hits[0]["rrf_score"], 0.5 / 61 + 0.5 / 61)
        self.assertAlmostEqual(hits[1]["rrf_score"], 0.5 / 62)
        self.assertEqual((hits[0]["bm25_rank"], hits[0]["vector_sim"]), (1, 1.0))
        self.assertEqual((hits[1]["bm25_rank"], hits[1]["vector_sim"]), (2, 0.0))

    def test_the_result_keys_keep_the_order_cmd_search_json_prints(self):
        """`memory.py search --json` dumps this dict, so the insertion order is part of the contract."""
        keys = list(_rank(bm25=[_row(1)], vector=[_row(1, embedding=VEC_HI)])[0])
        self.assertEqual(keys, ["chunk_id", "path", "title", "category", "start_line", "end_line",
                                "content", "rrf_score", "bm25_rank", "vector_sim"])

    def test_only_the_first_fuse_depth_vector_rows_are_fused(self):
        """Beyond fuse_depth a vector row contributes nothing: a lone far hit disappears entirely."""
        rows = [_row(1, embedding=VEC_HI), _row(2, embedding=VEC_HI)]
        self.assertEqual([h["chunk_id"] for h in _rank(vector=rows, fuse_depth=1)], [1])
        self.assertEqual(_rank(vector=rows, fuse_depth=1)[0]["bm25_rank"], 999)


class CategoryBoost(unittest.TestCase):
    def test_equal_similarity_still_ranks_the_wiki_hit_first(self):
        """Same cosine, so the 1.35 boost carries the wiki chunk past the better-placed code chunk."""
        hits = _rank(vector=[_row(1, embedding=VEC_HI), _row(2, category="wiki", embedding=VEC_HI)])
        self.assertEqual([h["chunk_id"] for h in hits], [2, 1])
        self.assertAlmostEqual(hits[0]["rrf_score"], 1.35 * (0.5 / 62))  # vector rank 2, boosted
        self.assertAlmostEqual(hits[1]["rrf_score"], 1.00 * (0.5 / 61))  # vector rank 1, unboosted


class Gates(unittest.TestCase):
    def test_a_vector_only_hit_below_the_floor_is_dropped(self):
        """No BM25 rank means the vector floor alone decides, and 0.0 is below 0.35."""
        self.assertEqual(_rank(vector=[_row(1, embedding=VEC_LO)]), [])

    def test_a_bm25_hit_with_no_embedding_survives_the_gate(self):
        """A chunk that was never embedded cannot be judged semantically, so its BM25 hit stays."""
        hits = _rank(bm25=[_row(1)])
        self.assertEqual([h["chunk_id"] for h in hits], [1])
        self.assertEqual(hits[0]["vector_sim"], 0.0)

    def test_a_bm25_hit_with_a_vector_below_the_bm25_floor_is_dropped(self):
        """The chunk does have a vector, and 0.0 < 0.15, so the lexical hit goes too."""
        self.assertEqual(_rank(bm25=[_row(1)], vector=[_row(1, embedding=VEC_LO)]), [])


class Limit(unittest.TestCase):
    def test_the_limit_cuts_the_tail_of_the_ranking(self):
        """Three survivors, limit 2: the two best BM25 ranks come back, best first."""
        hits = _rank(bm25=[_row(1), _row(2), _row(3)], limit=2)
        self.assertEqual([h["chunk_id"] for h in hits], [1, 2])


if __name__ == "__main__":
    unittest.main()
