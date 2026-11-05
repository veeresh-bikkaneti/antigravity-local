"""serve.py: limit validation, empty results, diagram symlink escape."""
import json
import os
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


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class ServeHardening(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "docs" / "diagrams").mkdir(parents=True)
        (root / "docs" / "diagrams" / "a.html").write_text("<h1>diagram</h1>", encoding="utf-8")
        (root / "outside.html").write_text("OUTSIDE SECRET", encoding="utf-8")
        (root / "README.md").write_text("# Zebra\n\nzebra memory fabric hybrid retrieval notes for testing\n", encoding="utf-8")
        self.root = root
        self._saved = (memory.REPO_ROOT, memory.WIKI_DIR, serve.DIAGRAMS)
        memory.REPO_ROOT, memory.WIKI_DIR, serve.DIAGRAMS = root, root / ".wiki", root / "docs" / "diagrams"
        self.server = serve.build_server("127.0.0.1", 0, root / "i.sqlite", "http://127.0.0.1:9")
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close()
        memory.REPO_ROOT, memory.WIKI_DIR, serve.DIAGRAMS = self._saved
        self.tmp.cleanup()

    def test_bad_limits_are_400(self):
        for lim in ("0", "-1", "", "abc"):
            self.assertEqual(get(f"{self.base}/api/search?q=zebra&limit={lim}")[0], 400, repr(lim))

    def test_large_limit_is_capped_not_rejected(self):
        code, body = get(f"{self.base}/api/search?q=zebra&limit=999")
        self.assertEqual(code, 200)
        self.assertLessEqual(len(json.loads(body)["results"]), serve.MAX_LIMIT)

    def test_garbage_query_returns_empty_list(self):
        code, body = get(f"{self.base}/api/search?q=zzzzqqqxxyy")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["results"], [])

    def test_diagram_symlink_escape_is_404(self):
        link = self.root / "docs" / "diagrams" / "evil.html"
        try:
            os.symlink(self.root / "outside.html", link)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this OS/user")
        code, body = get(f"{self.base}/diagrams/evil.html")
        self.assertEqual(code, 404)
        self.assertNotIn(b"OUTSIDE SECRET", body)
        self.assertEqual(get(f"{self.base}/diagrams/a.html")[0], 200)


if __name__ == "__main__":
    unittest.main()
