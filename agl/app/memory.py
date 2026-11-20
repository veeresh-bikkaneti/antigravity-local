"""The memory use cases: hybrid search and the index run, both printing nothing.

Phase 6b moved them here from MemorySearcher.search and MemoryIndexer.index_all; the SQL lives in
agl.platform.memory_store and the ranking math in agl.core.memory, so this file is only orchestration.
"""
import json

from agl.core import memory as core_memory

FUSE_DEPTH = 30  # rows kept from each half before fusing: today's BM25 LIMIT and the vector cut


def _bm25_ranked(store, conn, fts_query):
    """The BM25 hits, or [] when the query has no tokens or FTS5 rejects the match expression."""
    if not fts_query:
        return []
    try:
        return store.fts_candidates(conn, fts_query, FUSE_DEPTH)
    except Exception:
        return []


def _query_vector(embedder, query):
    """The query vector and the embed mode to compare it with: None when the vector fell back."""
    embedder.fell_back = False
    vector = embedder.embed_text(query)
    # A fallback query vector is not comparable to stored backend vectors: BM25 only.
    return vector, (None if embedder.fell_back else embedder.mode)


def search(query, limit=5, *, store, embedder, category_boosts, vector_sim_floor, bm25_min_sim):
    """The fused top-`limit` chunks for `query`: one connection, two queries, one ranking pass."""
    query = query.strip()
    if not query:
        return []

    fts_query = core_memory._sanitize_fts_query(query)
    with store.get_connection() as conn:
        bm25_rows = _bm25_ranked(store, conn, fts_query)
        query_emb, mode = _query_vector(embedder, query)
        vector_rows = store.vector_chunks(conn, mode)  # only compare vectors from the same backend
    return core_memory.rank_hits(bm25_rows, vector_rows, query_emb,
                                 category_boosts=category_boosts,
                                 vector_sim_floor=vector_sim_floor,
                                 bm25_min_sim=bm25_min_sim,
                                 limit=limit, fuse_depth=FUSE_DEPTH)


def _rel_path(file_path, repo_root):
    """The path stored on the document row: relative and forward-slashed, so it matches on every OS."""
    return str(file_path.relative_to(repo_root)).replace("\\", "/")


def _purge_vanished(store, conn, targets, repo_root):
    """Drop documents whose source file is gone (FTS5 has no FK cascade); returns how many went."""
    live = {_rel_path(p, repo_root) for p, _ in targets}
    purged = 0
    for r in store.document_paths(conn):
        if r["path"] not in live:
            store.prune_document(conn, r["id"])
            purged += 1
    return purged


def _is_current(row, mtime, force, embed_mode):
    """True when the row is here, not forced, unchanged on disk and embedded by this same backend."""
    return bool(row and not force and abs(row["mtime"] - mtime) < 1e-4
                and row["embed_mode"] == embed_mode)


def _warn_backend_change(row, embed_mode, rel_path, warn):
    """Say it out loud when the stored vectors came from a backend other than the one in use now."""
    if row and row["embed_mode"] not in (None, embed_mode):
        warn(f"[!] Embedding backend changed ({row['embed_mode']} -> {embed_mode}); re-embedding {rel_path}")


def _store_chunks(store, conn, doc_id, raw_chunks, embedder):
    """Embed and insert every chunk of one document; returns the set of embedding sizes seen."""
    dims = set()
    embedder.fell_back = False
    for idx, ch in enumerate(raw_chunks):
        emb = embedder.embed_text(ch["content"])
        dims.add(len(emb))
        store.insert_chunk(conn, doc_id, idx, ch["start_line"], ch["end_line"], ch["content"], json.dumps(emb))
    return dims


def _index_document(store, conn, file_path, category, *, embedder, repo_root, chunk, warn, force):
    """Index one target file: (skipped, chunks stored). Skipped means 'already current', not 'empty'."""
    rel_path = _rel_path(file_path, repo_root)
    mtime = file_path.stat().st_mtime
    row = store.document_row(conn, rel_path)  # Check if already indexed and up to date
    if _is_current(row, mtime, force, embedder.mode):
        return True, 0
    _warn_backend_change(row, embedder.mode, rel_path, warn)
    if row:  # Delete existing entries for this doc
        store.clear_document(conn, row["id"])
    raw_chunks = chunk(file_path)  # Chunk file
    if not raw_chunks:
        return False, 0
    title = file_path.stem.replace("_", " ").replace("-", " ").title()
    doc_id = store.insert_document(conn, rel_path, title, category, mtime, len(raw_chunks))
    dims = _store_chunks(store, conn, doc_id, raw_chunks, embedder)
    # Mixed sizes or any fallback vector = backend flaked mid-doc: leave NULL so the next run retries.
    if len(dims) == 1 and not embedder.fell_back:
        store.set_embed_mode(conn, doc_id, embedder.mode)
    else:
        warn(f"[!] Inconsistent embedding sizes for {rel_path}; will retry next index")
    return False, len(raw_chunks)


def index_all(force=False, *, store, embedder, targets, repo_root, chunk, warn):
    """Index every target file; returns the run's stats (indexed, skipped, chunks, purged, in that order)."""
    stats = {"indexed": 0, "skipped": 0, "chunks": 0, "purged": 0}
    with store.get_connection() as conn:
        store.begin_immediate(conn)  # one writer at a time
        stats["purged"] += _purge_vanished(store, conn, targets, repo_root)
        for file_path, category in targets:
            skipped, stored = _index_document(store, conn, file_path, category, embedder=embedder,
                                              repo_root=repo_root, chunk=chunk, warn=warn, force=force)
            if skipped:
                stats["skipped"] += 1
            elif stored:
                stats["indexed"] += 1
                stats["chunks"] += stored
        conn.commit()
    return stats
