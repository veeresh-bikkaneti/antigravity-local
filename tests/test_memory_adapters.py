"""Phase 6a sanity: the memory adapters and pure helpers offline."""
import argparse
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agl.platform import embeddings, memory_store  # noqa: E402
from agl.core import memory as core_memory  # noqa: E402


class Embeddings(unittest.TestCase):
    def test_dead_endpoint_falls_back_to_the_pure_python_backend(self):
        emb = embeddings.EmbeddingProvider("http://127.0.0.1:9")
        self.assertIsNone(emb.ollama_model)
        self.assertEqual(emb.mode, "pure_python_tfidf")
        vec = emb.embed_text("hello world")
        self.assertEqual(len(vec), 128)
        self.assertLess(abs(sum(v * v for v in vec) - 1.0), 1e-6)
        # fell_back only marks a failed call after a model was detected; with none detected
        # the fallback is the provider's quiet normal mode, so the flag stays False.
        self.assertFalse(emb.fell_back)


class MemoryStore(unittest.TestCase):
    def test_schema_has_the_documents_chunks_and_fts_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "a.sqlite"
            memory_store.MemoryDatabase(db_path)
            conn = sqlite3.connect(str(db_path))
            try:
                names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
            finally:
                conn.close()
            self.assertIn("documents", names)
            self.assertIn("chunks", names)
            self.assertIn("chunks_fts", names)
            self.assertIs(memory_store.DatabaseError, sqlite3.DatabaseError)


class CoreHelpers(unittest.TestCase):
    def test_the_pure_helpers(self):
        self.assertEqual(core_memory.cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)
        self.assertEqual(core_memory._sanitize_fts_query("two words!"), '"two" OR "words"')
        self.assertEqual(core_memory._positive_limit("9999", 20), 20)
        with self.assertRaises(argparse.ArgumentTypeError):
            core_memory._positive_limit("0", 20)
        for chunk in core_memory._split_oversize(["x" * 5000], 1, 2000):
            self.assertLessEqual(len(chunk["content"]), 2000)


if __name__ == "__main__":
    unittest.main()
