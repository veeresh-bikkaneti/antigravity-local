#!/usr/bin/env python3
"""
memory.py - Embedded Hybrid Memory Engine for Local Antigravity Agent
Combines SQLite FTS5 (BM25 exact match) with dense semantic embeddings (Ollama or pure Python).
Part of the 3-Tier Memory Fabric: Graphify (AST) + LLMWiki (Canonical) + SQLite Hybrid (RAG).

Zero external dependencies: runs on pure Python standard library.
"""

import os
import sys
import time
import re
import json
import math
import zlib
import contextlib
import sqlite3
import argparse
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

# Windows console UTF-8 safety
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent
DB_DIR = REPO_ROOT / ".memory"
DB_PATH = DB_DIR / "index.sqlite"
WIKI_DIR = REPO_ROOT / ".wiki"
OLLAMA_API_BASE = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")

# Relevance gates (calibrated on this repo's index with the pure-python backend: gibberish tops out
# near 0.31 cosine, real questions sit 0.35-0.7). A vector-only hit must clear VECTOR_SIM_FLOOR; a
# BM25 hit still needs BM25_MIN_SIM so a stray token like "00" in "%00" cannot drag in noise.
# ponytail: one floor for all backends; Ollama vectors run higher, tune per-mode if that matters.
VECTOR_SIM_FLOOR = 0.35
BM25_MIN_SIM = 0.15
MAX_LIMIT = 20  # hard cap on results per search (CLI and /api/search)

# Chunking: oversize markdown sections are split on paragraph/line boundaries
MAX_CHUNK_CHARS = 2000

# Category priorities for ranking boost
CATEGORY_BOOSTS = {
    "wiki": 1.35,      # Canonical domain truth
    "context": 1.25,   # Ongoing project progress & decisions
    "doc": 1.10,       # Static guides & architecture
    "root_doc": 1.10,  # README, ZERO_TO_CODING
    "code": 1.00       # Source code files
}


# ==============================================================================
# 1. Embedding Provider: Local Ollama with Pure Python Fallback
# ==============================================================================

class EmbeddingProvider:
    """Provides vector embeddings via local Ollama or pure-Python TF-IDF fallback."""

    def __init__(self, base_url: str = OLLAMA_API_BASE):
        self.base_url = base_url.rstrip("/")
        self.ollama_model = self._detect_ollama_embedding_model()
        self.mode = f"ollama ({self.ollama_model})" if self.ollama_model else "pure_python_tfidf"
        self.fell_back = False  # set when an Ollama call failed and a fallback vector was returned

    def _detect_ollama_embedding_model(self) -> str | None:
        """Check if Ollama has a known embedding model installed."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", headers={"User-Agent": "antigravity-memory"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in data.get("models", [])]
                # Look for common embedding models
                candidates = ["nomic-embed-text", "all-minilm", "bge-m3", "bge-small", "snowflake-arctic-embed"]
                for cand in candidates:
                    for m in models:
                        if cand in m:
                            return m
        except Exception:
            pass
        return None

    def embed_text(self, text: str) -> list[float]:
        """Generate embedding vector for text."""
        if self.ollama_model:
            try:
                payload = json.dumps({"model": self.ollama_model, "prompt": text[:2000]}).encode("utf-8")
                req = urllib.request.Request(
                    f"{self.base_url}/api/embeddings",
                    data=payload,
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    emb = data.get("embedding")
                    if emb and isinstance(emb, list):
                        return emb
            except Exception:
                pass
            self.fell_back = True

        # Fallback to pure Python feature vectorizer
        return self._pure_python_embed(text)

    def _pure_python_embed(self, text: str, dimensions: int = 128) -> list[float]:
        """Deterministic, lightweight 128-dim hashing vectorizer with L2 normalization."""
        words = re.findall(r"\w+", text.lower())
        if not words:
            return [0.0] * dimensions

        vec = [0.0] * dimensions
        for word in words:
            # Word hash
            h = zlib.crc32(word.encode())  # stable across processes (builtin hash() is salted)
            idx = h % dimensions
            sign = 1.0 if (h >> 3) & 1 else -1.0
            vec[idx] += sign

            # Character 3-gram hashing for subword matching
            if len(word) >= 3:
                for i in range(len(word) - 2):
                    trigram = word[i:i+3]
                    th = zlib.crc32(trigram.encode())
                    tidx = th % dimensions
                    tsign = 1.0 if (th >> 2) & 1 else -1.0
                    vec[tidx] += 0.5 * tsign

        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 1e-9:
            vec = [v / norm for v in vec]
        return vec


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two unit vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    return sum(a * b for a, b in zip(v1, v2))


# ==============================================================================
# 2. Database & Schema Management
# ==============================================================================

class MemoryDatabase:
    """Manages SQLite tables and FTS5 virtual indices."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DB_PATH  # looked up at call time so tests/tools can repoint DB_PATH
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


# ==============================================================================
# 3. Document Chunking & Indexer Engine
# ==============================================================================

class MemoryIndexer:
    """Discovers repository files, chunks them by markdown sections or lines, and indexes them."""

    def __init__(self, db: MemoryDatabase, embedder: EmbeddingProvider):
        self.db = db
        self.embedder = embedder

    def collect_target_files(self) -> list[tuple[Path, str]]:
        """Collect all files to index categorized by priority."""
        targets = []

        # 1. LLMWiki (.wiki/*.md)
        if WIKI_DIR.is_dir():
            for p in WIKI_DIR.glob("*.md"):
                targets.append((p, "wiki"))

        # 2. Context Memory (CONTEXT_MEMORY.md)
        ctx_file = REPO_ROOT / "CONTEXT_MEMORY.md"
        if ctx_file.exists():
            targets.append((ctx_file, "context"))

        # 3. Docs (docs/*.md)
        docs_dir = REPO_ROOT / "docs"
        if docs_dir.is_dir():
            for p in docs_dir.glob("*.md"):
                targets.append((p, "doc"))

        # 4. Root documentation
        for doc_name in ["README.md", "ZERO_TO_CODING.md", "AGENTS.md"]:
            p = REPO_ROOT / doc_name
            if p.exists():
                targets.append((p, "root_doc"))

        # 5. Core Python modules
        for py_name in ["run.py", "agent_with_workspace.py", "code_agent.py", "test_local.py"]:
            p = REPO_ROOT / py_name
            if p.exists():
                targets.append((p, "code"))

        return targets

    @staticmethod
    def _split_oversize(lines: list[str], start_line: int) -> list[dict]:
        """Cut a section into pieces <= MAX_CHUNK_CHARS, preferring blank-line (paragraph) breaks."""
        # Hard cap: a single giant line is sliced.
        pieces = []  # (line_no, text)
        for n, ln in enumerate(lines, start=start_line):
            for i in range(0, max(len(ln), 1), MAX_CHUNK_CHARS):
                pieces.append((n, ln[i:i + MAX_CHUNK_CHARS]))
        out, buf = [], []

        def flush(items):
            text = "\n".join(t for _, t in items).strip()
            if text:
                out.append({"start_line": items[0][0], "end_line": items[-1][0], "content": text})

        size = 0
        for item in pieces:
            if buf and size + len(item[1]) + 1 > MAX_CHUNK_CHARS:
                cut = next((i for i in range(len(buf) - 1, 0, -1) if not buf[i][1].strip()), None)
                head, buf = (buf[:cut], buf[cut:]) if cut else (buf, [])
                flush(head)
                size = sum(len(t) + 1 for _, t in buf)
            buf.append(item)
            size += len(item[1]) + 1
        if buf:
            flush(buf)
        return out

    def chunk_file(self, path: Path) -> list[dict]:
        """Split a file into semantically meaningful chunks with line bounds."""
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        lines = content.splitlines()
        if not lines:
            return []

        chunks = []
        is_markdown = path.suffix.lower() == ".md"

        if is_markdown:
            # Markdown header-based chunking
            current_chunk = []
            start_line = 1

            for idx, line in enumerate(lines, start=1):
                # Detect header break (## or ###)
                if (line.startswith("## ") or line.startswith("# ")) and current_chunk:
                    chunk_text = "\n".join(current_chunk).strip()
                    if len(chunk_text) > 30:
                        chunks.extend(self._split_oversize(current_chunk, start_line))
                    current_chunk = [line]
                    start_line = idx
                else:
                    current_chunk.append(line)

            # Final chunk
            if current_chunk:
                chunk_text = "\n".join(current_chunk).strip()
                if len(chunk_text) > 20:
                    chunks.extend(self._split_oversize(current_chunk, start_line))
        else:
            # Code sliding window: 60 lines with 10 lines overlap
            window_size = 60
            overlap = 10
            i = 0
            while i < len(lines):
                end = min(i + window_size, len(lines))
                chunk_text = "\n".join(lines[i:end]).strip()
                if chunk_text:
                    chunks.append({
                        "start_line": i + 1,
                        "end_line": end,
                        "content": chunk_text
                    })
                if end >= len(lines):
                    break
                i += (window_size - overlap)

        return chunks

    def index_all(self, force: bool = False) -> dict:
        """Scan, chunk, and index all repository memory files."""
        targets = self.collect_target_files()
        stats = {"indexed": 0, "skipped": 0, "chunks": 0, "purged": 0}

        with self.db.get_connection() as conn:
            # One writer at a time: parallel `index` runs queue here instead of hitting IntegrityError.
            conn.execute("BEGIN IMMEDIATE")
            # Purge docs whose source file vanished (FTS5 has no FK cascade, delete it by hand).
            live = {str(p.relative_to(REPO_ROOT)).replace("\\", "/") for p, _ in targets}
            for r in conn.execute("SELECT id, path FROM documents").fetchall():
                if r["path"] not in live:
                    conn.execute("DELETE FROM chunks_fts WHERE doc_id = ?", (r["id"],))
                    conn.execute("DELETE FROM documents WHERE id = ?", (r["id"],))  # chunks cascade
                    stats["purged"] += 1

            for file_path, category in targets:
                rel_path = str(file_path.relative_to(REPO_ROOT)).replace("\\", "/")
                mtime = file_path.stat().st_mtime

                # Check if already indexed and up to date
                cur = conn.execute("SELECT id, mtime, embed_mode FROM documents WHERE path = ?", (rel_path,))
                row = cur.fetchone()

                if row and not force and abs(row["mtime"] - mtime) < 1e-4                         and row["embed_mode"] == self.embedder.mode:
                    stats["skipped"] += 1
                    continue
                if row and row["embed_mode"] not in (None, self.embedder.mode):
                    print(f"[!] Embedding backend changed ({row['embed_mode']} -> {self.embedder.mode}); re-embedding {rel_path}", file=sys.stderr)

                # Delete existing entries for this doc
                if row:
                    doc_id = row["id"]
                    conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
                    conn.execute("DELETE FROM chunks_fts WHERE doc_id = ?", (doc_id,))
                    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

                # Chunk file
                raw_chunks = self.chunk_file(file_path)
                if not raw_chunks:
                    continue

                title = file_path.stem.replace("_", " ").replace("-", " ").title()

                # Insert document
                cur = conn.execute("""
                    INSERT INTO documents (path, title, category, mtime, chunk_count)
                    VALUES (?, ?, ?, ?, ?)
                """, (rel_path, title, category, mtime, len(raw_chunks)))
                doc_id = cur.lastrowid

                # Insert chunks and compute embeddings
                dims = set()
                self.embedder.fell_back = False
                for idx, ch in enumerate(raw_chunks):
                    emb = self.embedder.embed_text(ch["content"])
                    dims.add(len(emb))
                    emb_json = json.dumps(emb)

                    cur_chunk = conn.execute("""
                        INSERT INTO chunks (doc_id, chunk_index, start_line, end_line, content, embedding)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (doc_id, idx, ch["start_line"], ch["end_line"], ch["content"], emb_json))
                    chunk_id = cur_chunk.lastrowid

                    # Insert into FTS5
                    conn.execute("""
                        INSERT INTO chunks_fts (content, doc_id, chunk_id)
                        VALUES (?, ?, ?)
                    """, (ch["content"], doc_id, chunk_id))

                # Mixed sizes or any fallback vector = backend flaked mid-doc: leave NULL so the next run retries.
                if len(dims) == 1 and not self.embedder.fell_back:
                    conn.execute("UPDATE documents SET embed_mode = ? WHERE id = ?", (self.embedder.mode, doc_id))
                else:
                    print(f"[!] Inconsistent embedding sizes for {rel_path}; will retry next index", file=sys.stderr)

                stats["indexed"] += 1
                stats["chunks"] += len(raw_chunks)

            conn.commit()

        return stats


# ==============================================================================
# 4. Search & Reciprocal Rank Fusion (RRF) Retrieval Engine
# ==============================================================================

class MemorySearcher:
    """Executes hybrid BM25 + Vector search with Reciprocal Rank Fusion."""

    def __init__(self, db: MemoryDatabase, embedder: EmbeddingProvider):
        self.db = db
        self.embedder = embedder

    def _sanitize_fts_query(self, query: str) -> str:
        """Strip punctuation and format query tokens for safe SQLite FTS5 matching."""
        tokens = re.findall(r"\w+", query)
        if not tokens:
            return ""
        # Match tokens using prefix or exact matching
        return " OR ".join(f'"{t}"' for t in tokens)

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Perform hybrid search and return top-K scored chunks."""
        query = query.strip()
        if not query:
            return []

        fts_query = self._sanitize_fts_query(query)
        bm25_results = []

        with self.db.get_connection() as conn:
            # 1. BM25 Lexical Search via FTS5
            if fts_query:
                try:
                    cur = conn.execute("""
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
                        LIMIT 30;
                    """, (fts_query,))
                    bm25_results = cur.fetchall()
                except Exception:
                    bm25_results = []

            # 2. Semantic Vector Search
            self.embedder.fell_back = False
            query_emb = self.embedder.embed_text(query)
            # A fallback query vector is not comparable to stored backend vectors: BM25 only.
            mode = None if self.embedder.fell_back else self.embedder.mode
            cur = conn.execute("""
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
            """, (mode,))  # only compare vectors from the same backend
            all_chunks = cur.fetchall()

        vector_results = []
        sims: dict[int, float] = {}
        for ch in all_chunks:
            if ch["embedding"]:
                emb = json.loads(ch["embedding"])
                sim = cosine_similarity(query_emb, emb)
                sims[ch["chunk_id"]] = sim
                vector_results.append((ch, sim))

        # Sort vector results by cosine similarity descending
        vector_results.sort(key=lambda x: x[1], reverse=True)
        top_vector = vector_results[:30]

        # 3. Reciprocal Rank Fusion (RRF)
        # RRF Score = sum( w / (k + rank) )
        k = 60.0
        scores: dict[int, dict] = {}

        # Accumulate BM25 ranks
        for rank, row in enumerate(bm25_results):
            cid = row["chunk_id"]
            if cid not in scores:
                scores[cid] = {
                    "chunk_id": cid,
                    "path": row["path"],
                    "title": row["title"],
                    "category": row["category"],
                    "start_line": row["start_line"],
                    "end_line": row["end_line"],
                    "content": row["content"],
                    "rrf_score": 0.0,
                    "bm25_rank": rank + 1,
                    "vector_sim": 0.0
                }
            boost = CATEGORY_BOOSTS.get(row["category"], 1.0)
            scores[cid]["rrf_score"] += boost * (0.5 / (k + rank + 1))

        # Accumulate Vector ranks
        for rank, (row, sim) in enumerate(top_vector):
            cid = row["chunk_id"]
            if cid not in scores:
                scores[cid] = {
                    "chunk_id": cid,
                    "path": row["path"],
                    "title": row["title"],
                    "category": row["category"],
                    "start_line": row["start_line"],
                    "end_line": row["end_line"],
                    "content": row["content"],
                    "rrf_score": 0.0,
                    "bm25_rank": 999,
                    "vector_sim": sim
                }
            scores[cid]["vector_sim"] = max(scores[cid].get("vector_sim", 0.0), sim)
            boost = CATEGORY_BOOSTS.get(row["category"], 1.0)
            scores[cid]["rrf_score"] += boost * (0.5 / (k + rank + 1))

        # Relevance gate: drop vector-only noise and BM25 hits with no semantic support.
        # No comparable vectors (backend flaked/mismatch) -> trust BM25 alone.
        kept = {}
        for cid, r in scores.items():
            has_vec = cid in sims
            r["vector_sim"] = sims.get(cid, r["vector_sim"])
            if r["bm25_rank"] == 999:
                ok = r["vector_sim"] >= VECTOR_SIM_FLOOR
            else:
                # A chunk with no embedding cannot be judged semantically, so keep its BM25 hit.
                ok = not has_vec or r["vector_sim"] >= BM25_MIN_SIM
            if ok:
                kept[cid] = r
        ranked = sorted(kept.values(), key=lambda x: x["rrf_score"], reverse=True)
        return ranked[:limit]


# ==============================================================================
# 5. CLI & User-Facing Operations
# ==============================================================================

REINDEX_HINT = "Run: python memory.py index --force"


def _run_index(force: bool, embedder) -> dict:
    """Index; if the DB file is corrupt, move it aside to .bak and rebuild from scratch."""
    try:
        return MemoryIndexer(MemoryDatabase(), embedder).index_all(force=force)
    except sqlite3.DatabaseError as e:
        msg = str(e).lower()
        if "malformed" not in msg and "not a database" not in msg:
            raise  # locked, disk I/O, read-only and similar are not corruption
        bak = DB_PATH.with_name(f"{DB_PATH.name}.{int(time.time())}.bak")
        print(f"[!] Index database is corrupt ({e}); moving it to {bak.name} and rebuilding.", file=sys.stderr)
        try:
            for suffix in ("-wal", "-shm", ""):
                p = DB_PATH.with_name(DB_PATH.name + suffix)
                if p.exists():
                    os.replace(p, bak.with_name(bak.name + suffix) if suffix else bak)
        except OSError as oe:
            sys.exit(f"[!] Could not move the corrupt index aside ({oe}). Close other memory.py or serve.py processes and retry.")
        return MemoryIndexer(MemoryDatabase(), embedder).index_all(force=True)


def _positive_limit(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"limit must be an integer, got {value!r}")
    if n < 1:
        raise argparse.ArgumentTypeError("limit must be >= 1")
    return min(n, MAX_LIMIT)


def _need_index() -> bool:
    if DB_PATH.exists():
        return False
    print("No index found. Run: python memory.py index", file=sys.stderr)
    return True


def cmd_index(args):
    print("=" * 70)
    print("MEMORY FABRIC: Scanning & Indexing Repository Knowledge Base")
    print("=" * 70)
    embedder = EmbeddingProvider()
    print(f"[*] Vector Embedding Backend: {embedder.mode}")
    stats = _run_index(args.force, embedder)
    print(f"[+] Indexing Complete: {stats['indexed']} files updated, {stats['skipped']} files unchanged, {stats['chunks']} chunks stored.")
    print(f"[+] Memory Store Location: {DB_PATH}")


def cmd_search(args):
    if _need_index():
        sys.exit(1)
    embedder = EmbeddingProvider()
    try:
        searcher = MemorySearcher(MemoryDatabase(), embedder)
        results = searcher.search(args.query, limit=args.limit)
    except sqlite3.DatabaseError as e:
        print(f"Memory index is unreadable ({e}). {REINDEX_HINT}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    print("=" * 70)
    print(f"HYBRID MEMORY SEARCH: '{args.query}'")
    print(f"Engine: BM25 (FTS5) + Cosine Vector Fusion [{embedder.mode}]")
    print("=" * 70)

    if not results:
        print("No results. (If you expected some, re-index with: python memory.py index)")
        return

    for i, res in enumerate(results, start=1):
        rel_link = f"{res['path']}#L{res['start_line']}-L{res['end_line']}"
        print(f"\n[{i}] [{res['category'].upper()}] {res['title']} -> {rel_link}")
        print(f"    RRF Score: {res['rrf_score']:.5f} | Vector Sim: {res['vector_sim']:.3f} | BM25 Rank: {res['bm25_rank']}")
        print("    " + "-" * 62)
        lines = res["content"].strip().splitlines()
        preview = lines[:6]
        for l in preview:
            print(f"    | {l}")
        if len(lines) > 6:
            print(f"    | ... ({len(lines) - 6} more lines)")


def cmd_status(args):
    embedder = EmbeddingProvider()
    print("=" * 70)
    print("MEMORY FABRIC STATUS")
    print("=" * 70)
    print(f"Database Path: {DB_PATH}")
    print(f"Vector Backend: {embedder.mode}")

    if not DB_PATH.exists():
        print("Database not initialized. Run: python memory.py index")
        return

    size_kb = DB_PATH.stat().st_size / 1024
    print(f"Database Size: {size_kb:.1f} KB")

    try:
        _print_status(MemoryDatabase())
    except sqlite3.DatabaseError as e:
        print(f"Memory index is unreadable ({e}). {REINDEX_HINT}", file=sys.stderr)
        sys.exit(1)


def _print_status(db):
    with db.get_connection() as conn:
        doc_count = conn.execute("SELECT COUNT(*) FROM documents;").fetchone()[0]
        chunk_count = conn.execute("SELECT COUNT(*) FROM chunks;").fetchone()[0]
        categories = conn.execute("SELECT category, COUNT(*) FROM documents GROUP BY category;").fetchall()

        print(f"Total Documents Indexed: {doc_count}")
        print(f"Total Chunks Stored: {chunk_count}")
        print("\nDocument Breakdown:")
        for cat, cnt in categories:
            print(f"  - {cat}: {cnt} documents")


def cmd_wiki(args):
    """View or list canonical LLMWiki pages."""
    if not WIKI_DIR.is_dir():
        print(f"LLMWiki directory not found at {WIKI_DIR}")
        return

    if not args.topic:
        print("=" * 70)
        print("CANONICAL LLMWIKI TOPICS (.wiki/)")
        print("=" * 70)
        for p in sorted(WIKI_DIR.glob("*.md")):
            name = p.stem
            # extract first line or title
            title = ""
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    if line.startswith("# "):
                        title = line.replace("# ", "").strip()
                        break
            except Exception:
                pass
            print(f"  * {name:<22} - {title}")
        print("\nUsage: python memory.py wiki <topic>")
        return

    wiki_root = WIKI_DIR.resolve()
    target = (WIKI_DIR / f"{args.topic}.md").resolve()
    if not (target.is_relative_to(wiki_root) and target.is_file()):
        # Try matching stem (never leave .wiki/, even via symlinks)
        matches = [p for p in WIKI_DIR.glob("*.md")
                   if args.topic.lower() in p.stem.lower() and p.resolve().is_relative_to(wiki_root)]
        if matches:
            target = matches[0]
        else:
            print(f"Wiki topic '{args.topic}' not found in {WIKI_DIR}.")
            sys.exit(1)

    print("=" * 70)
    print(f"LLMWIKI: {target.stem.upper()} ({target.name})")
    print("=" * 70)
    print(target.read_text(encoding="utf-8"))


def cmd_sync(args):
    """Dual-sync: Update Graphify AST graph + SQLite memory store in one step."""
    print("=" * 70)
    print("DUAL-SYNC: Synchronizing Graphify AST Knowledge Graph + Memory Store")
    print("=" * 70)

    # 1. Run memory indexing
    embedder = EmbeddingProvider()
    stats = _run_index(True, embedder)
    print(f"[+] Memory Index Updated: {stats['indexed']} files, {stats['chunks']} chunks.")

    # 2. Run graphify update if installed
    try:
        proc = subprocess.run(["graphify", "update", "."], capture_output=True, text=True)
        if proc.returncode == 0:
            print("[+] Graphify AST Knowledge Graph updated successfully.")
        else:
            print(f"[!] Graphify update returned non-zero code: {proc.stderr.strip() or proc.stdout.strip()}")
    except FileNotFoundError:
        print("[!] Note: 'graphify' command not in PATH. AST graph was left untouched.")


# ==============================================================================
# Main Entry Point
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Antigravity Embedded Hybrid Memory Engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # index
    p_index = subparsers.add_parser("index", help="Index or re-index repository memory")
    p_index.add_argument("--force", action="store_true", help="Force re-indexing of all files")
    p_index.set_defaults(func=cmd_index)

    # search
    p_search = subparsers.add_parser("search", help="Hybrid BM25 + Vector search across memory")
    p_search.add_argument("query", type=str, help="Search query string")
    p_search.add_argument("--limit", type=_positive_limit, default=5,
                          help=f"Number of results, 1-{MAX_LIMIT} (default: 5; larger values are capped)")
    p_search.add_argument("--json", action="store_true", help="Output results in JSON format")
    p_search.set_defaults(func=cmd_search)

    # status
    p_status = subparsers.add_parser("status", help="Show memory store status and statistics")
    p_status.set_defaults(func=cmd_status)

    # wiki
    p_wiki = subparsers.add_parser("wiki", help="Read or list canonical LLMWiki topic pages")
    p_wiki.add_argument("topic", nargs="?", default=None, help="Topic name to display")
    p_wiki.set_defaults(func=cmd_wiki)

    # sync
    p_sync = subparsers.add_parser("sync", help="Synchronize both Graphify AST and SQLite memory store")
    p_sync.set_defaults(func=cmd_sync)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

