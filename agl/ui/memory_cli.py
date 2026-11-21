"""Pure renderers for memory.py's CLI commands: every printed string lives here.

The ui layer: terminal text only, with output injected as ``out`` (``print`` for
stdout, ``_write_err`` for stderr, both resolved at call time so redirecting
sys.stdout/sys.stderr keeps working). No literal print() calls.
"""

import json
import sys

REINDEX_HINT = "Run: python memory.py index --force"


def _write_err(msg) -> None:
    """One stderr line, byte-identical to print(msg, file=sys.stderr)."""
    sys.stderr.write(msg + "\n")


def render_index_header(out=print) -> None:
    out("=" * 70)
    out("MEMORY FABRIC: Scanning & Indexing Repository Knowledge Base")
    out("=" * 70)


def render_index_backend(mode, out=print) -> None:
    out(f"[*] Vector Embedding Backend: {mode}")


def render_index_done(stats, db_path, out=print) -> None:
    out(f"[+] Indexing Complete: {stats['indexed']} files updated, {stats['skipped']} files unchanged, {stats['chunks']} chunks stored.")
    out(f"[+] Memory Store Location: {db_path}")


def render_index_corrupt(error, bak_name, out=_write_err) -> None:
    out(f"[!] Index database is corrupt ({error}); moving it to {bak_name} and rebuilding.")


def render_index_warn(msg, out=_write_err) -> None:
    out(msg)


def render_no_index(out=_write_err) -> None:
    out("No index found. Run: python memory.py index")


def render_search_unreadable(error, out=_write_err) -> None:
    out(f"Memory index is unreadable ({error}). {REINDEX_HINT}")


def render_search_json(results, out=print) -> None:
    out(json.dumps(results, indent=2))


def render_search_header(query, mode, out=print) -> None:
    out("=" * 70)
    out(f"HYBRID MEMORY SEARCH: '{query}'")
    out(f"Engine: BM25 (FTS5) + Cosine Vector Fusion [{mode}]")
    out("=" * 70)


def render_search_empty(out=print) -> None:
    out("No results. (If you expected some, re-index with: python memory.py index)")


def render_search_results(results, out=print) -> None:
    for i, res in enumerate(results, start=1):
        rel_link = f"{res['path']}#L{res['start_line']}-L{res['end_line']}"
        out(f"\n[{i}] [{res['category'].upper()}] {res['title']} -> {rel_link}")
        out(f"    RRF Score: {res['rrf_score']:.5f} | Vector Sim: {res['vector_sim']:.3f} | BM25 Rank: {res['bm25_rank']}")
        out("    " + "-" * 62)
        lines = res["content"].strip().splitlines()
        preview = lines[:6]
        for line in preview:
            out(f"    | {line}")
        if len(lines) > 6:
            out(f"    | ... ({len(lines) - 6} more lines)")


def render_status_header(db_path, mode, out=print) -> None:
    out("=" * 70)
    out("MEMORY FABRIC STATUS")
    out("=" * 70)
    out(f"Database Path: {db_path}")
    out(f"Vector Backend: {mode}")


def render_status_uninitialized(out=print) -> None:
    out("Database not initialized. Run: python memory.py index")


def render_status_size(size_kb, out=print) -> None:
    out(f"Database Size: {size_kb:.1f} KB")


def render_status_counts(doc_count, chunk_count, categories, out=print) -> None:
    out(f"Total Documents Indexed: {doc_count}")
    out(f"Total Chunks Stored: {chunk_count}")
    out("\nDocument Breakdown:")
    for cat, cnt in categories:
        out(f"  - {cat}: {cnt} documents")


def render_status_unreadable(error, out=_write_err) -> None:
    out(f"Memory index is unreadable ({error}). {REINDEX_HINT}")


def render_wiki_missing_dir(wiki_dir, out=print) -> None:
    out(f"LLMWiki directory not found at {wiki_dir}")


def render_wiki_list(entries, out=print) -> None:
    out("=" * 70)
    out("CANONICAL LLMWIKI TOPICS (.wiki/)")
    out("=" * 70)
    for name, title in entries:
        out(f"  * {name:<22} - {title}")
    out("\nUsage: python memory.py wiki <topic>")


def render_wiki_not_found(topic, wiki_dir, out=print) -> None:
    out(f"Wiki topic '{topic}' not found in {wiki_dir}.")


def render_wiki_page(title_upper, file_name, content, out=print) -> None:
    out("=" * 70)
    out(f"LLMWIKI: {title_upper} ({file_name})")
    out("=" * 70)
    out(content)


def render_sync_header(out=print) -> None:
    out("=" * 70)
    out("DUAL-SYNC: Synchronizing Graphify AST Knowledge Graph + Memory Store")
    out("=" * 70)


def render_sync_memory_done(stats, out=print) -> None:
    out(f"[+] Memory Index Updated: {stats['indexed']} files, {stats['chunks']} chunks.")


def render_sync_graphify_ok(out=print) -> None:
    out("[+] Graphify AST Knowledge Graph updated successfully.")


def render_sync_graphify_failed(text, out=print) -> None:
    out(f"[!] Graphify update returned non-zero code: {text}")


def render_sync_graphify_missing(out=print) -> None:
    out("[!] Note: 'graphify' command not in PATH. AST graph was left untouched.")
