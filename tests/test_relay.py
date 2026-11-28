"""C2 relay: the trim and /api/show decisions, and one real round trip through the relay to a fake Ollama.

The fake Ollama is a local ThreadingHTTPServer on 127.0.0.1 with port 0, so nothing leaves this machine.
"""
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import relay  # noqa: E402
from agl.core import relay_trim  # noqa: E402
from agl.platform import http, relay_server  # noqa: E402


def msg(role, n, **extra):
    return {"role": role, "content": "x" * n, **extra}


def chat(*middle, tail=6):
    return {"model": "m", "stream": True, "tools": [{"type": "function", "function": {"name": "read"}}],
            "messages": [msg("system", 400), msg("user", 40)] + list(middle) + [msg("user", 40)] * tail}


class Trim(unittest.TestCase):
    def test_small_request_is_unchanged(self):
        body = chat(msg("assistant", 40))
        self.assertEqual(relay_trim.trim(body, 8192), (body, 0))

    def test_big_request_keeps_system_goal_tools_and_latest(self):
        body = chat(*[msg("assistant", 4000) for _ in range(10)])
        new, dropped = relay_trim.trim(body, 8192)
        self.assertGreater(dropped, 0)
        self.assertLessEqual(relay_trim.tokens(new), 8192 - relay_trim.RESERVE)
        self.assertEqual(new["messages"][:2], body["messages"][:2])
        self.assertEqual(new["messages"][-6:], body["messages"][-6:])
        self.assertEqual(new["tools"], body["tools"])
        self.assertIn(f"{dropped} earlier messages", new["messages"][2]["content"])

    def test_a_tool_result_goes_with_its_call(self):
        call = msg("assistant", 4000, tool_calls=[{"function": {"name": "read"}}])
        body = chat(call, msg("tool", 4000), call, msg("tool", 4000), msg("assistant", 10))
        new, dropped = relay_trim.trim(body, 6000)
        self.assertEqual(dropped % 2, 0)
        roles = [m["role"] for m in new["messages"]]
        for i, role in enumerate(roles):
            if role == "tool":
                self.assertIn(roles[i - 1], ("assistant", "tool"))

    def test_tail_never_starts_on_a_tool_result(self):
        body = {"messages": [msg("system", 10), msg("user", 10)] + [msg("assistant", 4000)] * 5
                + [msg("assistant", 10, tool_calls=[{}])] + [msg("tool", 10)] * 6}
        new, _ = relay_trim.trim(body, 4096)
        first_kept = new["messages"][3]
        self.assertNotEqual(first_kept["role"], "tool")

    def test_no_messages_is_left_alone(self):
        self.assertEqual(relay_trim.trim({"prompt": "x" * 90000}, 8192), ({"prompt": "x" * 90000}, 0))

    def test_patch_show_caps_context_length(self):
        reply = {"model_info": {"qwen2.context_length": 32768, "qwen2.embedding_length": 5120}}
        got = relay_trim.patch_show(reply, 8192)["model_info"]
        self.assertEqual(got, {"qwen2.context_length": 8192, "qwen2.embedding_length": 5120})
        self.assertEqual(relay_trim.patch_show({"x": 1}, 8192), {"x": 1})


class FakeOllama(BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.seen.append((self.path, body))
        if self.path == "/api/show":
            payload = json.dumps({"model_info": {"llama.context_length": 131072}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        for part in ({"message": {"content": "he"}}, {"message": {"tool_calls": [{"function": {"name": "read"}}]}},
                     {"done": True}):
            self.wfile.write((json.dumps(part) + "\n").encode())
            self.wfile.flush()


class RoundTrip(unittest.TestCase):
    def setUp(self):
        FakeOllama.seen = []
        self.ollama = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=self.ollama.serve_forever, daemon=True).start()
        self.addCleanup(self.ollama.server_close)
        self.addCleanup(self.ollama.shutdown)
        self.logs = []
        self.relay = relay_server.serve(0, f"http://127.0.0.1:{self.ollama.server_port}", 8192,
                                        trim=relay_trim.trim, patch_show=relay_trim.patch_show,
                                        chat_paths=relay_trim.CHAT_PATHS, log=self.logs.append)
        self.addCleanup(self.relay.server_close)
        self.addCleanup(self.relay.shutdown)
        self.base = f"http://127.0.0.1:{self.relay.server_port}"

    def post(self, path, body):
        with http.open_url(self.base + path, timeout=10, method="POST", data=json.dumps(body).encode(),
                           headers={"Content-Type": "application/json"}) as resp:
            return resp.status, resp.read().decode()

    def test_binds_loopback_only(self):
        self.assertEqual(self.relay.server_address[0], "127.0.0.1")

    def test_big_chat_is_trimmed_and_the_stream_passes_through(self):
        status, text = self.post("/api/chat", chat(*[msg("assistant", 4000) for _ in range(10)]))
        self.assertEqual(status, 200)
        lines = [json.loads(x) for x in text.splitlines()]
        self.assertEqual(lines[1]["message"]["tool_calls"][0]["function"]["name"], "read")
        self.assertTrue(lines[-1]["done"])
        sent = FakeOllama.seen[-1][1]
        self.assertLessEqual(relay_trim.tokens(sent), 8192 - relay_trim.RESERVE)
        self.assertTrue(any("trimmed" in line for line in self.logs))

    def test_small_chat_reaches_ollama_byte_for_byte(self):
        body = chat(msg("assistant", 40))
        self.post("/api/chat", body)
        self.assertEqual(FakeOllama.seen[-1][1], body)

    def test_show_reports_the_real_window(self):
        status, text = self.post("/api/show", {"model": "m"})
        self.assertEqual((status, json.loads(text)["model_info"]["llama.context_length"]), (200, 8192))


class Cli(unittest.TestCase):
    def test_tiny_window_is_refused(self):
        lines = []
        self.assertEqual(relay.main(["--window", "512"], out=lines.append), 2)

    def test_starts_says_nothing_changed_and_stops(self):
        lines = []
        self.assertEqual(relay.main(["--port", "0", "--upstream", "http://127.0.0.1:9"], out=lines.append,
                                    wait=lambda: None), 0)
        self.assertIn("Nothing was changed", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
