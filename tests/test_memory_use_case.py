"""Phase 6b sanity: the search use case talks to a store and an embedder, and prints nothing."""
import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agl.app import memory as app_memory  # noqa: E402

GATES = {"category_boosts": {"code": 1.00}, "vector_sim_floor": 0.35, "bm25_min_sim": 0.15}
VEC_HI = "[1.0, 0.0]"  # cosine with the fake query vector [1.0, 0.0] is 1.0


def _row(cid, embedding=None):
    """A chunk row shaped like the two SELECTs, plus a stored vector when it has one."""
    row = {"chunk_id": cid, "doc_id": 1, "start_line": cid, "end_line": cid + 1, "content": f"chunk {cid}",
           "path": f"docs/{cid}.md", "title": f"T{cid}", "category": "code"}
    if embedding is not None:
        row["embedding"] = embedding
    return row


class _FakeConn:
    """Stands in for the sqlite3 connection: the store methods take it and ignore it here."""


class _FakeStore:
    """A duck-typed store: the two query methods the use case calls, plus connection bookkeeping."""

    def __init__(self, bm25_rows=(), vector_rows=(), fts_error=None):
        self.bm25_rows = list(bm25_rows)
        self.vector_rows = list(vector_rows)
        self.fts_error = fts_error
        self.fts_calls = []
        self.mode_calls = []
        self.connections = 0

    @contextlib.contextmanager
    def get_connection(self):
        self.connections += 1
        yield _FakeConn()

    def fts_candidates(self, conn, fts_query, limit):
        self.fts_calls.append((fts_query, limit))
        if self.fts_error:
            raise self.fts_error
        return self.bm25_rows

    def vector_chunks(self, conn, embed_mode):
        self.mode_calls.append(embed_mode)
        return self.vector_rows


class _FakeEmbedder:
    """Records what it was asked to embed; `fell_back` after the call is what the mode rule reads."""

    def __init__(self, mode="pure_python_tfidf", falls_back=False):
        self.mode = mode
        self.fell_back = True  # the use case must reset this before it embeds
        self.falls_back = falls_back
        self.texts = []

    def embed_text(self, text):
        self.texts.append(text)
        self.fell_back = self.falls_back
        return [1.0, 0.0]


class Search(unittest.TestCase):
    def test_a_blank_query_never_touches_the_store(self):
        """Whitespace means no query: no connection, no embed, no rows."""
        store, emb = _FakeStore(), _FakeEmbedder()
        self.assertEqual(app_memory.search("   \n", store=store, embedder=emb, **GATES), [])
        self.assertEqual((store.connections, store.fts_calls, store.mode_calls), (0, [], []))
        self.assertEqual(emb.texts, [])

    def test_one_connection_one_embed_and_no_output(self):
        """The sanitized query and the embed mode reach the store once each, and nothing is printed."""
        store = _FakeStore(bm25_rows=[_row(1), _row(2)], vector_rows=[_row(1, embedding=VEC_HI)])
        emb = _FakeEmbedder(mode="pure_python_tfidf")
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            hits = app_memory.search("two words!", store=store, embedder=emb, **GATES)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(store.connections, 1)
        self.assertEqual(store.fts_calls, [('"two" OR "words"', 30)])
        self.assertEqual(store.mode_calls, ["pure_python_tfidf"])
        self.assertFalse(emb.fell_back)  # reset before the embed, so a stale flag cannot leak in
        self.assertEqual(emb.texts, ["two words!"])
        self.assertEqual([h["chunk_id"] for h in hits], [1, 2])

    def test_a_query_with_no_words_skips_the_fts_query(self):
        """Punctuation only: the sanitizer returns "", so only the vector half runs."""
        store, emb = _FakeStore(), _FakeEmbedder()
        self.assertEqual(app_memory.search("!!!", store=store, embedder=emb, **GATES), [])
        self.assertEqual(store.fts_calls, [])
        self.assertEqual(store.mode_calls, ["pure_python_tfidf"])

    def test_a_rejected_fts_query_falls_back_to_the_vector_half(self):
        """The store raising is not fatal: BM25 comes back empty and the vector hits still rank."""
        store = _FakeStore(vector_rows=[_row(1, embedding=VEC_HI)],
                           fts_error=RuntimeError("fts5: syntax error near"))
        hits = app_memory.search("two words", store=store, embedder=_FakeEmbedder(), **GATES)
        self.assertEqual([h["chunk_id"] for h in hits], [1])

    def test_a_fallback_vector_asks_the_store_for_no_mode(self):
        """fell_back means the query vector is not comparable, so the mode filter is None."""
        store, emb = _FakeStore(), _FakeEmbedder(falls_back=True)
        app_memory.search("anything", store=store, embedder=emb, **GATES)
        self.assertEqual(store.mode_calls, [None])

    def test_the_limit_reaches_the_ranking(self):
        """Three BM25 survivors with no embeddings, limit 2: the two best ranks come back."""
        store = _FakeStore(bm25_rows=[_row(1), _row(2), _row(3)])
        hits = app_memory.search("three chunks", limit=2, store=store, embedder=_FakeEmbedder(), **GATES)
        self.assertEqual([h["chunk_id"] for h in hits], [1, 2])


if __name__ == "__main__":
    unittest.main()
