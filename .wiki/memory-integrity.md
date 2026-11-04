# Memory Index Integrity

How `memory.py` keeps its SQLite index honest. Spec: `docs/MEMORY_SPEC.md` (Section 3 and 4).

- **Stable fallback vectors**: pure-Python embeddings hash with `zlib.crc32`, so an index built today still matches tomorrow's queries.
- **Backend-aware**: every document stores `embed_mode`. Switching Ollama and the fallback re-embeds on the next `python memory.py index`. `NULL` means retry.
- **Same-backend search only**: vectors from different backends are never compared. A fallback query skips the vector leg (BM25 only).
- **No ghosts**: deleted or renamed source files are purged from documents, chunks and the FTS table.
- **Connections close**: `get_connection()` commits, rolls back on error, and always closes.
- **Run the checks**: `python -m unittest tests.test_memory_integrity tests.test_memory_determinism` (name the modules; `discover` does not work here).
