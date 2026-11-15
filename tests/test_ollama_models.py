"""Installed-model details from /api/tags and /api/show, with a pretend server (no real Ollama needed)."""
import json
import os
import sys
import unittest
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ollama_models as om  # noqa: E402

BASE = "http://localhost:11434"


class _Reply:
    def __init__(self, data):
        self.body = json.dumps(data).encode("utf-8")

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOllama:
    """Routes by URL. `show` maps a model to its /api/show reply (or an exception). Records every request."""

    def __init__(self, tags, show=None):
        self.tags, self.show, self.seen = tags, show or {}, []

    def __call__(self, request, timeout=None):
        url = request.full_url
        body = json.loads(request.data) if request.data else None
        self.seen.append((request.get_method(), url.replace(BASE, ""), body))
        if url.endswith("/api/tags"):
            if isinstance(self.tags, BaseException):
                raise self.tags
            return _Reply(self.tags)
        if url.endswith("/api/show"):
            item = self.show.get(body["model"], urllib.error.URLError("no such model"))
            if isinstance(item, BaseException):
                raise item
            return _Reply(item)
        raise urllib.error.URLError("unexpected " + url)


def row(name, size=9_000_000_000, caps=None, modified="2026-11-01T10:00:00Z"):
    r = {"name": name, "size": size, "modified_at": modified}
    if caps is not None:
        r["capabilities"] = caps
    return r


class InstalledDetails(unittest.TestCase):
    def test_capabilities_in_tags_mean_no_show_calls(self):
        fake = FakeOllama({"models": [row("qwen3:8b", caps=["completion", "tools"])]})
        got = om.installed_details(BASE, opener=fake)
        self.assertEqual(got["qwen3:8b"]["caps"], ["completion", "tools"])
        self.assertEqual([m for m, u, b in fake.seen], ["GET"])

    def test_missing_capabilities_are_asked_for_once_per_model_with_the_model_key(self):
        fake = FakeOllama({"models": [row("old:1b"), row("older:2b")]},
                          show={"old:1b": {"capabilities": ["completion"]}, "older:2b": {"capabilities": ["embedding"]}})
        got = om.installed_details(BASE, opener=fake)
        self.assertEqual((got["old:1b"]["caps"], got["older:2b"]["caps"]), (["completion"], ["embedding"]))
        self.assertEqual([(m, u, b) for m, u, b in fake.seen[1:]],
                         [("POST", "/api/show", {"model": "old:1b"}), ("POST", "/api/show", {"model": "older:2b"})])

    def test_an_old_server_with_no_capabilities_field_is_unknown_not_empty(self):
        fake = FakeOllama({"models": [row("old:1b")]}, show={"old:1b": {"details": {}, "template": "x"}})
        self.assertIsNone(om.installed_details(BASE, opener=fake)["old:1b"]["caps"])

    def test_a_failing_show_call_is_unknown_and_does_not_stop_the_rest(self):
        fake = FakeOllama({"models": [row("a:1"), row("b:2")]}, show={"a:1": OSError("boom"), "b:2": {"capabilities": ["tools"]}})
        got = om.installed_details(BASE, opener=fake)
        self.assertEqual((got["a:1"]["caps"], got["b:2"]["caps"]), (None, ["tools"]))

    def test_show_calls_are_capped(self):
        fake = FakeOllama({"models": [row(f"m{i}:1b") for i in range(45)]})
        got = om.installed_details(BASE, opener=fake)
        self.assertEqual(len(got), 45)
        self.assertEqual(sum(1 for m, u, b in fake.seen if u == "/api/show"), om.MAX_SHOW_CALLS)

    def test_size_and_age_come_through_and_odd_values_do_not_crash(self):
        fake = FakeOllama({"models": [row("a:1", size=15_200_000_000, caps=[]), row("b:2", size="big", caps=[], modified=7),
                                      row("c:3", size=True, caps=[]), row("d:4", size=0, caps=[])]})
        got = om.installed_details(BASE, opener=fake)
        self.assertEqual((got["a:1"]["size_gb"], got["a:1"]["modified_at"]), (15.2, "2026-11-01T10:00:00Z"))
        self.assertEqual([got[k]["size_gb"] for k in ("b:2", "c:3", "d:4")], [None, None, None])
        self.assertIsNone(got["b:2"]["modified_at"])

    def test_capabilities_with_junk_values_keep_only_strings(self):
        fake = FakeOllama({"models": [row("a:1", caps=["tools", 3, None, "vision"])]})
        self.assertEqual(om.installed_details(BASE, opener=fake)["a:1"]["caps"], ["tools", "vision"])

    def test_a_server_that_does_not_answer_gives_nothing(self):
        self.assertEqual(om.installed_details(BASE, opener=FakeOllama(urllib.error.URLError("down"))), {})

    def test_junk_replies_give_nothing_and_junk_rows_are_skipped(self):
        self.assertEqual(om.installed_details(BASE, opener=FakeOllama(["not", "a", "dict"])), {})
        self.assertEqual(om.installed_details(BASE, opener=FakeOllama({"models": "nope"})), {})
        got = om.installed_details(BASE, opener=FakeOllama({"models": [None, 5, {"size": 1}, {"name": ""}, row("ok:1", caps=[])]}))
        self.assertEqual(list(got), ["ok:1"])

    def test_names_are_normalised_so_an_implicit_latest_matches(self):
        fake = FakeOllama({"models": [row("Qwen3", caps=["completion"])]})
        got = om.installed_details(BASE, opener=fake)
        self.assertEqual(list(got), ["qwen3:latest"])
        self.assertEqual(om.lookup(got, "qwen3")["name"], "Qwen3")

    def test_lookup_finds_the_short_alias_run_py_lists_for_hf_models(self):
        fake = FakeOllama({"models": [row("hf.co/u/m:q4_k_m", caps=["completion", "tools"])]})
        got = om.installed_details(BASE, opener=fake)
        self.assertEqual(om.lookup(got, "m:q4_k_m")["caps"], ["completion", "tools"])
        self.assertIsNone(om.lookup(got, "other:1"))
        self.assertIsNone(om.lookup({}, "m:q4_k_m"))
        self.assertIsNone(om.lookup(got, ""))

    def test_a_trailing_slash_on_the_base_url_is_fine(self):
        fake = FakeOllama({"models": [row("a:1", caps=[])]})
        self.assertIn("a:1", om.installed_details(BASE + "/", opener=fake))
        self.assertEqual(fake.seen[0][1], "/api/tags")


if __name__ == "__main__":
    unittest.main()
