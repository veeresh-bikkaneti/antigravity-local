"""
agl/platform/memory_store.py - the SQLite adapter: the memory store's connection and
schema, moved out of memory.py in Phase 6a, and the search queries, moved in Phase 6b.
The db path is always passed in.
"""
import contextlib
import sqlite3

DatabaseError = sqlite3.DatabaseError  # callers classify without importing sqlite3


class MemoryDatabase:
    """Manages SQLite tables and FTS5 virtual indices."""

    def __init__(self, db_path=None):
        if db_path is None:
            import sys
            mem = sys.modules.get("memory")
            if mem and hasattr(mem, "DB_PATH"):
                db_path = mem.DB_PATH
            else:
                from pathlib import Path
                db_path = Path(__file__).resolve().parent.parent.parent / ".memory" / "index.sqlite"
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextlib.contextmanager
    def get_connection(self):
        """Yield a connection: commit on success, roll back on error, always close."""
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 30000;")
            if conn.execute("PRAGMA journal_mode;").fetchone()[0] != "wal":  # sticky once set
                try:
                    conn.execute("PRAGMA journal_mode = WAL;")
                except sqlite3.OperationalError:  # another process is switching it; rollback mode still works
                    pass
            conn.execute("PRAGMA foreign_keys = ON;")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self):
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    mtime REAL NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    embed_mode TEXT
                );
            """)
            # Migrate pre-embed_mode DBs. NULL = unknown backend = re-embedded on next index.
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(documents)")]
            if "embed_mode" not in cols:
                try:
                    conn.execute("ALTER TABLE documents ADD COLUMN embed_mode TEXT")
                except sqlite3.OperationalError as e:  # another process migrated first
                    if "duplicate column" not in str(e):
                        raise

            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding TEXT
                );
            """)

            # FTS5 virtual table for lexical BM25 matching
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    content,
                    doc_id UNINDEXED,
                    chunk_id UNINDEXED,
                    tokenize = 'porter unicode61'
                );
            """)
            conn.commit()

    @staticmethod
    def fts_candidates(conn, fts_query, limit):
        """BM25 lexical hits for a sanitized FTS query, best first (the search path's half 1)."""
        return conn.execute("""
            SELECT 
                c.id AS chunk_id,
                c.doc_id,
                c.start_line,
                c.end_line,
                c.content,
                d.path,
                d.title,
                d.category,
                bm25(chunks_fts) AS bm25_rank
            FROM chunks_fts f
            JOIN chunks c ON f.chunk_id = c.id
            JOIN documents d ON c.doc_id = d.id
            WHERE chunks_fts MATCH ?
            ORDER BY bm25_rank ASC
            LIMIT ?;
        """, (fts_query, limit)).fetchall()

    @staticmethod
    def vector_chunks(conn, embed_mode):
        """Every chunk whose document was embedded by `embed_mode`, stored vector included (half 2)."""
        return conn.execute("""
            SELECT 
                c.id AS chunk_id,
                c.doc_id,
                c.start_line,
                c.end_line,
                c.content,
                c.embedding,
                d.path,
                d.title,
                d.category
            FROM chunks c
            JOIN documents d ON c.doc_id = d.id
            WHERE d.embed_mode = ?;
        """, (embed_mode,)).fetchall()  # only compare vectors from the same backend

    @staticmethod
    def begin_immediate(conn):
        """Take the write lock up front: parallel index runs queue here instead of hitting IntegrityError."""
        conn.execute("BEGIN IMMEDIATE")

    @staticmethod
    def document_paths(conn):
        """(id, path) for every indexed document, so the indexer can spot the ones whose file vanished."""
        return conn.execute("SELECT id, path FROM documents").fetchall()

    @staticmethod
    def prune_document(conn, doc_id):
        """Drop one vanished document: FTS5 has no FK cascade, so its FTS rows go by hand first."""
        conn.execute("DELETE FROM chunks_fts WHERE doc_id = ?", (doc_id,))
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))  # chunks cascade

    @staticmethod
    def document_row(conn, rel_path):
        """The indexed row for `rel_path` (id, mtime, embed_mode), or None when it was never indexed."""
        return conn.execute("SELECT id, mtime, embed_mode FROM documents WHERE path = ?", (rel_path,)).fetchone()

    @staticmethod
    def clear_document(conn, doc_id):
        """Delete a document's chunks, its FTS rows and the document itself, ready for a re-index."""
        conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        conn.execute("DELETE FROM chunks_fts WHERE doc_id = ?", (doc_id,))
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    @staticmethod
    def insert_document(conn, rel_path, title, category, mtime, chunk_count):
        """Insert one document row and return its id."""
        cur = conn.execute("""
            INSERT INTO documents (path, title, category, mtime, chunk_count)
            VALUES (?, ?, ?, ?, ?)
        """, (rel_path, title, category, mtime, chunk_count))
        return cur.lastrowid

    @staticmethod
    def insert_chunk(conn, doc_id, chunk_index, start_line, end_line, content, embedding):
        """Insert one chunk and its FTS5 row; return the new chunk id."""
        cur_chunk = conn.execute("""
            INSERT INTO chunks (doc_id, chunk_index, start_line, end_line, content, embedding)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (doc_id, chunk_index, start_line, end_line, content, embedding))
        chunk_id = cur_chunk.lastrowid
        # Insert into FTS5
        conn.execute("""
            INSERT INTO chunks_fts (content, doc_id, chunk_id)
            VALUES (?, ?, ?)
        """, (content, doc_id, chunk_id))
        return chunk_id

    @staticmethod
    def set_embed_mode(conn, doc_id, embed_mode):
        """Record which backend's vectors this document holds; NULL means the next run retries."""
        conn.execute("UPDATE documents SET embed_mode = ? WHERE id = ?", (embed_mode, doc_id))

    @staticmethod
    def counts(conn):
        """(documents, chunks) totals for the status report."""
        doc_count = conn.execute("SELECT COUNT(*) FROM documents;").fetchone()[0]
        chunk_count = conn.execute("SELECT COUNT(*) FROM chunks;").fetchone()[0]
        return doc_count, chunk_count

    @staticmethod
    def category_counts(conn):
        """(category, document count) rows for the status report."""
        return conn.execute("SELECT category, COUNT(*) FROM documents GROUP BY category;").fetchall()
