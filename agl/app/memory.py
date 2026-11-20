"""The memory search use case: hybrid BM25 + vector fusion for one query, printing nothing.

Phase 6b moved it here from MemorySearcher.search; the SQL lives in agl.platform.memory_store and the
ranking math in agl.core.memory, so this file is only the orchestration between the two.
"""
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
