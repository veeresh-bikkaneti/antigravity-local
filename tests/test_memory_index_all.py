"""One test: agl.app.memory.index_all indexes a new file once, then skips it unforced."""

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agl.app import memory as app_memory


class _FakeConn:
    """Just enough of a sqlite connection: index_all only calls commit() on it."""

    def commit(self):
        pass


class _FakeStore:
    """In-memory stand-in for the memory_store SQL layer, keyed by relative path."""

    def __init__(self):
        self.conn = _FakeConn()
        self.docs = {}
        self._next_id = 1

    def get_connection(self):
        store = self

        class _Ctx:
            def __enter__(self):
                return store.conn

            def __exit__(self, *exc):
                return False

        return _Ctx()

    def begin_immediate(self, conn):
        pass

    def document_paths(self, conn):
        return [{"path": p, "id": r["id"]} for p, r in self.docs.items()]

    def prune_document(self, conn, doc_id):
        for p, r in list(self.docs.items()):
            if r["id"] == doc_id:
                del self.docs[p]

    def document_row(self, conn, rel_path):
        return self.docs.get(rel_path)

    def clear_document(self, conn, doc_id):
        for p, r in list(self.docs.items()):
            if r["id"] == doc_id:
                del self.docs[p]

    def insert_document(self, conn, rel_path, title, category, mtime, n_chunks):
        doc_id = self._next_id
        self._next_id += 1
        self.docs[rel_path] = {
            "id": doc_id, "path": rel_path, "title": title, "category": category,
            "mtime": mtime, "n_chunks": n_chunks, "embed_mode": None,
        }
        return doc_id

    def insert_chunk(self, conn, doc_id, idx, start_line, end_line, content, emb_json):
        pass

    def set_embed_mode(self, conn, doc_id, mode):
        for row in self.docs.values():
            if row["id"] == doc_id:
                row["embed_mode"] = mode


class _FakeEmbedder:
    mode = "fake-backend"
    fell_back = False

    def embed_text(self, text):
        return [1.0, 0.0]


class TestIndexAll(unittest.TestCase):
    def test_index_new_file_once_then_skip_unforced(self):
        with TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            note = repo_root / "note.md"
            note.write_text("hello memory", encoding="utf-8")
            kwargs = dict(
                store=_FakeStore(),
                embedder=_FakeEmbedder(),
                targets=[(note, "doc")],
                repo_root=repo_root,
                chunk=lambda p: [{"start_line": 1, "end_line": 1, "content": "hello memory"}],
                warn=lambda m: None,
            )
            first = app_memory.index_all(**kwargs)
            self.assertEqual(first, {"indexed": 1, "skipped": 0, "chunks": 1, "purged": 0})
            second = app_memory.index_all(**kwargs)
            self.assertEqual(second, {"indexed": 0, "skipped": 1, "chunks": 0, "purged": 0})


if __name__ == "__main__":
    unittest.main()
