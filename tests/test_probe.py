"""The live tool probe, against a pretend OpenAI-compatible server. No Ollama, no network, no real clock."""
import contextlib
import io
import json
import os
import re
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import probe  # noqa: E402

BASE = "http://localhost:11434"
HEX = re.compile(r"^[0-9a-f]{32}$")


def call(name, args, cid="c1", as_dict=False):
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": args if as_dict else json.dumps(args)}}


def msg(*calls, content=""):
    return {"role": "assistant", "content": content, "tool_calls": list(calls)}


def say(text):
    return {"role": "assistant", "content": text}


class FakeServer:
    """A scripted chat server. script(step, requests) returns the assistant message (or raises) for each request.
    Every request advances the fake clock by `tick` seconds."""

    def __init__(self, script, tokens=(30, 30, 0), tick=5.0):
        self.script, self.tokens, self.tick = script, list(tokens), tick
        self.requests, self.t = [], [0.0]

    def clock(self):
        return self.t[0]

    def __call__(self, request, timeout=None):
        body = json.loads(request.data)
        self.requests.append((request.full_url, request.get_method(), body, timeout))
        step = len(self.requests) - 1
        self.t[0] += self.tick
        out = self.script(step, self.requests)
        if isinstance(out, BaseException):
            raise out
        used = self.tokens[step] if step < len(self.tokens) else 0
        payload = {"choices": [{"message": out}], "usage": {"completion_tokens": used}}
        if out is None:
            payload = {"unexpected": True}
        return _Reply(payload)


class _Reply:
    def __init__(self, payload):
        self.body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def marker_from(requests):
    """What a real model would do: read the marker out of the tool result it was handed."""
    for _, _, body, _ in reversed(requests):
        for m in body["messages"]:
            if m.get("role") == "tool" and m["content"].startswith("MARKER="):
                return m["content"][len("MARKER="):]
    return None


def good(write=lambda marker: marker, path="output.md"):
    def script(step, requests):
        if step == 0:
            return msg(call("read_file", {"path": "seed.md"}))
        if step == 1:
            return msg(call("write_file", {"path": path, "content": write(marker_from(requests))}, cid="c2"))
        return say("done")
    return script


class Probe(unittest.TestCase):
    def run_probe(self, script, **kw):
        server = FakeServer(script, **{k: kw.pop(k) for k in ("tokens", "tick") if k in kw})
        folders = []
        real = probe.tempfile.mkdtemp

        def spy(*a, **k):
            folders.append(real(*a, **k))
            return folders[-1]
        out = io.StringIO()
        with mock.patch.object(probe.tempfile, "mkdtemp", spy), contextlib.redirect_stdout(out):
            result = probe.run_probe(BASE, "qwen3:8b", opener=server, clock=server.clock, **kw)
        self.server, self.folders, self.printed = server, folders, out.getvalue()
        return result

    def assertNoLeak(self, result):
        marker = marker_from(self.server.requests)
        if marker:
            self.assertNotIn(marker, json.dumps(result))
            self.assertNotIn(marker, self.printed)
            first_prompt = json.dumps(self.server.requests[0][2])
            self.assertNotIn(marker, first_prompt)

    # --- pass ---------------------------------------------------------------------------------------------
    def test_a_model_that_reads_and_writes_the_marker_through_tools_passes(self):
        result = self.run_probe(good())
        self.assertEqual((result["verdict"], result["calls"]), ("pass", 2))
        self.assertNoLeak(result)

    def test_the_request_is_a_non_streaming_chat_with_both_tools_to_the_v1_endpoint(self):
        self.run_probe(good())
        url, method, body, _ = self.server.requests[0]
        self.assertEqual((url, method), (BASE + "/v1/chat/completions", "POST"))
        self.assertEqual((body["model"], body["stream"]), ("qwen3:8b", False))
        self.assertEqual([t["function"]["name"] for t in body["tools"]], ["read_file", "write_file"])

    def test_a_base_url_that_already_ends_in_v1_is_not_doubled(self):
        server = FakeServer(good())
        probe.run_probe(BASE + "/v1/", "m", opener=server, clock=server.clock)
        self.assertEqual(server.requests[0][0], BASE + "/v1/chat/completions")

    def test_seed_md_holds_exactly_marker_equals_128_bits_of_hex_and_no_newline(self):
        seen = []

        def script(step, requests):
            if step == 0:
                return msg(call("read_file", {"path": "seed.md"}))
            seen.append([m for m in requests[-1][2]["messages"] if m["role"] == "tool"][0]["content"])
            return say("stop")
        self.run_probe(script)
        self.assertRegex(seen[0], r"^MARKER=[0-9a-f]{32}$")

    def test_each_run_gets_a_new_marker(self):
        a, b = [], []
        for store in (a, b):
            self.run_probe(good())
            store.append(marker_from(self.server.requests))
        self.assertNotEqual(a, b)
        self.assertRegex(a[0], HEX)

    def test_a_single_trailing_newline_in_output_md_is_tolerated(self):
        self.assertEqual(self.run_probe(good(write=lambda m: m + "\n"))["verdict"], "pass")

    def test_arguments_given_as_an_object_instead_of_a_string_are_accepted(self):
        def script(step, requests):
            if step == 0:
                return msg(call("read_file", {"path": "seed.md"}, as_dict=True))
            if step == 1:
                return msg(call("write_file", {"path": "output.md", "content": marker_from(requests)}, as_dict=True))
            return say("done")
        self.assertEqual(self.run_probe(script)["verdict"], "pass")

    # --- fail reasons, in the spec's order ---------------------------------------------------------------
    def test_a_server_that_errors_fails_with_the_server_reason(self):
        for exc in (urllib.error.URLError("down"), OSError("reset"),
                    urllib.error.HTTPError(BASE, 500, "boom", {}, io.BytesIO(b""))):
            with self.subTest(exc=type(exc).__name__):
                result = self.run_probe(lambda step, req, e=exc: e)
                self.assertEqual(result["verdict"], "fail")
                self.assertIn("the server did not answer properly", result["reason"])

    def test_a_reply_with_the_wrong_shape_counts_as_a_server_problem(self):
        result = self.run_probe(lambda step, req: None)
        self.assertIn("the server did not answer properly", result["reason"])

    def test_a_server_error_after_some_tool_calls_still_reports_the_server(self):
        def script(step, requests):
            return msg(call("read_file", {"path": "seed.md"})) if step == 0 else OSError("gone")
        self.assertIn("the server did not answer properly", self.run_probe(script)["reason"])

    def test_a_path_outside_the_folder_fails_before_anything_else_and_is_never_run(self):
        escaped = os.path.join(os.path.dirname(os.path.abspath(__file__)), "escaped_by_probe_test.txt")
        for path in ("../escaped.txt", "..\\escaped.txt", "/etc/passwd", "C:\\Windows\\win.ini", escaped, "sub/../../x", "",
                     "..\\x", "a\\..\\..\\x", "C:\\x", "c:x", "\\x", "seed.md\x00.txt"):
            with self.subTest(path=path):
                result = self.run_probe(lambda step, req, p=path: msg(call("write_file", {"path": p, "content": "x"})))
                self.assertEqual(result["verdict"], "fail")
                self.assertIn("outside the working folder", result["reason"])
        self.assertFalse(os.path.exists(escaped))

    def test_no_structured_tool_call_fails_even_if_the_text_looks_like_one(self):
        text = '{"name": "read_file", "arguments": {"path": "seed.md"}}'
        result = self.run_probe(lambda step, req: say(text))
        self.assertEqual(result["verdict"], "fail")
        self.assertIn("no structured tool call", result["reason"])
        self.assertIn("plain text", result["reason"])

    def test_an_answer_with_no_tool_call_at_all_fails_without_the_plain_text_note(self):
        result = self.run_probe(lambda step, req: say("I cannot do that."))
        self.assertIn("no structured tool call", result["reason"])
        self.assertNotIn("plain text", result["reason"])

    def test_more_than_eight_tool_calls_is_a_loop(self):
        result = self.run_probe(lambda step, req: msg(call("read_file", {"path": "seed.md"}, cid=f"c{step}")))
        self.assertEqual(result["verdict"], "fail")
        self.assertIn("tool-call loop", result["reason"])
        self.assertEqual(result["calls"], 9)

    def test_the_loop_limit_is_adjustable_and_exactly_the_limit_is_not_a_loop(self):
        def script(step, requests):
            if step < 2:
                return msg(call("read_file", {"path": "seed.md"}, cid=f"c{step}"))
            if step == 2:
                return msg(call("write_file", {"path": "output.md", "content": marker_from(requests)}, cid="w"))
            return say("done")
        self.assertEqual(self.run_probe(script, max_calls=3)["verdict"], "pass")
        self.assertIn("tool-call loop", self.run_probe(script, max_calls=2)["reason"])

    def test_output_md_missing_fails(self):
        def script(step, requests):
            return msg(call("read_file", {"path": "seed.md"})) if step == 0 else say("done")
        self.assertIn("output.md was not written", self.run_probe(script)["reason"])

    def test_output_md_empty_fails(self):
        self.assertIn("output.md is empty", self.run_probe(good(write=lambda m: ""))["reason"])

    def test_output_md_with_the_wrong_content_fails(self):
        for wrong in (lambda m: "MARKER=" + m, lambda m: m[:-1] + "0" if m[-1] != "0" else m[:-1] + "1",
                      lambda m: " " + m, lambda m: m + "\n\n", lambda m: "the marker"):
            with self.subTest():
                result = self.run_probe(good(write=wrong))
                self.assertEqual(result["verdict"], "fail")
                self.assertIn("does not hold the marker", result["reason"])
                self.assertNoLeak(result)

    def test_writing_to_a_different_file_is_not_output_md(self):
        self.assertIn("output.md was not written", self.run_probe(good(path="out.md"))["reason"])

    def test_a_tool_call_with_unreadable_arguments_does_not_crash_the_probe(self):
        bad = {"id": "c1", "function": {"name": "read_file", "arguments": "{not json"}}
        result = self.run_probe(lambda step, req: msg(bad) if step == 0 else say("done"))
        self.assertEqual(result["verdict"], "fail")  # no output.md, but it ran to the end

    def test_an_unknown_tool_name_is_answered_with_an_error_not_run(self):
        result = self.run_probe(lambda step, req: msg(call("rm_rf", {"path": "/"})) if step == 0 else say("done"))
        self.assertEqual(result["verdict"], "fail")
        self.assertIn("unknown tool", json.dumps(self.server.requests[1][2]["messages"]))

    def test_running_out_of_time_fails_with_a_timeout(self):
        result = self.run_probe(good(), tick=100.0, timeout=120)
        self.assertEqual(result["verdict"], "fail")
        self.assertIn("timed out after 120 s", result["reason"])

    # --- speed, cleanup, leaks ----------------------------------------------------------------------------
    def test_tokens_per_second_is_completion_tokens_over_elapsed_rounded_to_a_tenth(self):
        result = self.run_probe(good(), tokens=(30, 30, 0), tick=5.0)  # 60 tokens over 15 s
        self.assertEqual(result["tok_s"], 4.0)
        result = self.run_probe(good(), tokens=(33, 34, 0), tick=3.0)  # 67 tokens over 9 s
        self.assertEqual(result["tok_s"], 7.4)

    def test_no_token_counts_means_no_speed(self):
        self.assertIsNone(self.run_probe(good(), tokens=(0, 0, 0))["tok_s"])

    def test_the_temp_folder_is_removed_after_a_pass_a_fail_and_a_server_error(self):
        for script in (good(), good(write=lambda m: "no"), lambda step, req: OSError("down")):
            self.run_probe(script)
            self.assertEqual(len(self.folders), 1)
            self.assertFalse(os.path.exists(self.folders[0]))

    def test_no_reason_ever_contains_the_marker_even_if_the_model_echoes_it(self):
        def script(step, requests):
            if step == 0:
                return msg(call("read_file", {"path": "seed.md"}))
            return msg(call("write_file", {"path": "../" + marker_from(requests), "content": "x"}))
        result = self.run_probe(script)
        self.assertIn("outside the working folder", result["reason"])
        self.assertNoLeak(result)

    def test_the_result_builder_scrubs_the_marker_from_any_reason_it_is_handed(self):
        marker = "ab" * 16
        got = probe._result("fail", f"saw {marker} in a path", marker, 0, 0, lambda: 1, 0)
        self.assertNotIn(marker, got["reason"])
        self.assertIn("<marker>", got["reason"])

    def test_a_reason_is_capped(self):
        self.assertLessEqual(len(probe._result("fail", "x" * 900, "m", 0, 0, lambda: 1, 0)["reason"]), probe.REASON_CAP)


class AppProbe(unittest.TestCase):
    def test_check_or_update_memory_raising_calls_out(self):
        class RaisingPorts:
            def index_memory(self):
                raise RuntimeError("database locked")

        out = mock.Mock()
        import agl.app.probe
        agl.app.probe.check_or_update_memory(ports=RaisingPorts(), out=out)
        out.assert_called_with("Memory index skipped: database locked")


if __name__ == "__main__":
    unittest.main()
