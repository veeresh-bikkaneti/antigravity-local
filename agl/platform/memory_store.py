"""
agl/platform/memory_store.py - the SQLite adapter: the memory store's connection and
schema, moved out of memory.py in Phase 6a. The db path is always passed in.
"""
import contextlib
import sqlite3

DatabaseError = sqlite3.DatabaseError  # callers classify without importing sqlite3


class MemoryDatabase:
    """Manages SQLite tables and FTS5 virtual indices."""

    def __init__(self, db_path):
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
