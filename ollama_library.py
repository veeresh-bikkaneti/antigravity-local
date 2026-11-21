"""Optional, FRAGILE: read the model list off https://ollama.com/library.

Ollama has no documented JSON API for its library, so this reads the HTML page. The markup is plain Tailwind classes
with no stable hooks, so a redesign can break it at any time. That is why it sits behind --scan-library and why a
page we cannot read gives an empty list instead of an error. The curated catalog stays the dependable list.

the fetch lives in the ollama platform module (agl/platform/ollama.py);
this file keeps the parsing (which is pure) and the same names for old imports and test patches.
"""
import bisect
import html
import re

from agl.platform import ollama as ollama_platform

MAX_BYTES = ollama_platform.MAX_BYTES  # moved to agl.platform.ollama
CAPABILITY_CHIPS = {"tools": "tools", "vision": "vision", "thinking": "thinking", "embedding": "embedding"}
# The page paints capability chips indigo and size chips blue. Anything else is ignored.
_ITEM_OPEN = re.compile(r'<li\b[^>]{0,4000}>')  # the cap keeps a flood of "<li" linear, and allows long real attributes
_ITEM_CLOSE = re.compile(r'</li>')
_LINK = re.compile(r'href="/library/([a-z0-9][a-z0-9._-]*)"', re.IGNORECASE)
_CHIP = re.compile(r'<span[^>]*class="[^"]*?(bg-indigo-50|bg-\[#ddf4ff\])[^"]*"[^>]*>\s*([^<]+?)\s*</span>', re.DOTALL)
_DESC = re.compile(r'<p[^>]*class="[^"]*max-w-lg[^"]*"[^>]*>(.*?)</p>', re.DOTALL)


def _items(page):
    """The body of each <li>...</li>, in order. Same answer as the old regex, but one pass: no backtracking over the
    rest of the page for every unclosed <li>."""
    closes = [m.start() for m in _ITEM_CLOSE.finditer(page)]
    pos = 0
    for opening in _ITEM_OPEN.finditer(page):
        if opening.start() < pos:
            continue  # inside the item we just took, as the old non-overlapping regex would have skipped it
        i = bisect.bisect_left(closes, opening.end())
        if i == len(closes):
            break  # no closing tag after this point, so none after the later ones either
        yield page[opening.end():closes[i]]
        pos = closes[i] + len("</li>")


def parse_library(page):
    """[{"name", "badges", "sizes", "note"}] from the library page HTML. Unreadable markup gives []."""
    if not isinstance(page, str):
        return []
    rows, seen = [], set()
    for item in _items(page):
        link = _LINK.search(item)
        if not link or link.group(1) in seen:
            continue
        name = link.group(1).lower()
        seen.add(name)
        badges, sizes = [], []
        for kind, text in _CHIP.findall(item):
            text = html.unescape(text).strip().lower()
            if kind == "bg-indigo-50":
                badge = CAPABILITY_CHIPS.get(text)
                if badge and badge not in badges:
                    badges.append(badge)
            elif text not in sizes:
                sizes.append(text)
        desc = _DESC.search(item)
        note = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", desc.group(1)))).strip() if desc else ""
        rows.append({"name": name, "badges": tuple(badges), "sizes": tuple(sizes), "note": note[:100]})
    return rows


def scan(opener=None, timeout=6):
    """Fetch and parse the page. Any failure is []."""
    # the page fetch lives in agl.platform.ollama; the None opener resolves there
    return parse_library(ollama_platform.library_page(opener=opener, timeout=timeout))
