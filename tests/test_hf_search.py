"""Hugging Face search: 24 h cache, back-off on 429, token handling and the offline path. No network, no real clock."""
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hf_search  # noqa: E402

URL = "https://huggingface.co/api/models?x=1"
T0 = 1_800_000_000.0
HOUR = 3600


class _Reply:
    def __init__(self, data):
        self.body = json.dumps(data).encode("utf-8")

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def too_many(headers=None):
    return urllib.error.HTTPError(URL, 429, "slow down", headers or {}, io.BytesIO(b""))


class Net:
    """A scripted opener: each call pops the next item (a payload, or an exception to raise). Records requests."""

    def __init__(self, *script):
        self.script, self.requests = list(script), []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return _Reply(item)


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self._tmp.name) / "cache"
        self.addCleanup(self._tmp.cleanup)
        self.clock = [T0]
        self.slept = []

    def fetch(self, net, **kw):
        return hf_search.fetch_json(URL, cache_dir=self.cache, now=lambda: self.clock[0], opener=net,
                                    sleep=self.slept.append, **kw)


class Cache(Base):
    def test_second_call_inside_24h_never_touches_the_network(self):
        self.assertEqual(self.fetch(Net({"a": 1})), ({"a": 1}, "net"))
        self.clock[0] += 23 * HOUR + 3599
        net = Net()
        self.assertEqual(self.fetch(net), ({"a": 1}, "cache"))
        self.assertEqual(net.requests, [])

    def test_cache_expires_at_24h(self):
        self.fetch(Net({"a": 1}))
        self.clock[0] += 24 * HOUR
        net = Net({"a": 2})
        self.assertEqual(self.fetch(net), ({"a": 2}, "net"))
        self.assertEqual(len(net.requests), 1)

    def test_a_cache_stamped_in_the_future_is_not_trusted(self):
        self.fetch(Net({"a": 1}))
        self.clock[0] -= 5 * HOUR  # the clock went backwards
        self.assertEqual(self.fetch(Net({"a": 2})), ({"a": 2}, "net"))

    def test_a_corrupt_cache_file_is_ignored_and_replaced(self):
        self.cache.mkdir(parents=True)
        hf_search.cache_path(URL, self.cache).write_text("{not json", encoding="utf-8")
        self.assertEqual(self.fetch(Net({"a": 1})), ({"a": 1}, "net"))
        self.assertEqual(self.fetch(Net()), ({"a": 1}, "cache"))

    def test_the_cache_file_is_named_from_a_hash_of_the_url(self):
        self.fetch(Net({"a": 1}))
        names = [p.name for p in self.cache.iterdir()]
        self.assertEqual(len(names), 1)
        self.assertRegex(names[0], r"^hf-[0-9a-f]{40}\.json$")

    def test_an_unwritable_cache_folder_does_not_break_the_fetch(self):
        with tempfile.NamedTemporaryFile() as blocker:
            got = hf_search.fetch_json(URL, cache_dir=Path(blocker.name) / "c", now=lambda: T0, opener=Net({"a": 1}),
                                       sleep=self.slept.append)
        self.assertEqual(got, ({"a": 1}, "net"))


class Offline(Base):
    def test_offline_with_no_cache_is_none_and_offline(self):
        self.assertEqual(self.fetch(Net(urllib.error.URLError("down"))), (None, "offline"))

    def test_offline_with_an_expired_cache_serves_it_as_stale(self):
        self.fetch(Net({"a": 1}))
        self.clock[0] += 48 * HOUR
        self.assertEqual(self.fetch(Net(OSError("offline"))), ({"a": 1}, "stale"))

    def test_a_server_error_is_treated_like_offline_without_retrying(self):
        net = Net(urllib.error.HTTPError(URL, 500, "boom", {}, io.BytesIO(b"")))
        self.assertEqual(self.fetch(net), (None, "offline"))
        self.assertEqual((len(net.requests), self.slept), (1, []))

    def test_junk_json_is_offline_not_a_crash(self):
        class Junk:
            def __call__(self, request, timeout=None):
                r = _Reply(None)
                r.body = b"<html>oops"
                return r
        self.assertEqual(self.fetch(Junk()), (None, "offline"))


class Backoff(Base):
    def test_retry_after_is_obeyed(self):
        net = Net(too_many({"Retry-After": "7"}), {"ok": True})
        self.assertEqual(self.fetch(net), ({"ok": True}, "net"))
        self.assertEqual(self.slept, [7.0])

    def test_ratelimit_header_t_is_used_when_there_is_no_retry_after(self):
        net = Net(too_many({"RateLimit": '"api";r=0;t=9'}), {"ok": True})
        self.fetch(net)
        self.assertEqual(self.slept, [9.0])

    def test_no_hint_waits_2_then_4_seconds_then_gives_up_after_two_retries(self):
        net = Net(too_many(), too_many(), too_many())
        self.assertEqual(self.fetch(net), (None, "offline"))
        self.assertEqual(self.slept, [2.0, 4.0])
        self.assertEqual(len(net.requests), 3)  # the first try plus two retries, never more

    def test_a_huge_wait_is_capped(self):
        net = Net(too_many({"Retry-After": "3000"}), {"ok": True})
        self.fetch(net)
        self.assertEqual(self.slept, [30.0])

    def test_junk_wait_values_fall_back_to_the_defaults(self):
        net = Net(too_many({"Retry-After": "soon"}), too_many({"RateLimit": "t=never"}), {"ok": True})
        self.fetch(net)
        self.assertEqual(self.slept, [2.0, 4.0])

    def test_nan_and_infinite_wait_values_never_crash_the_wait(self):
        for value in ("nan", "NaN", "-inf"):
            with self.subTest(value=value):
                self.slept.clear()
                self.clock[0] += 30 * HOUR  # last round's answer must not be served from the cache
                net = Net(too_many({"Retry-After": value}), too_many({"RateLimit": f"t={value}"}), {"ok": True})
                self.assertEqual(self.fetch(net), ({"ok": True}, "net"))
                self.assertEqual(self.slept, [2.0, 4.0])
        self.slept.clear()
        self.clock[0] += 30 * HOUR
        self.fetch(Net(too_many({"Retry-After": "inf"}), {"ok": True}))
        self.assertEqual(self.slept, [30.0])

    def test_an_answer_that_is_not_a_list_is_not_cached_as_search_results(self):
        rows, source = hf_search.search_models(self.cache, opener=Net({"error": "rate limited"}), now=lambda: self.clock[0], sleep=self.slept.append)
        self.assertEqual(rows, [])
        self.assertEqual(list(self.cache.glob("hf-*.json")), [])

    def test_still_limited_after_retries_serves_a_stale_cache(self):
        self.fetch(Net({"a": 1}))
        self.clock[0] += 30 * HOUR
        self.assertEqual(self.fetch(Net(too_many(), too_many(), too_many())), ({"a": 1}, "stale"))


class Token(Base):
    def test_no_token_means_no_authorization_header(self):
        net = Net({"a": 1})
        self.fetch(net)
        self.assertNotIn("Authorization", net.requests[0].headers)

    def test_a_token_is_sent_as_a_bearer_header_and_never_cached(self):
        net = Net({"a": 1})
        self.fetch(net, token="hf_secret123")
        self.assertEqual(net.requests[0].get_header("Authorization"), "Bearer hf_secret123")
        for p in self.cache.iterdir():
            self.assertNotIn("hf_secret123", p.read_text(encoding="utf-8"))


class Search(Base):
    ROW_CHAT = {"id": "u/chat-GGUF", "downloads": 5000, "lastModified": "2026-11-01T00:00:00.000Z",
                "pipeline_tag": "text-generation",
                "gguf": {"chat_template": "{% if tools %}x{% endif %}<think>", "context_length": 32768, "totalFileSize": 5_000_000_000}}
    ROW_MEDIA = {"id": "u/pic", "pipeline_tag": "text-to-image", "downloads": 10}

    def test_url_asks_for_gguf_sorted_by_downloads_with_every_field_we_read(self):
        url = hf_search.search_url("qwen coder", "text-generation", 20)
        for part in ("filter=gguf", "pipeline_tag=text-generation", "sort=downloads", "limit=20", "search=qwen+coder",
                     "expand[]=gguf", "expand[]=downloads", "expand[]=lastModified", "expand[]=pipeline_tag", "expand[]=tags"):
            self.assertIn(part, url)
        self.assertNotIn("search=", hf_search.search_url(None))

    def test_rows_get_badges_kind_and_numbers(self):
        rows, source = hf_search.search_models(self.cache, now=lambda: T0, opener=Net([self.ROW_CHAT, self.ROW_MEDIA]),
                                               sleep=self.slept.append)
        self.assertEqual(source, "net")
        chat, pic = rows
        self.assertEqual((chat["repo"], chat["downloads"], chat["kind"], chat["context_length"], chat["total_file_size"]),
                         ("u/chat-GGUF", 5000, "chat", 32768, 5_000_000_000))
        self.assertEqual(chat["badges"], ("tools?", "thinking?"))  # guesses from the template, so they keep the ?
        self.assertEqual((pic["kind"], pic["badges"]), ("media", ("image",)))

    def test_the_chat_template_itself_is_never_kept(self):
        rows, _ = hf_search.search_models(self.cache, now=lambda: T0, opener=Net([self.ROW_CHAT]), sleep=self.slept.append)
        self.assertNotIn("chat_template", json.dumps(rows))

    def test_odd_rows_are_skipped_or_tolerated(self):
        data = ["not a dict", {"pipeline_tag": "text-generation"}, {"id": "u/ok", "downloads": "many", "gguf": "nope"}]
        rows, _ = hf_search.search_models(self.cache, now=lambda: T0, opener=Net(data), sleep=self.slept.append)
        self.assertEqual([r["repo"] for r in rows], ["u/ok"])
        self.assertIsNone(rows[0]["downloads"])

    def test_a_reply_that_is_not_a_list_is_empty(self):
        rows, _ = hf_search.search_models(self.cache, now=lambda: T0, opener=Net({"error": "nope"}), sleep=self.slept.append)
        self.assertEqual(rows, [])

    def test_offline_gives_no_rows_and_says_so(self):
        got = hf_search.search_models(self.cache, now=lambda: T0, opener=Net(OSError("down")), sleep=self.slept.append)
        self.assertEqual(got, ([], "offline"))


if __name__ == "__main__":
    unittest.main()
