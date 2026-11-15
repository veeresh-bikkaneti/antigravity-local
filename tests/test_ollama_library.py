"""The fragile library page scan: a saved snippet of the real markup, and every way the page can go wrong."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ollama_library as lib  # noqa: E402

CHIP_CAP = '<span class="inline-flex items-center rounded-md bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-600 sm:text-[13px]">%s</span>'
CHIP_SIZE = '<span class="inline-flex items-center rounded-md bg-[#ddf4ff] px-2 py-0.5 text-xs font-medium text-blue-600 sm:text-[13px]">%s</span>'


def item(name, caps=(), sizes=(), note="A model."):
    chips = "".join(CHIP_CAP % c for c in caps) + "".join(CHIP_SIZE % s for s in sizes)
    return (f'<li class="flex items-baseline border-b"><a href="/library/{name}" class="group w-full space-y-5">'
            f'<div title="{name}"><h2><span class="group-hover:underline truncate">{name}</span></h2>'
            f'<p class="max-w-lg break-words text-neutral-800 text-md">{note}</p></div>'
            f'<div class="flex flex-wrap space-x-2">{chips}</div></a></li>')


def page(*items):
    return '<div id="repo"><ul role="list">' + "".join(items) + "</ul></div>"


class Parse(unittest.TestCase):
    def test_name_badges_sizes_and_note(self):
        rows = lib.parse_library(page(item("llama3.1", ["tools"], ["8b", "70b"], "Llama 3.1 is a model.")))
        self.assertEqual(rows, [{"name": "llama3.1", "badges": ("tools",), "sizes": ("8b", "70b"), "note": "Llama 3.1 is a model."}])

    def test_several_capabilities_and_unknown_chips(self):
        rows = lib.parse_library(page(item("m", ["vision", "thinking", "cloud", "tools"], ["7b"])))
        self.assertEqual(rows[0]["badges"], ("vision", "thinking", "tools"))  # "cloud" is not a capability we know

    def test_a_model_without_chips_still_lists(self):
        self.assertEqual(lib.parse_library(page(item("plain")))[0]["badges"], ())

    def test_a_list_item_with_a_long_class_attribute_still_lists(self):
        long_class = " ".join(f"utility-{i}" for i in range(120))  # about 1,500 characters of classes
        self.assertGreater(len(long_class), 1000)
        li = item("llama3.1", ["tools"]).replace('<li class="flex items-baseline border-b">', f'<li class="{long_class}">', 1)
        self.assertIn(long_class, li)
        self.assertEqual([r["name"] for r in lib.parse_library(page(li))], ["llama3.1"])

    def test_duplicates_and_items_without_a_library_link_are_skipped(self):
        rows = lib.parse_library(page(item("a"), item("a"), "<li><a href='/other'>x</a></li>", item("b")))
        self.assertEqual([r["name"] for r in rows], ["a", "b"])

    def test_html_entities_and_long_notes_are_tidied(self):
        rows = lib.parse_library(page(item("m", note="Fast &amp; small. " + "x" * 300)))
        self.assertTrue(rows[0]["note"].startswith("Fast & small."))
        self.assertLessEqual(len(rows[0]["note"]), 100)

    def test_a_changed_page_gives_nothing_not_an_error(self):
        for junk in ("", "<html>maintenance</html>", None, 42, "<li>", "\x00" * 50):
            with self.subTest(junk=junk):
                self.assertEqual(lib.parse_library(junk), [])


class _Reply:
    def __init__(self, body):
        self.body = body

    def read(self, n=-1):
        return self.body if n < 0 else self.body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Scan(unittest.TestCase):
    def test_fetches_and_parses(self):
        body = page(item("qwen3", ["tools"], ["8b"])).encode("utf-8")
        rows = lib.scan(opener=lambda request, timeout=None: _Reply(body))
        self.assertEqual([r["name"] for r in rows], ["qwen3"])

    def test_any_failure_is_an_empty_list(self):
        def boom(request, timeout=None):
            raise OSError("offline")
        self.assertEqual(lib.scan(opener=boom), [])

    def test_a_page_with_bad_bytes_does_not_crash(self):
        self.assertEqual(lib.scan(opener=lambda request, timeout=None: _Reply(b"\xff\xfe\x00junk")), [])

    def test_it_asks_for_the_library_page_only(self):
        seen = []

        def opener(request, timeout=None):
            seen.append(request.full_url)
            return _Reply(b"")
        lib.scan(opener=opener)
        self.assertEqual(seen, ["https://ollama.com/library"])


if __name__ == "__main__":
    unittest.main()
