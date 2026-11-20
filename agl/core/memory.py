"""
agl/core/memory.py - the pure memory helpers moved out of memory.py in Phase 6a: cosine
similarity, the pure-python vectorizer, the oversize chunk split, the FTS query sanitizer
and the limit rule. Phase 6b added the hybrid rank fusion, rank_hits.
Standard library only, no I/O.
"""
import argparse
import json
import math
import re
import zlib


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two unit vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    return sum(a * b for a, b in zip(v1, v2))


def _pure_python_embed(text, dimensions=128):
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


def _split_oversize(lines, start_line, max_chars):
    """Cut a section into pieces <= MAX_CHUNK_CHARS, preferring blank-line (paragraph) breaks."""
    # Hard cap: a single giant line is sliced.
    pieces = []  # (line_no, text)
    for n, ln in enumerate(lines, start=start_line):
        for i in range(0, max(len(ln), 1), max_chars):
            pieces.append((n, ln[i:i + max_chars]))
    out, buf = [], []

    def flush(items):
        text = "\n".join(t for _, t in items).strip()
        if text:
            out.append({"start_line": items[0][0], "end_line": items[-1][0], "content": text})

    size = 0
    for item in pieces:
        if buf and size + len(item[1]) + 1 > max_chars:
            cut = next((i for i in range(len(buf) - 1, 0, -1) if not buf[i][1].strip()), None)
            head, buf = (buf[:cut], buf[cut:]) if cut else (buf, [])
            flush(head)
            size = sum(len(t) + 1 for _, t in buf)
        buf.append(item)
        size += len(item[1]) + 1
    if buf:
        flush(buf)
    return out


def _sanitize_fts_query(query: str) -> str:
    """Strip punctuation and format query tokens for safe SQLite FTS5 matching."""
    tokens = re.findall(r"\w+", query)
    if not tokens:
        return ""
    # Match tokens using prefix or exact matching
    return " OR ".join(f'"{t}"' for t in tokens)


def _positive_limit(value, max_limit):
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"limit must be an integer, got {value!r}")
    if n < 1:
        raise argparse.ArgumentTypeError("limit must be >= 1")
    return min(n, max_limit)


def _sims_and_vector_ranks(vector_rows, query_emb, fuse_depth):
    """(cosine by chunk id, [(row, sim)] best first cut to fuse_depth) over rows with a stored vector."""
    sims: dict[int, float] = {}
    vector_results = []
    for ch in vector_rows:
        if ch["embedding"]:
            emb = json.loads(ch["embedding"])
            sim = cosine_similarity(query_emb, emb)
            sims[ch["chunk_id"]] = sim
            vector_results.append((ch, sim))
    # Sort vector results by cosine similarity descending
    vector_results.sort(key=lambda x: x[1], reverse=True)
    return sims, vector_results[:fuse_depth]


def _new_hit(row, bm25_rank, vector_sim):
    """One fused result; the key order is what `memory.py search --json` prints, so never reorder it."""
    return {
        "chunk_id": row["chunk_id"],
        "path": row["path"],
        "title": row["title"],
        "category": row["category"],
        "start_line": row["start_line"],
        "end_line": row["end_line"],
        "content": row["content"],
        "rrf_score": 0.0,
        "bm25_rank": bm25_rank,
        "vector_sim": vector_sim
    }


def _add_bm25_ranks(scores, bm25_rows, *, category_boosts, rrf_k):
    """Accumulate BM25 ranks: a first sighting records that rank, every sighting adds its boosted share."""
    for rank, row in enumerate(bm25_rows):
        cid = row["chunk_id"]
        if cid not in scores:
            scores[cid] = _new_hit(row, rank + 1, 0.0)
        boost = category_boosts.get(row["category"], 1.0)
        scores[cid]["rrf_score"] += boost * (0.5 / (rrf_k + rank + 1))


def _add_vector_ranks(scores, top_vector, *, category_boosts, rrf_k):
    """Accumulate vector ranks: keep the best cosine, and a vector-only hit is marked bm25_rank 999."""
    for rank, (row, sim) in enumerate(top_vector):
        cid = row["chunk_id"]
        if cid not in scores:
            scores[cid] = _new_hit(row, 999, sim)
        scores[cid]["vector_sim"] = max(scores[cid].get("vector_sim", 0.0), sim)
        boost = category_boosts.get(row["category"], 1.0)
        scores[cid]["rrf_score"] += boost * (0.5 / (rrf_k + rank + 1))


def _clear_gate(hit, has_vec, *, vector_sim_floor, bm25_min_sim):
    """A vector-only hit must clear the vector floor; a BM25 hit needs support only when it has a vector."""
    if hit["bm25_rank"] == 999:
        return hit["vector_sim"] >= vector_sim_floor
    # A chunk with no embedding cannot be judged semantically, so keep its BM25 hit.
    return not has_vec or hit["vector_sim"] >= bm25_min_sim


def rank_hits(bm25_rows, vector_rows, query_emb, *, category_boosts, vector_sim_floor, bm25_min_sim,
              limit, fuse_depth=30, rrf_k=60.0):
    """Fuse BM25 and vector ranks (RRF, category-boosted), drop what fails the relevance gate, cut to limit."""
    # 3. Reciprocal Rank Fusion (RRF): RRF Score = sum( w / (k + rank) )
    sims, top_vector = _sims_and_vector_ranks(vector_rows, query_emb, fuse_depth)
    scores: dict[int, dict] = {}
    _add_bm25_ranks(scores, bm25_rows, category_boosts=category_boosts, rrf_k=rrf_k)
    _add_vector_ranks(scores, top_vector, category_boosts=category_boosts, rrf_k=rrf_k)

    # Relevance gate: drop vector-only noise and BM25 hits with no semantic support.
    # No comparable vectors (backend flaked/mismatch) -> trust BM25 alone.
    kept = {}
    for cid, r in scores.items():
        has_vec = cid in sims
        r["vector_sim"] = sims.get(cid, r["vector_sim"])
        if _clear_gate(r, has_vec, vector_sim_floor=vector_sim_floor, bm25_min_sim=bm25_min_sim):
            kept[cid] = r
    ranked = sorted(kept.values(), key=lambda x: x["rrf_score"], reverse=True)
    return ranked[:limit]
