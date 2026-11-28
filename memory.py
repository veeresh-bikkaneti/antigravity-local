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
import argparse
from pathlib import Path

from agl.app import memory as app_memory
from agl.platform import config, embeddings, memory_store, process
from agl.core import memory as core_memory
from agl.ui import memory_cli

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
PROJECT_ROOT = None  # set by --project: index the user's project, not this repo
PROJECT_FILES = ((".agl/checkpoint.md", "context"), ("HANDOFF.md", "context"), ("README.md", "root_doc"),
                 ("AGENTS.md", "root_doc"), ("CLAUDE.md", "root_doc"))
OLLAMA_API_BASE = os.getenv("OLLAMA_API_BASE", config.OLLAMA_BASE_URL)

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

EmbeddingProvider = embeddings.EmbeddingProvider
MemoryDatabase = memory_store.MemoryDatabase


# ==============================================================================
# Document Chunking & Indexer Engine
# ==============================================================================

class MemoryIndexer:
    """Discovers repository files, chunks them by markdown sections or lines, and indexes them."""

    def __init__(self, db: memory_store.MemoryDatabase, embedder: embeddings.EmbeddingProvider):
        self.db = db
        self.embedder = embedder

    def collect_target_files(self) -> list[tuple[Path, str]]:
        """Collect all files to index categorized by priority."""
        if PROJECT_ROOT is not None:
            return project_targets(PROJECT_ROOT)
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
                        chunks.extend(core_memory._split_oversize(current_chunk, start_line, MAX_CHUNK_CHARS))
                    current_chunk = [line]
                    start_line = idx
                else:
                    current_chunk.append(line)

            # Final chunk
            if current_chunk:
                chunk_text = "\n".join(current_chunk).strip()
                if len(chunk_text) > 20:
                    chunks.extend(core_memory._split_oversize(current_chunk, start_line, MAX_CHUNK_CHARS))
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
        return app_memory.index_all(
            force,
            store=self.db,
            embedder=self.embedder,
            targets=self.collect_target_files(),
            repo_root=PROJECT_ROOT or REPO_ROOT,
            chunk=self.chunk_file,
            warn=memory_cli.render_index_warn
        )


def project_targets(root: Path) -> list[tuple[Path, str]]:
    """What --project indexes: the shared checkpoint, the hand-off, the project's own guides and docs/*.md."""
    targets = [(p, "wiki") for p in sorted((root / ".agl" / "wiki").glob("*.md"))]
    targets += [(root / name, cat) for name, cat in PROJECT_FILES if (root / name).is_file()]
    targets += [(p, "doc") for p in sorted((root / "docs").glob("*.md"))]
    return [(p, cat) for p, cat in targets if p.resolve().is_relative_to(root)]  # a link must not leave it


def use_project(path) -> Path:
    """Root the index at the user's project: <project>/.agl/memory, kept out of git by its own .gitignore."""
    global PROJECT_ROOT, DB_DIR, DB_PATH, WIKI_DIR
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        sys.exit(f"[!] --project {path} is not a folder.")
    PROJECT_ROOT, DB_DIR, WIKI_DIR = root, root / ".agl" / "memory", root / ".agl" / "wiki"
    DB_PATH = DB_DIR / "index.sqlite"
    DB_DIR.mkdir(parents=True, exist_ok=True)
    ignore = DB_DIR / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")
    return root


def index_for_probe() -> dict:
    """Index the fabric for the pre-shell check; the body used to live inline in run.py."""
    database = memory_store.MemoryDatabase(DB_PATH)
    provider = embeddings.EmbeddingProvider(OLLAMA_API_BASE)
    return MemoryIndexer(database, provider).index_all(force=False)


# ==============================================================================
# Search & Reciprocal Rank Fusion (RRF) Retrieval Engine
# ==============================================================================

class MemorySearcher:
    """Executes hybrid BM25 + Vector search with Reciprocal Rank Fusion."""

    def __init__(self, db: memory_store.MemoryDatabase, embedder: embeddings.EmbeddingProvider):
        self.db = db
        self.embedder = embedder

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Perform hybrid search and return top-K scored chunks."""
        return app_memory.search(
            query, limit,
            store=self.db,
            embedder=self.embedder,
            category_boosts=CATEGORY_BOOSTS,
            vector_sim_floor=VECTOR_SIM_FLOOR,
            bm25_min_sim=BM25_MIN_SIM
        )


# ==============================================================================
# CLI & User-Facing Operations
# ==============================================================================

REINDEX_HINT = memory_cli.REINDEX_HINT  # the text itself lives in agl.ui.memory_cli


def _run_index(force: bool, embedder) -> dict:
    """Index; if the DB file is corrupt, move it aside to .bak and rebuild from scratch."""
    try:
        return MemoryIndexer(memory_store.MemoryDatabase(DB_PATH), embedder).index_all(force=force)
    except memory_store.DatabaseError as e:
        msg = str(e).lower()
        if "malformed" not in msg and "not a database" not in msg:
            raise  # locked, disk I/O, read-only and similar are not corruption
        bak = DB_PATH.with_name(f"{DB_PATH.name}.{int(time.time())}.bak")
        memory_cli.render_index_corrupt(str(e), bak.name)
        try:
            for suffix in ("-wal", "-shm", ""):
                p = DB_PATH.with_name(DB_PATH.name + suffix)
                if p.exists():
                    os.replace(p, bak.with_name(bak.name + suffix) if suffix else bak)
        except OSError as oe:
            sys.exit(f"[!] Could not move the corrupt index aside ({oe}). Close other memory.py or serve.py processes and retry.")
        return MemoryIndexer(memory_store.MemoryDatabase(DB_PATH), embedder).index_all(force=True)


def _positive_limit(value: str, max_limit: int = MAX_LIMIT) -> int:
    return core_memory._positive_limit(value, max_limit)


def cmd_index(args):
    memory_cli.render_index_header()
    embedder = embeddings.EmbeddingProvider(OLLAMA_API_BASE)
    memory_cli.render_index_backend(embedder.mode)
    stats = _run_index(args.force, embedder)
    memory_cli.render_index_done(stats, DB_PATH)


def cmd_search(args):
    if not DB_PATH.exists():
        memory_cli.render_no_index()
        sys.exit(1)
    embedder = embeddings.EmbeddingProvider(OLLAMA_API_BASE)
    try:
        searcher = MemorySearcher(memory_store.MemoryDatabase(DB_PATH), embedder)
        results = searcher.search(args.query, limit=args.limit)
    except memory_store.DatabaseError as e:
        memory_cli.render_search_unreadable(str(e))
        sys.exit(1)

    if args.json:
        memory_cli.render_search_json(results)
        return

    memory_cli.render_search_header(args.query, embedder.mode)

    if not results:
        memory_cli.render_search_empty()
        return

    memory_cli.render_search_results(results)


def cmd_status(args):
    embedder = embeddings.EmbeddingProvider(OLLAMA_API_BASE)
    memory_cli.render_status_header(DB_PATH, embedder.mode)

    if not DB_PATH.exists():
        memory_cli.render_status_uninitialized()
        return

    size_kb = DB_PATH.stat().st_size / 1024
    memory_cli.render_status_size(size_kb)

    try:
        db = memory_store.MemoryDatabase(DB_PATH)
        with db.get_connection() as conn:
            # moved in Phase 6d: the counts SQL lives in agl.platform.memory_store.
            doc_count, chunk_count = db.counts(conn)
            categories = db.category_counts(conn)
        memory_cli.render_status_counts(doc_count, chunk_count, categories)
    except memory_store.DatabaseError as e:
        memory_cli.render_status_unreadable(str(e))
        sys.exit(1)


def cmd_wiki(args):
    """View or list canonical LLMWiki pages."""
    if not WIKI_DIR.is_dir():
        memory_cli.render_wiki_missing_dir(WIKI_DIR)
        return

    if not args.topic:
        entries = []
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
            entries.append((name, title))
        memory_cli.render_wiki_list(entries)
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
            memory_cli.render_wiki_not_found(args.topic, WIKI_DIR)
            sys.exit(1)

    memory_cli.render_wiki_page(target.stem.upper(), target.name, target.read_text(encoding="utf-8"))


def cmd_sync(args):
    """Dual-sync: Update Graphify AST graph + SQLite memory store in one step."""
    memory_cli.render_sync_header()

    # 1. Run memory indexing
    embedder = embeddings.EmbeddingProvider(OLLAMA_API_BASE)
    stats = _run_index(True, embedder)
    memory_cli.render_sync_memory_done(stats)

    # 2. Run graphify update if installed
    try:
        proc = process.run(["graphify", "update", "."], capture_output=True, text=True, timeout=60)
        if proc.returncode == 0:
            memory_cli.render_sync_graphify_ok()
        else:
            memory_cli.render_sync_graphify_failed(proc.stderr.strip() or proc.stdout.strip())
    except FileNotFoundError:
        memory_cli.render_sync_graphify_missing()
    except process.TimeoutExpired:
        memory_cli.render_sync_graphify_failed("timed out after 60s")


# ==============================================================================
# Main Entry Point
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Antigravity Embedded Hybrid Memory Engine")
    parser.add_argument("--project", metavar="PATH",
                        help="index this project into <PATH>/.agl/memory instead of this repo")
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
    if args.project:
        use_project(args.project)
    args.func(args)


if __name__ == "__main__":
    main()

