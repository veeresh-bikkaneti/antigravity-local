#!/usr/bin/env python3
"""
serve.py - tiny web UI + JSON API over the memory fabric. Standard library only.

Port rule: no fixed port. Default is port 0, so the OS hands us a free one and we print it.
Override with --port N or PORT=N. Local default binds 127.0.0.1 only; the Docker image sets HOST=0.0.0.0.

  GET /             search page
  GET /healthz      {"status": "ok", ...}
  GET /api/search   ?q=<text>&limit=<1-20>
  GET /diagrams/X   interactive Archify diagrams from docs/diagrams
"""

import argparse
import functools
import html
import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import memory
from agl.platform.embeddings import EmbeddingProvider
from agl.platform.memory_store import MemoryDatabase

DIAGRAMS = memory.REPO_ROOT / "docs" / "diagrams"
MAX_QUERY_CHARS = 500
MAX_LIMIT = memory.MAX_LIMIT
DIAGRAM_NAME = re.compile(r"^[\w.-]+\.html$")

PAGE = """<!doctype html><meta charset="utf-8"><title>Local Antigravity Memory</title>
<style>body{font:16px system-ui;max-width:46rem;margin:2rem auto;padding:0 1rem}
input{width:75%%;padding:.5rem}pre{white-space:pre-wrap;background:#f4f4f4;padding:.6rem;border-radius:6px}</style>
<h1>Local Antigravity Memory</h1>
<p>Ask the memory fabric a question. Backend: <b>%(backend)s</b>.</p>
<form id=f><input id=q placeholder="how does hardware offloading work?" autofocus> <button>Search</button></form>
<div id=out></div>
<h3>Diagrams</h3><ul>%(diagrams)s</ul>
<script>
f.onsubmit=async e=>{e.preventDefault();out.textContent='...';
const r=await fetch('/api/search?q='+encodeURIComponent(q.value));const j=await r.json();
out.textContent='';(j.results||[]).forEach(x=>{const h=document.createElement('h4');
h.textContent=x.path+' (L'+x.start_line+'-'+x.end_line+')';const p=document.createElement('pre');
p.textContent=x.content.slice(0,600);out.append(h,p)});if(!(j.results||[]).length)out.textContent=j.error||'No results.'};
</script>"""


def _search_params(qs):
    """Parse ?q=&limit= into (q, limit). On a bad request limit is None and err is the 400 body."""
    q = (qs.get("q") or [""])[0].strip()
    if not q or len(q) > MAX_QUERY_CHARS:
        return None, None, f"q must be 1-{MAX_QUERY_CHARS} characters"
    try:
        limit = int((qs.get("limit") or ["5"])[0])
    except ValueError:
        return None, None, "limit must be an integer"
    if limit < 1:
        return None, None, "limit must be >= 1"
    return q, min(limit, MAX_LIMIT), None


def build_server(host, port, db_path=None, ollama_url=memory.OLLAMA_API_BASE):
    """Index memory (cheap when unchanged) and return a ready, not-yet-serving server."""
    db = MemoryDatabase(db_path if db_path is not None else memory.DB_PATH)
    embedder = EmbeddingProvider(ollama_url if ollama_url is not None else memory.OLLAMA_API_BASE)
    memory.MemoryIndexer(db, embedder).index_all()
    searcher = memory.MemorySearcher(db, embedder)
    # ponytail: one global lock, because EmbeddingProvider.fell_back is shared state that search
    # reads right after embedding. Per-request provider instances if concurrency ever matters.
    lock = threading.Lock()
    return Server((host, port), handler_factory(db, embedder, searcher, lock))


class Handler(BaseHTTPRequestHandler):
    def __init__(self, db, embedder, searcher, lock, *args, **kwargs):
        self.db, self.embedder, self.searcher, self.lock = db, embedder, searcher, lock
        BaseHTTPRequestHandler.__init__(self, *args, **kwargs)

    def log_message(self, fmt, *args):
        sys.stderr.write("[serve] " + fmt % args + "\n")

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj).encode("utf-8"))

    def _healthz(self, url):
        with self.db.get_connection() as c:
            n = c.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        return self._json(200, {"status": "ok", "backend": self.embedder.mode, "documents": n})

    def _search(self, url):
        qs = parse_qs(url.query, keep_blank_values=True)  # blank limit= must 400, not default
        q, limit, err = _search_params(qs)
        if err:
            return self._json(400, {"error": err})
        with self.lock:
            results = self.searcher.search(q, limit=limit)
        return self._json(200, {"query": q, "results": results})

    def _diagram(self, url):
        name = url.path[len("/diagrams/"):]
        f = DIAGRAMS / name
        # resolve() follows symlinks: a link pointing outside docs/diagrams must 404.
        if DIAGRAM_NAME.match(name) and f.is_file() and f.resolve().is_relative_to(DIAGRAMS.resolve()):
            return self._send(200, f.read_bytes(), "text/html")
        return self._json(404, {"error": "not found"})

    def _index(self, url):
        links = "".join(
            f'<li><a href="/diagrams/{html.escape(p.name)}">{html.escape(p.stem)}</a></li>'
            for p in sorted(DIAGRAMS.glob("*.html")))
        return self._send(200, (PAGE % {"backend": html.escape(self.embedder.mode), "diagrams": links}).encode("utf-8"), "text/html")

    # Exact routes first: a prefix match on "/" would swallow every unknown route.
    ROUTES = (("/healthz", "_healthz", True), ("/api/search", "_search", True),
              ("/diagrams/", "_diagram", False), ("/", "_index", True))

    def do_GET(self):
        url = urlparse(self.path)
        for prefix, name, exact in self.ROUTES:
            if (url.path == prefix) if exact else url.path.startswith(prefix):
                return getattr(self, name)(url)
        return self._json(404, {"error": "not found"})


def handler_factory(db, embedder, searcher, lock):
    """Handler bound to this server's db, embedder, searcher and lock."""
    return functools.partial(Handler, db, embedder, searcher, lock)


class Server(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets two processes bind one port (silent hijack); POSIX needs it for restarts.
    allow_reuse_address = os.name != "nt"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Serve the memory fabric on a free local port")
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "0")),
                    help="0 (default) = let the OS pick a free port")
    args = ap.parse_args(argv)
    server = build_server(args.host, args.port)
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    print(f"Serving on http://{shown}:{server.server_address[1]}", flush=True)
    print("Stop with Ctrl+C (in Docker: docker stop <name>).", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
