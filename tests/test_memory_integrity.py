"""Regressions for index integrity: backend switch, ghost docs, leaked connections."""
import json
import sqlite3
import sys
import tempfile
import threading
import urllib.request
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import memory  # noqa: E402

BODY = ("# Title\n\nsome searchable body text about retrieval and memory fabric\n\n"
        "## Part Two\n\nsecond section with enough words to become its own chunk\n")


class FakeEmbedder:
    def __init__(self, mode, dim, flaky=False):
        self.mode, self.dim, self.flaky, self.calls = mode, dim, flaky, 0

    def embed_text(self, text):
        self.calls += 1
        d = self.dim // 2 if self.flaky and self.calls % 2 == 0 else self.dim
        return [1.0] + [0.0] * (d - 1)


class IndexIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.root = root
        (root / "README.md").write_text(BODY, encoding="utf-8")
        (root / "AGENTS.md").write_text(BODY.replace("Title", "Agents"), encoding="utf-8")
        self._saved = (memory.REPO_ROOT, memory.WIKI_DIR)
        memory.REPO_ROOT, memory.WIKI_DIR = root, root / ".wiki"
        self.db = memory.MemoryDatabase(root / "i.sqlite")

    def tearDown(self):
        memory.REPO_ROOT, memory.WIKI_DIR = self._saved
        self.tmp.cleanup()

    def index(self, emb, **kw):
        return memory.MemoryIndexer(self.db, emb).index_all(**kw)

    def q(self, sql):
        with self.db.get_connection() as c:
            return c.execute(sql).fetchall()

    def test_backend_switch_reindexes_without_force(self):
        self.index(FakeEmbedder("ollama (x)", 8))
        self.index(FakeEmbedder("pure_python_tfidf", 4))
        dims = {len(__import__("json").loads(r[0])) for r in self.q("SELECT embedding FROM chunks")}
        self.assertEqual(dims, {4})

    def test_search_ignores_vectors_from_other_backend(self):
        self.index(FakeEmbedder("ollama (x)", 8))
        s = memory.MemorySearcher(self.db, FakeEmbedder("pure_python_tfidf", 4))
        self.assertEqual(s.search("qqqzzz"), [])  # no lexical hit, no comparable vectors

    def test_mixed_dimension_doc_is_not_marked_current(self):
        self.index(FakeEmbedder("ollama (x)", 8, flaky=True))
        modes = [r[0] for r in self.q("SELECT embed_mode FROM documents")]
        self.assertTrue(all(m is None for m in modes), modes)

    def test_legacy_db_without_embed_mode_is_migrated_and_reindexed(self):
        legacy = self.root / "old.sqlite"
        c = sqlite3.connect(legacy)
        c.executescript("""CREATE TABLE documents (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL, category TEXT NOT NULL, mtime REAL NOT NULL, chunk_count INTEGER NOT NULL,
            indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);""")
        mt = (self.root / "README.md").stat().st_mtime
        c.execute("INSERT INTO documents (path,title,category,mtime,chunk_count) VALUES ('README.md','R','root_doc',?,1)", (mt,))
        c.commit(); c.close()
        self.db = memory.MemoryDatabase(legacy)
        stats = self.index(FakeEmbedder("m", 4))
        self.assertGreaterEqual(stats["indexed"], 1)  # legacy row (NULL mode) is not skipped

    def test_deleted_source_file_is_purged_from_index_and_fts(self):
        e = FakeEmbedder("m", 4)
        self.index(e)
        (self.root / "AGENTS.md").unlink()
        self.index(e)
        self.assertEqual([r[0] for r in self.q("SELECT path FROM documents")], ["README.md"])
        self.assertEqual(self.q("SELECT COUNT(*) FROM chunks_fts WHERE doc_id NOT IN (SELECT id FROM documents)")[0][0], 0)

    def test_connection_is_closed_after_with_block(self):
        with self.db.get_connection() as conn:
            conn.execute("SELECT 1")
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_with_block_commits_on_success_and_rolls_back_on_error(self):
        with self.db.get_connection() as c:
            c.execute("INSERT INTO documents (path,title,category,mtime,chunk_count) VALUES ('a','a','doc',0,0)")
        with self.assertRaises(RuntimeError):
            with self.db.get_connection() as c:
                c.execute("INSERT INTO documents (path,title,category,mtime,chunk_count) VALUES ('b','b','doc',0,0)")
                raise RuntimeError
        self.assertEqual([r[0] for r in self.q("SELECT path FROM documents")], ["a"])


class _Resp:
    def __init__(self, body): self.body = body
    def read(self): return self.body
    def __enter__(self): return self
    def __exit__(self, *a): pass


class RealProviderAndMigration(IndexIntegrity):
    """Uses the real EmbeddingProvider (HTTP faked) and real concurrent opens."""

    def _fake_ollama(self, state):
        def fake(req, timeout=None):
            if req.full_url.endswith("/api/tags"):
                return _Resp(json.dumps({"models": [{"name": "nomic-embed-text:latest"}]}).encode())
            if not state["up"]:
                raise OSError("ollama down")
            return _Resp(json.dumps({"embedding": [0.1] * 768}).encode())
        saved = urllib.request.urlopen
        urllib.request.urlopen = fake
        self.addCleanup(setattr, urllib.request, "urlopen", saved)

    def test_total_fallback_during_ollama_outage_is_retried_not_stamped_ollama(self):
        state = {"up": False}
        self._fake_ollama(state)
        emb = memory.EmbeddingProvider()
        self.assertTrue(emb.mode.startswith("ollama"))
        self.index(emb)  # every embed call fails -> 128-dim fallback vectors
        self.assertTrue(all(r[0] is None for r in self.q("SELECT embed_mode FROM documents")))
        state["up"] = True
        self.index(memory.EmbeddingProvider())
        dims = {len(json.loads(r[0])) for r in self.q("SELECT embedding FROM chunks")}
        self.assertEqual(dims, {768})

    def test_concurrent_open_of_legacy_db_does_not_crash(self):
        for n in range(15):
            legacy = self.root / f"old{n}.sqlite"
            c = sqlite3.connect(legacy)
            c.execute("CREATE TABLE documents (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE NOT NULL,"
                      " title TEXT NOT NULL, category TEXT NOT NULL, mtime REAL NOT NULL, chunk_count INTEGER NOT NULL,"
                      " indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            c.commit(); c.close()
            barrier, errors = threading.Barrier(6), []

            def opener():
                barrier.wait()
                try:
                    memory.MemoryDatabase(legacy)
                except Exception as e:  # noqa: BLE001
                    errors.append(repr(e))
            ts = [threading.Thread(target=opener) for _ in range(6)]
            [t.start() for t in ts]; [t.join() for t in ts]
            self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
