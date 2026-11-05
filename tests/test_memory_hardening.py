"""Hardening regressions: relevance floor, wiki path escape, concurrent index, corrupt DB, limit, chunk cap."""
import contextlib
import io
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import memory  # noqa: E402

DEAD_OLLAMA = "http://127.0.0.1:9"
DOC = "# Zebra\n\nzebra memory fabric hybrid retrieval notes for testing the search floor\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "README.md").write_text(DOC, encoding="utf-8")
        (self.root / "CONTEXT_MEMORY.md").write_text("# Secret\n\nTOP SECRET CONTEXT body text here\n", encoding="utf-8")
        (self.root / ".wiki").mkdir()
        (self.root / ".wiki" / "topic.md").write_text("# Topic\n\nwiki body\n", encoding="utf-8")
        self._saved = (memory.REPO_ROOT, memory.WIKI_DIR, memory.DB_DIR, memory.DB_PATH)
        memory.REPO_ROOT, memory.WIKI_DIR = self.root, self.root / ".wiki"
        memory.DB_DIR = self.root / ".memory"
        memory.DB_PATH = memory.DB_DIR / "index.sqlite"
        self.emb = memory.EmbeddingProvider(DEAD_OLLAMA)

    def tearDown(self):
        memory.REPO_ROOT, memory.WIKI_DIR, memory.DB_DIR, memory.DB_PATH = self._saved
        self.tmp.cleanup()

    def run_cmd(self, fn, **kw):
        """Run a cmd_* function; return (exit_code, stdout, stderr)."""
        out, err, code = io.StringIO(), io.StringIO(), 0
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                fn(type("A", (), kw)())
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
        return code, out.getvalue(), err.getvalue()

    def index(self):
        memory.MemoryIndexer(memory.MemoryDatabase(), self.emb).index_all()


class RelevanceFloor(Base):
    def test_garbage_returns_nothing_legit_passes(self):
        self.index()
        s = memory.MemorySearcher(memory.MemoryDatabase(), self.emb)
        for q in ("zzzzqqqxxyy", "*** !!!", "%00"):
            self.assertEqual(s.search(q), [], q)
        self.assertTrue(s.search("zebra memory fabric"))

    def test_cli_prints_no_results(self):
        self.index()
        code, out, _ = self.run_cmd(memory.cmd_search, query="zzzzqqqxxyy", limit=5, json=False)
        self.assertEqual(code, 0)
        self.assertIn("No results", out)


class WikiEscape(Base):
    def test_traversal_rejected(self):
        for topic in ("../CONTEXT_MEMORY", "..\\CONTEXT_MEMORY", "../README"):
            code, out, _ = self.run_cmd(memory.cmd_wiki, topic=topic)
            self.assertNotEqual(code, 0, topic)
            self.assertNotIn("TOP SECRET", out)
            self.assertIn("not found", out)

    def test_normal_topic_still_works(self):
        code, out, _ = self.run_cmd(memory.cmd_wiki, topic="topic")
        self.assertEqual(code, 0)
        self.assertIn("wiki body", out)


class ConcurrentIndex(Base):
    def test_parallel_force_index_serialises(self):
        errors = []

        def work():
            try:
                memory.MemoryIndexer(memory.MemoryDatabase(), memory.EmbeddingProvider(DEAD_OLLAMA)).index_all(force=True)
            except BaseException as e:  # noqa: BLE001
                errors.append(repr(e))

        memory.MemoryDatabase()
        ts = [threading.Thread(target=work) for _ in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(errors, [])
        with contextlib.closing(sqlite3.connect(memory.DB_PATH)) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 2)

    def test_wal_enabled(self):
        memory.MemoryDatabase()
        with contextlib.closing(sqlite3.connect(memory.DB_PATH)) as c:
            self.assertEqual(c.execute("PRAGMA journal_mode").fetchone()[0], "wal")


class CorruptAndMissingDb(Base):
    def corrupt(self):
        memory.DB_DIR.mkdir(parents=True, exist_ok=True)
        memory.DB_PATH.write_bytes(b"this is definitely not a sqlite database" * 50)

    def test_index_rebuilds_and_keeps_bak(self):
        self.corrupt()
        code, _, _ = self.run_cmd(memory.cmd_index, force=False)
        self.assertEqual(code, 0)
        self.assertTrue(memory.DB_PATH.with_name("index.sqlite.bak").exists())
        with contextlib.closing(sqlite3.connect(memory.DB_PATH)) as c:
            self.assertGreater(c.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 0)

    def test_search_and_status_give_hint(self):
        self.corrupt()
        for fn, kw in ((memory.cmd_search, dict(query="zebra", limit=5, json=False)), (memory.cmd_status, {})):
            code, out, err = self.run_cmd(fn, **kw)
            self.assertEqual(code, 1, fn.__name__)
            self.assertIn("index --force", out + err)
            self.assertNotIn("Traceback", out + err)

    def test_no_index_does_not_create_db(self):
        code, out, err = self.run_cmd(memory.cmd_search, query="zebra", limit=5, json=False)
        self.assertEqual(code, 1)
        self.assertIn("index", err)
        code, out, _ = self.run_cmd(memory.cmd_status)
        self.assertIn("python memory.py index", out)
        self.assertFalse(memory.DB_PATH.exists())


class LimitValidation(unittest.TestCase):
    def test_cli_rejects_bad_limit_and_caps_large(self):
        for bad in ("0", "-1", "abc", ""):
            with self.subTest(bad=bad), contextlib.redirect_stderr(io.StringIO()):
                saved = sys.argv
                sys.argv = ["memory.py", "search", "x", "--limit", bad]
                try:
                    with self.assertRaises(SystemExit) as cm:
                        memory.main()
                    self.assertEqual(cm.exception.code, 2)
                finally:
                    sys.argv = saved
        self.assertEqual(memory._positive_limit("9999"), memory.MAX_LIMIT)


class ChunkCap(unittest.TestCase):
    def chunks(self, text):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "big.md"
            p.write_text(text, encoding="utf-8")
            return memory.MemoryIndexer(None, None).chunk_file(p)

    def test_oversize_section_split_on_paragraphs(self):
        paras = [f"paragraph{i} " + "word " * 60 for i in range(30)]
        chunks = self.chunks("# Big\n\n" + "\n\n".join(paras))
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c["content"]) <= memory.MAX_CHUNK_CHARS for c in chunks))
        joined = " ".join(c["content"] for c in chunks)
        self.assertTrue(all(f"paragraph{i} " in joined for i in range(30)))  # nothing lost
        self.assertTrue(all(c["start_line"] <= c["end_line"] for c in chunks))

    def test_single_giant_line_hard_capped(self):
        chunks = self.chunks("# Big\n\n" + "x" * 9000)
        self.assertTrue(all(len(c["content"]) <= memory.MAX_CHUNK_CHARS for c in chunks))
        self.assertEqual(sum(c["content"].count("x") for c in chunks), 9000)

    def test_small_section_unchanged(self):
        chunks = self.chunks("# Small\n\nshort section with enough text to keep\n")
        self.assertEqual(len(chunks), 1)


if __name__ == "__main__":
    unittest.main()
