"""serve.py: free-port binding, API contract, and path-traversal safety."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import memory  # noqa: E402
import serve  # noqa: E402

DEAD_OLLAMA = "http://127.0.0.1:9"


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class ServeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "docs" / "diagrams").mkdir(parents=True)
        (root / "docs" / "diagrams" / "a.html").write_text("<h1>diagram</h1>", encoding="utf-8")
        (root / "README.md").write_text("# Zebra\n\nzebra memory fabric hybrid retrieval notes for testing\n", encoding="utf-8")
        (root / "secret.txt").write_text("TOP SECRET", encoding="utf-8")
        self._saved = (memory.REPO_ROOT, memory.WIKI_DIR, serve.DIAGRAMS)
        memory.REPO_ROOT, memory.WIKI_DIR, serve.DIAGRAMS = root, root / ".wiki", root / "docs" / "diagrams"
        self.servers = []
        self.base = self.start()

    def start(self):
        s = serve.build_server("127.0.0.1", 0, Path(self.tmp.name) / f"i{len(self.servers)}.sqlite", DEAD_OLLAMA)
        threading.Thread(target=s.serve_forever, daemon=True).start()
        self.servers.append(s)
        return f"http://127.0.0.1:{s.server_address[1]}"

    def tearDown(self):
        for s in self.servers:
            s.shutdown(); s.server_close()
        memory.REPO_ROOT, memory.WIKI_DIR, serve.DIAGRAMS = self._saved
        self.tmp.cleanup()

    def test_port_zero_gets_a_real_free_port_and_two_servers_differ(self):
        other = self.start()
        self.assertNotEqual(self.base, other)
        self.assertGreater(int(self.base.rsplit(":", 1)[1]), 0)

    def test_healthz(self):
        code, body = get(self.base + "/healthz")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["status"], "ok")

    def test_search_finds_indexed_doc(self):
        code, body = get(self.base + "/api/search?q=zebra+fabric&limit=3")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["results"][0]["path"], "README.md")

    def test_search_rejects_empty_and_oversized_query(self):
        self.assertEqual(get(self.base + "/api/search?q=")[0], 400)
        self.assertEqual(get(self.base + "/api/search?q=" + "a" * 501)[0], 400)

    def test_limit_is_clamped(self):
        code, body = get(self.base + "/api/search?q=zebra&limit=99999")
        self.assertEqual(code, 200)
        self.assertLessEqual(len(json.loads(body)["results"]), 20)
        self.assertEqual(get(self.base + "/api/search?q=zebra&limit=abc")[0], 400)

    def test_diagram_served_and_traversal_blocked(self):
        self.assertEqual(get(self.base + "/diagrams/a.html")[0], 200)
        for evil in ("/diagrams/..%2f..%2fsecret.txt", "/diagrams/../secret.txt",
                     "/diagrams/%2e%2e/secret.txt", "/diagrams/a.html%00", "/diagrams/secret.txt"):
            code, body = get(self.base + evil)
            self.assertIn(code, (400, 404), evil)
            self.assertNotIn(b"TOP SECRET", body, evil)

    def test_index_page_and_unknown_route(self):
        code, body = get(self.base + "/")
        self.assertEqual(code, 200)
        self.assertIn(b"<form", body)
        self.assertEqual(get(self.base + "/nope")[0], 404)


if __name__ == "__main__":
    unittest.main()
