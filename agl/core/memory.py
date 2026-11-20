"""
agl/core/memory.py - the pure memory helpers moved out of memory.py in Phase 6a: cosine
similarity, the pure-python vectorizer, the oversize chunk split, the FTS query sanitizer
and the limit rule. Standard library only, no I/O.
"""
import argparse
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
