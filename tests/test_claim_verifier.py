"""Local claim verifier: prompts, cache key, search hits, and the verify_claims tool."""
import json
import os
import tempfile
import types
import unittest
from unittest import mock

from agl.app.agent import _shell_config
from agl.app.ports import AppPorts
from agl.app.verifier import UNAVAILABLE, bind_verify_claims
from agl.core.claim_cache import make_key, ttl_for
from agl.core.verification_prompts import (
    CONFIDENCE_RULE,
    MAIN_SYSTEM_PROMPT,
    VERIFIER_SYSTEM_PROMPT,
)
from agl.platform.claim_store import ClaimStore
from agl.platform.ollama import verifier_model
from agl.platform.web_search import search

RULE = "\n".join([
    'High (conf "high"): 3+ primary sources agree. Use "confirms", "establishes".',
    'Moderate (conf "mod"): 2 agreeing sources, or 1 primary source. Use "indicates", "suggests".',
    'Low (conf "low"): 1 secondary source, or sources conflict. Say "sources conflict" or "preliminary".',
    "Tag every cited claim, High included: [High 3/3], [Moderate 1/1], [Low 1/2].",
])
PAGE = "<html><body>PAGEBODY-9f3c</body></html>"


class _Search:
    def __init__(self, backend="searxng", hits=None):
        self.backend = backend
        self.hits = hits if hits is not None else [{"url": "https://example.com/a", "snippet": "yes"}]
        self.queries = []

    def search(self, query, *, http, env):
        self.queries.append(query)
        return {"backend": self.backend, "hits": list(self.hits)}


class _Ports:
    def __init__(self, store, searcher=None, reply=None):
        self.claim_store = store
        self.web_search = searcher
        self.http = object()
        self.env = {}
        self.complete_calls = []
        self._reply = reply

    def complete(self, system, user):
        self.complete_calls.append((system, user))
        if self._reply is not None:
            return self._reply(system, user)
        data = json.loads(user)
        rows = [_verified(claim) for claim in data["claims"]]
        return json.dumps({"results": rows})


def _verified(claim):
    return {
        "claim": claim,
        "status": "verified",
        "conf": "high",
        "extract": "ok",
        "sources": [{"url": "https://example.com/a", "type": "primary"}],
    }


class ConfidenceRule(unittest.TestCase):
    def test_rule_is_the_four_lines_and_both_prompts_keep_it(self):
        self.assertEqual(CONFIDENCE_RULE, RULE)
        self.assertEqual(len(CONFIDENCE_RULE.split("\n")), 4)
        self.assertIn(CONFIDENCE_RULE, MAIN_SYSTEM_PROMPT)
        self.assertIn(CONFIDENCE_RULE, VERIFIER_SYSTEM_PROMPT)
        self.assertNotIn("1+ primary source", MAIN_SYSTEM_PROMPT)
        self.assertNotIn("1+ primary source", VERIFIER_SYSTEM_PROMPT)
        self.assertNotIn("Exception-Only", MAIN_SYSTEM_PROMPT)
        self.assertIn("1 authoritative primary source", MAIN_SYSTEM_PROMPT)
        self.assertIn("Compact Inline Links", MAIN_SYSTEM_PROMPT)
        self.assertIn("Label Original Work", MAIN_SYSTEM_PROMPT)
        self.assertIn("1 primary source", VERIFIER_SYSTEM_PROMPT)


class CacheKey(unittest.TestCase):
    def test_claim_case_spaces_and_one_trailing_dot_match(self):
        self.assertEqual(make_key("Hello."), make_key("  hello  "))
        self.assertEqual(make_key("Hello   World."), make_key("hello world"))

    def test_context_spaces_collapse_but_case_and_wording_do_not(self):
        self.assertEqual(make_key("c", "Foo   Bar"), make_key("c", "Foo Bar"))
        self.assertNotEqual(make_key("c", "left"), make_key("c", "right"))
        self.assertNotEqual(make_key("c", "Foo"), make_key("c", "foo"))

    def test_ttl_for_verified_is_a_day_and_the_rest_are_five_minutes(self):
        self.assertEqual(ttl_for("verified"), 86400)
        self.assertEqual(ttl_for("conflict"), 300)
        self.assertEqual(ttl_for("unavailable"), 300)
        self.assertEqual(ttl_for("none"), 300)


class WebSearchHits(unittest.TestCase):
    def test_html_page_body_is_not_copied_onto_a_hit(self):
        seen = {}

        def get_json(url, *, timeout, headers=None, data=None, opener=None):
            seen["url"] = url
            seen["timeout"] = timeout
            return {"results": [{
                "url": "https://docs.example.com/a",
                "content": "A short snippet.",
                "html": PAGE,
                "raw_content": PAGE,
            }]}

        out = search("json", http=types.SimpleNamespace(get_json=get_json),
                     env={"AGL_SEARXNG_URL": "http://localhost:8888/"})
        self.assertEqual(out["backend"], "searxng")
        self.assertEqual(seen["timeout"], 10)
        self.assertIn("/search?", seen["url"])
        self.assertIn("format=json", seen["url"])
        self.assertEqual(set(out["hits"][0]), {"url", "snippet"})
        self.assertNotIn("PAGEBODY-9f3c", json.dumps(out["hits"]))
        self.assertEqual(out["hits"][0]["snippet"], "A short snippet.")

    def test_non_list_or_error_falls_through_to_tavily_then_none(self):
        calls = []

        def get_json(url, *, timeout, headers=None, data=None, opener=None):
            calls.append((url, headers, data))
            if "tavily" not in url:
                raise OSError("down")
            return {"results": [{
                "url": "https://docs.tavily.com/a",
                "content": "1000 credits",
                "html": PAGE,
            }]}

        http = types.SimpleNamespace(get_json=get_json)
        env = {"AGL_SEARXNG_URL": "http://localhost:8888", "TAVILY_API_KEY": "test-key"}
        out = search("credits", http=http, env=env)
        self.assertEqual(out["backend"], "tavily")
        self.assertEqual(set(out["hits"][0]), {"url", "snippet"})
        self.assertNotIn("PAGEBODY-9f3c", json.dumps(out))
        body = json.loads(calls[1][2].decode("utf-8"))
        self.assertEqual(body["api_key"], "test-key")
        self.assertEqual(body["query"], "credits")
        self.assertEqual(body["search_depth"], "basic")
        self.assertEqual(body["max_results"], 5)
        self.assertEqual(calls[1][1]["Content-Type"], "application/json")
        called = []

        def refuse(*args, **kwargs):
            called.append(1)
            raise OSError("no")

        quiet = types.SimpleNamespace(get_json=refuse)
        self.assertEqual(search("q", http=quiet, env={}), {"backend": "none", "hits": []})
        self.assertEqual(called, [])


class VerifyClaims(unittest.TestCase):
    def test_output_is_minified_json_and_round_trips(self):
        store = ClaimStore(":memory:")
        text = bind_verify_claims(_Ports(store, _Search()))(["rain is wet"])
        parsed = json.loads(text)
        self.assertEqual(text, json.dumps(parsed, separators=(",", ":")))
        self.assertEqual(parsed, json.loads(json.dumps(parsed)))
        self.assertEqual(parsed["results"][0]["claim"], "rain is wet")

    def test_cached_claim_keeps_its_place_in_the_input_order(self):
        store = ClaimStore(":memory:")
        store.set_many([{"claim": "a", "status": "verified", "conf": "high", "extract": "cached", "sources": []}])
        searcher = _Search()
        ports = _Ports(store, searcher)
        rows = json.loads(bind_verify_claims(ports)(["b", "a", "c"]))["results"]
        self.assertEqual([row["claim"] for row in rows], ["b", "a", "c"])
        self.assertEqual(rows[1]["extract"], "cached")
        self.assertEqual(searcher.queries, ["b", "c"])

    def test_second_call_does_not_complete_again(self):
        store = ClaimStore(":memory:")
        searcher = _Search()
        ports = _Ports(store, searcher)
        tool = bind_verify_claims(ports)
        self.assertEqual(tool.__name__, "verify_claims")
        tool(["same claim"])
        tool(["same claim"])
        self.assertEqual(len(ports.complete_calls), 1)
        self.assertEqual(searcher.queries, ["same claim"])

    def test_no_backend_marks_every_claim_unavailable_without_complete(self):
        for searcher in (None, _Search(backend="none", hits=[])):
            store = ClaimStore(":memory:")
            ports = _Ports(store, searcher)
            rows = json.loads(bind_verify_claims(ports)(["one", "two"]))["results"]
            self.assertEqual(ports.complete_calls, [])
            self.assertEqual([row["status"] for row in rows], ["unavailable", "unavailable"])
            self.assertEqual([row["extract"] for row in rows], [UNAVAILABLE, UNAVAILABLE])
            self.assertEqual(UNAVAILABLE, "Data not available.")

    def test_invalid_model_json_is_stored_for_the_short_ttl(self):
        store = ClaimStore(":memory:")
        clock = {"t": 1_000_000.0}
        ports = _Ports(store, _Search(), reply=lambda system, user: "not-json")
        with mock.patch("agl.platform.claim_store.time.time", lambda: clock["t"]):
            rows = json.loads(bind_verify_claims(ports)(["plasma"]))["results"]
            self.assertEqual(rows[0]["status"], "unavailable")
            self.assertEqual(rows[0]["extract"], "Data not available.")
            clock["t"] = 1_000_000.0 + 299
            found, miss = store.get_many(["plasma"])
            self.assertEqual(miss, [])
            self.assertEqual(found["plasma"]["status"], "unavailable")
            clock["t"] = 1_000_000.0 + 301
            found, miss = store.get_many(["plasma"])
            self.assertEqual(found, {})
            self.assertEqual(miss, ["plasma"])

    def test_a_payload_without_a_results_list_is_also_unavailable(self):
        store = ClaimStore(":memory:")
        ports = _Ports(store, _Search(), reply=lambda system, user: '{"results": {}}')
        rows = json.loads(bind_verify_claims(ports)(["q"]))["results"]
        self.assertEqual(rows[0]["extract"], "Data not available.")
        found, miss = store.get_many(["q"])
        self.assertEqual(miss, [])
        self.assertEqual(found["q"]["status"], "unavailable")

    def test_a_miss_the_model_omits_is_unavailable(self):
        store = ClaimStore(":memory:")

        def reply(system, user):
            return json.dumps({"results": [_verified("b")]})

        ports = _Ports(store, _Search(), reply=reply)
        rows = json.loads(bind_verify_claims(ports)(["b", "c"]))["results"]
        self.assertEqual(rows[0]["status"], "verified")
        self.assertEqual(rows[1]["extract"], "Data not available.")

    def test_at_most_three_searches_then_one_complete(self):
        store = ClaimStore(":memory:")
        searcher = _Search()
        ports = _Ports(store, searcher)
        bind_verify_claims(ports)(["a", "b", "c", "d"])
        self.assertEqual(searcher.queries, ["a", "b", "c"])
        self.assertEqual(len(ports.complete_calls), 1)
        self.assertEqual(ports.complete_calls[0][0], VERIFIER_SYSTEM_PROMPT)
        user = json.loads(ports.complete_calls[0][1])
        self.assertEqual(user["claims"], ["a", "b", "c", "d"])
        for packet in user["sources"]:
            for hit in packet["hits"]:
                self.assertEqual(set(hit), {"url", "snippet"})

    def test_build_ports_does_not_open_the_claim_cache(self):
        import run
        previous = run.PROJECT_DIR
        folder_path = None
        try:
            with tempfile.TemporaryDirectory() as folder:
                folder_path = folder
                run.PROJECT_DIR = folder
                ports = run.build_ports()
                self.assertIsNone(ports.claim_store)
                self.assertFalse(os.path.exists(os.path.join(folder, ".claim_cache.sqlite")))
            self.assertFalse(os.path.exists(folder_path))
        finally:
            run.PROJECT_DIR = previous

    def test_file_cache_closes_before_verify_claims_returns(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, ".claim_cache.sqlite")
            ports = _Ports(None, _Search())
            ports.open_claim_store = lambda: ClaimStore(path)
            text = bind_verify_claims(ports)(["rain is wet"])
            self.assertEqual(json.loads(text)["results"][0]["claim"], "rain is wet")
            self.assertTrue(os.path.exists(path))
            self.assertIsNone(ports.claim_store)

    def test_each_call_with_no_store_opens_again(self):
        opened = {"n": 0}

        def opener():
            opened["n"] += 1
            return ClaimStore(":memory:")

        ports = _Ports(None, _Search())
        ports.open_claim_store = opener
        tool = bind_verify_claims(ports)
        tool(["one"])
        tool(["two"])
        self.assertEqual(opened["n"], 2)
        self.assertIsNone(ports.claim_store)

    def test_no_store_and_no_opener_skips_complete(self):
        ports = _Ports(None, _Search())
        rows = json.loads(bind_verify_claims(ports)(["one", "two"]))["results"]
        self.assertEqual(ports.complete_calls, [])
        self.assertEqual([row["status"] for row in rows], ["unavailable", "unavailable"])

    def test_file_cache_closes_when_complete_raises(self):
        def boom(system, user):
            raise RuntimeError("complete failed")

        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, ".claim_cache.sqlite")
            ports = _Ports(None, _Search(), reply=boom)
            ports.open_claim_store = lambda: ClaimStore(path)
            with self.assertRaises(RuntimeError):
                bind_verify_claims(ports)(["rain is wet"])
            self.assertTrue(os.path.exists(path))
            self.assertIsNone(ports.claim_store)


class ModelAndWiring(unittest.TestCase):
    def test_blank_verifier_model_skips_the_installed_list(self):
        def boom(*args, **kwargs):
            raise AssertionError("should not look up models")

        model, note = verifier_model({"LOCAL_LLM_MODEL": "qwen2.5:14b"}, get_json=boom)
        self.assertEqual((model, note), ("qwen2.5:14b", ""))

    def test_missing_verifier_model_falls_back_without_a_pull(self):
        def get_json(url, *, timeout, headers=None, data=None, opener=None):
            return {"models": [{"name": "qwen2.5:14b"}]}

        model, note = verifier_model(
            {"LOCAL_VERIFIER_MODEL": "missing:1b", "LOCAL_LLM_MODEL": "qwen2.5:14b"},
            base_url="http://localhost:11434",
            get_json=get_json,
        )
        self.assertEqual(model, "qwen2.5:14b")
        self.assertIn("not installed", note)
        self.assertIn("qwen2.5:14b", note)

    def test_installed_verifier_model_keeps_its_name(self):
        def get_json(url, *, timeout, headers=None, data=None, opener=None):
            return {"models": [{"name": "small:1b"}]}

        model, note = verifier_model(
            {"LOCAL_VERIFIER_MODEL": "Small:1b", "LOCAL_LLM_MODEL": "qwen2.5:14b"},
            base_url="http://localhost:11434",
            get_json=get_json,
        )
        self.assertEqual((model, note), ("Small:1b", ""))

    def test_tools_only_when_capabilities_is_none(self):
        class Policy:
            @staticmethod
            def allow_all():
                return "allow"

        bare = _shell_config("m", "http://localhost:11434/v1", "ws", Policy(), None, object())
        self.assertEqual(bare["system_instructions"], MAIN_SYSTEM_PROMPT)
        self.assertEqual([tool.__name__ for tool in bare["tools"]], ["verify_claims"])
        held = _shell_config("gemma2", "http://localhost:11434/v1", "ws", Policy(), object(), object())
        self.assertEqual(held["system_instructions"], MAIN_SYSTEM_PROMPT)
        self.assertNotIn("tools", held)

    def test_complete_posts_to_the_local_chat_url_and_forwards_the_note(self):
        seen = {}

        class Config:
            def llm_base_url(self):
                return "http://localhost:11434/v1"

            def ollama_api_base(self, env):
                return "http://127.0.0.1:11434"

        class Ollama:
            def verifier_model(self, env, *, base_url=None, get_json=None):
                seen["base"] = base_url
                return "qwen2.5:14b", "The verifier model x is not installed. qwen2.5:14b is used."

            def chat_json(self, url, body, **kwargs):
                seen["url"] = url
                seen["body"] = body
                return {"choices": [{"message": {"content": "{\"ok\":true}"}}]}

            def pull(self, tag):
                raise AssertionError("pull")

        notes = []
        ports = types.SimpleNamespace(
            config=Config(),
            ollama=Ollama(),
            os=types.SimpleNamespace(environ={"LOCAL_LLM_MODEL": "qwen2.5:14b"}),
            _out=notes.append,
        )
        text = AppPorts.complete(ports, "system text", "user text")
        self.assertEqual(text, '{"ok":true}')
        self.assertEqual(seen["url"], "http://localhost:11434/v1/chat/completions")
        self.assertEqual(seen["base"], "http://127.0.0.1:11434")
        self.assertEqual(seen["body"]["model"], "qwen2.5:14b")
        self.assertIs(seen["body"]["stream"], False)
        self.assertEqual(seen["body"]["messages"][0]["content"], "system text")
        self.assertEqual(notes, ["The verifier model x is not installed. qwen2.5:14b is used."])


if __name__ == "__main__":
    unittest.main()
