"""C2 relay: a small HTTP server on 127.0.0.1 that forwards every request to Ollama, unchanged except two:
chat requests bigger than the window are trimmed, and /api/show reports the real window. Replies stream back
as they arrive, so NDJSON streaming and tool calls pass through intact. It never changes Ollama's own settings.

The decisions arrive as callables (`trim`, `patch_show`) from the root relay.py, so this module holds only I/O.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agl.platform import http

HOST = "127.0.0.1"   # loopback only: the relay is never reachable from another machine
TIMEOUT = 600        # a long answer from a big model can take minutes
CHUNK = 8192
SKIP_HEADERS = {"host", "content-length", "connection", "accept-encoding"}


class Relay(BaseHTTPRequestHandler):
    """One request. serve() binds upstream, window and the decisions on a subclass."""
    upstream = window = chat_paths = None
    trim = patch_show = log = None  # staticmethods set by serve()

    def log_message(self, *args):  # quiet: our own log line says what matters
        pass

    def _forward(self, method):
        size = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(size) if size else None
        path = self.path.split("?", 1)[0]
        if data and path in self.chat_paths:
            data = self._trimmed(data)
        headers = {k: v for k, v in self.headers.items() if k.lower() not in SKIP_HEADERS}
        try:
            resp = http.open_url(self.upstream + self.path, timeout=TIMEOUT, method=method, headers=headers,
                                 data=data)
        except http.ANSWERED_ERRORS as exc:
            resp = exc  # Ollama answered with an error: pass it through as it is
        except http.NETWORK_ERRORS as exc:
            self.send_error(502, f"Ollama did not answer at {self.upstream}: {exc.__class__.__name__}")
            return
        with resp:
            status = getattr(resp, "status", None) or getattr(resp, "code", 502)
            if path == "/api/show" and status == 200:
                self._send(status, resp.headers, self._shown(resp.read()))
                return
            self.send_response(status)
            for k, v in resp.headers.items():
                if k.lower() not in ("content-length", "connection", "transfer-encoding"):
                    self.send_header(k, v)
            self.send_header("Connection", "close")
            self.end_headers()
            while True:
                chunk = resp.read1(CHUNK) if hasattr(resp, "read1") else resp.read(CHUNK)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()

    def _trimmed(self, data):
        try:
            body = json.loads(data.decode("utf-8"))
        except ValueError:
            return data  # not JSON: forward it as it is and let Ollama answer
        new, dropped = self.trim(body, self.window)
        if not dropped:
            return data
        self.log(f"[relay] trimmed {dropped} older messages to fit the {self.window}-token window")
        return json.dumps(new, ensure_ascii=False).encode("utf-8")

    def _shown(self, raw):
        try:
            return json.dumps(self.patch_show(json.loads(raw.decode("utf-8")), self.window)).encode("utf-8")
        except ValueError:
            return raw

    def _send(self, status, headers, payload):
        self.send_response(status)
        self.send_header("Content-Type", headers.get("Content-Type", "application/json"))
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self._forward("GET")

    def do_POST(self):
        self._forward("POST")

    def do_HEAD(self):
        self._forward("HEAD")

    def do_DELETE(self):
        self._forward("DELETE")


def serve(port, upstream, window, *, trim, patch_show, chat_paths, log=print):
    """Start the relay in a daemon thread and return the server. Call .shutdown() to stop it."""
    bound = type("BoundRelay", (Relay,), {
        "upstream": upstream.rstrip("/"), "window": window, "chat_paths": tuple(chat_paths),
        "trim": staticmethod(trim), "patch_show": staticmethod(patch_show), "log": staticmethod(log)})
    server = ThreadingHTTPServer((HOST, port), bound)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
