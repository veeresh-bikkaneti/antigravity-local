"""Pick a local model with a short menu instead of silently taking the first one. Standard library only.

Why this exists: run.py used to grab whatever was already installed and call it "most capable".
Models move fast, so we show what is installed plus a short list of newer candidates, say what fits
this machine, and let the human choose. Enter keeps the current pick, so it costs one keypress.
"""
import json
import re
import urllib.error

import capabilities
from agl.platform import http

# Re-check this list when you touch it: `curl -I https://registry.ollama.ai/v2/library/<name>/manifests/<tag>`
# must return 200, and sizes come from the manifest layers. Nothing here has been run through this
# project's agent loop yet, so the notes say what is reported, not what we measured.
CATALOG_VERIFIED = "2026-11-15"
# Sizes were read on each Ollama tag page: https://ollama.com/library/<model>/tags (checked 2026-11-15).
# devstral-small-2:24b is the family tag; its exact q4_K_M tag is devstral-small-2:24b-instruct-2512-q4_K_M (15GB).
CATALOG = [
    # (tag, size_gb, note)
    ("devstral-small-2:24b", 15.0, "Built for agentic coding and multi-file edits (Mistral)"),
    ("gpt-oss:20b", 14.0, "OpenAI open-weight model, native tool calling"),
    ("qwen3.6:27b", 17.8, "Qwen3 line with native tool calling, the established pick"),
    ("qwen3.8:27b", 17.7, "Newest Qwen; strongest reported coding, but tool calling is new and unproven"),
    ("qwen3-coder:30b", 19.0, "Coding-tuned mixture-of-experts, fast for its size"),
    ("glm-4.7-flash:q4_K_M", 19.0, "GLM-4.7 Flash, a quick agentic coder from Zhipu (q4_K_M quant)"),
    ("qwen3-coder-next:q4_K_M", 52.0, "Large coding model; at 52GB it only fits big machines"),
    ("laguna-xs.2:latest", 23.1, "Long-horizon agent model; reported by third-party guides only"),
    # Not on Ollama's library (registry 404), so it comes from Hugging Face. Verified 2026-11-14: the Hub API lists
    # a Q4_K_M .gguf in mradermacher/Nanbeige4.1-3B-GGUF (2.44 GB), and `ollama pull` of this tag succeeded (2.4 GB).
    ("hf.co/mradermacher/nanbeige4.1-3b-gguf:q4_k_m", 2.4,
     "Nanbeige4.1-3B agentic tool caller, a GGUF that Ollama pulls from Hugging Face"),
]


TAG_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]*(:[a-z0-9._-]+)?$")
REPO_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*")  # used with fullmatch: one slash, no spaces or shell characters


MAX_PICK_DIGITS = 6


def _is_repo_id(repo):
    # ".." is allowed by the character class (dots are fine in names) but a repo id with it is a path trick.
    return isinstance(repo, str) and REPO_RE.fullmatch(repo) is not None and ".." not in repo

# Hugging Face: Ollama pulls any public GGUF with `ollama pull hf.co/{username}/{repository}:{quantization}`.
# Only the Ollama backend can do that, so the menu hides this row on an OpenAI-compatible server.
HF_PREFIXES = ("hf.co/", "huggingface.co/")
HF_ROW_TAG = "hf.co/<user>/<repo>:<quant>"  # placeholder shown on the menu row, never returned as a pick
QUANT_RE = re.compile(r"(?<![A-Za-z0-9])((?:IQ|Q)\d(?:_[A-Z0-9]+)*|BF16|F16|F32)(?![A-Za-z0-9])", re.IGNORECASE)


def is_hf_tag(tag):
    return (tag or "").strip().lower().startswith(HF_PREFIXES)


def parse_hf_tag(tag):
    """(user, repo, quant or None) for hf.co/user/repo[:quant], or None when the shape is wrong."""
    text = (tag or "").strip()
    for prefix in HF_PREFIXES:
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
            break
    else:
        return None
    path, _, quant = text.partition(":")
    parts = path.split("/")
    if len(parts) != 2 or not all(parts):
        return None
    return parts[0], parts[1], (quant or None)


def _hf_api_model(user, repo, timeout=4):
    """The Hub's model record for user/repo, fetched through the same-host opener. Returns (status, data):
    'ok' with a dict, 'missing' (a 404), or 'unknown' (offline, private or gated, odd reply; data None).
    Sends only the repo name. Both hf_check and hf_repo_info read through here."""
    try:
        with _HF_OPENER.open(f"https://huggingface.co/api/models/{user}/{repo}", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return ("missing", None) if e.code == 404 else ("unknown", None)
    except Exception:
        return "unknown", None
    if not isinstance(data, dict):
        return "unknown", None
    return "ok", data


def hf_check(tag, timeout=4):
    """Ask the Hugging Face API about an hf.co tag. Returns (status, detail), status one of:
    'ok'       the repo is there (and has a .gguf for the quant, when one was given)
    'missing'  the repo is a 404: refuse it
    'no_quant' the repo exists but no .gguf matches the quant; detail = the quants it does have
    'bad_tag'  not hf.co/user/repo[:quant]
    'unknown'  could not tell (offline, private or gated repo, odd reply): allow it, like the Ollama registry check
    Sends only the repo name."""
    parsed = parse_hf_tag(tag)
    if not parsed:
        return "bad_tag", None
    user, repo, quant = parsed
    status, data = _hf_api_model(user, repo, timeout=timeout)
    if status != "ok":
        return status, None
    if not quant:
        return "ok", None
    files = [s.get("rfilename", "") for s in (data.get("siblings") or []) if s.get("rfilename", "").lower().endswith(".gguf")]
    have = sorted({q.upper() for f in files for q in QUANT_RE.findall(f)})
    if quant.upper() in have:
        return "ok", None
    return "no_quant", have


def _norm(tag):
    tag = tag.strip().lower()
    return tag if ":" in tag.split("/")[-1] else tag + ":latest"


FIT_HEADROOM = 1.2         # a model needs its file size x 1.2 (context and buffers) to sit in memory
LEGACY_HEADROOM = 1 / 0.9  # the old "90% of total VRAM" rule, kept as the default for old callers
SPLIT_RAM_SHARE = 0.7      # share of free RAM we count on when part of the model runs on the CPU


def fit_label(size_gb, vram_gb, ram_gb, headroom=LEGACY_HEADROOM):
    """'gpu' if the model sits in VRAM with room to spare, 'split' if part runs on the CPU, else 'too big'.
    Pass FREE vram and ram with headroom=FIT_HEADROOM to fit against what is available right now."""
    need = size_gb * headroom
    if need <= vram_gb:
        return "gpu"
    if need <= vram_gb + ram_gb * SPLIT_RAM_SHARE:
        return "split"
    return "too big"


FIT_TEXT = {"gpu": "fits in GPU", "split": "part on CPU", "too big": "too big"}
LEGEND = "Fast = fits in your graphics card · Moderate = part on CPU · Slow = mostly CPU (estimate from size and memory)"


def speed_label(size_gb, vram_gb, ram_gb, headroom=FIT_HEADROOM):
    """How fast tokens should come: 'Fast' when the model sits in VRAM, 'Moderate' when it splits with at least half
    in VRAM, 'Slow' when it splits with less (or there is no GPU at all). None when it is too big to run, or the
    size is unknown. An estimate from size and memory, not a measurement."""
    if not size_gb or size_gb <= 0:
        return None
    fit = fit_label(size_gb, vram_gb, ram_gb, headroom=headroom)
    if fit == "gpu":
        return "Fast"
    if fit == "split":
        return "Moderate" if vram_gb >= size_gb * headroom / 2 else "Slow"
    return None
TOP_DOWNLOADS = 3  # catalog rows shown on the main list; the rest sit behind "More downloads"
MORE_ROW_TAG = "More downloads"
MEDIA_ROW_TAG = "Image and video models"


def hf_repo_info(user, repo, timeout=4):
    """{'status': 'ok'|'missing'|'unknown', 'gated': bool, 'license': str|None} for a Hugging Face repo.
    Sends only the repo name. gated can be False, True, 'auto' or 'manual' on the Hub: anything truthy counts."""
    status, data = _hf_api_model(user, repo, timeout=timeout)
    if status != "ok":
        return {"status": status, "gated": False, "license": None}
    card = data.get("cardData") if isinstance(data.get("cardData"), dict) else {}
    lic = card.get("license")
    if not lic:
        lic = next((t[len("license:"):] for t in data.get("tags") or [] if isinstance(t, str) and t.startswith("license:")), None)
    return {"status": "ok", "gated": bool(data.get("gated")), "license": str(lic) if lic else None}


_SameHostOnly = http._SameHostOnly  # moved, shim until Phase 6: the class now lives in agl.platform.http
_HF_OPENER = http.same_host_opener()  # moved, shim until Phase 6: built by the platform http helper
_REGISTRY_OPENER = http.same_host_opener()  # registry.ollama.ai: a cross-host redirect is not followed
_STATE = {"offline": False}  # set when the Hub cannot be reached; later calls in the run stop asking


def hf_tree_files(user, repo, timeout=6, max_pages=5):
    """[{'name', 'size'}] for every file in the repo (sizes in bytes, from the LFS size when there is one).
    Follows the Link: rel=next header up to max_pages, on huggingface.co only. Any failure returns []."""
    url = f"https://huggingface.co/api/models/{user}/{repo}/tree/main?expand=true&recursive=true"
    files = []
    for _ in range(max_pages):
        try:
            with _HF_OPENER.open(url, timeout=timeout) as resp:
                rows = json.loads(resp.read().decode("utf-8"))
                link = resp.headers.get("Link", "") if getattr(resp, "headers", None) else ""
        except urllib.error.HTTPError:
            return []  # the Hub answered with an error: say nothing rather than give a wrong size
        except (urllib.error.URLError, OSError, TimeoutError):
            _STATE["offline"] = True  # no network: stop asking for the rest of the run
            return []
        except Exception:
            return []  # a half-read repo would undercount split quants, so say nothing rather than give a wrong size
        if not isinstance(rows, list):
            return []
        for row in rows:
            if isinstance(row, dict) and row.get("type", "file") == "file":
                size = (row.get("lfs") or {}).get("size") if isinstance(row.get("lfs"), dict) else None
                files.append({"name": row.get("path", ""), "size": size if size else row.get("size")})
        nxt = re.search(r'<([^>]+)>;\s*rel="next"', link or "")
        if not nxt:
            break
        url = nxt.group(1)
        if not url.startswith("https://huggingface.co/"):
            return []  # never follow a page link to another host
    else:
        return []  # still more pages after max_pages: a partial list would undercount split quants
    return files


def _badge_list(value):
    """Badges as a tuple of non-empty strings. A bare string is one badge (never split into letters); anything
    that is not a list or tuple, and any non-string item, counts as unknown and is dropped."""
    if isinstance(value, str):
        value = (value,)
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(b for b in value if isinstance(b, str) and b.strip())


def _text(value):
    """A note or hint as stripped text. Anything that is not a string, or is blank, becomes ''."""
    return value.strip() if isinstance(value, str) else ""


def _badges(tag, known=None):
    """Badges for a row: what we were told (installed models), else the curated catalog, plus a coding hint."""
    found = known.get(_norm(tag)) if known else None
    if found is None:
        found = capabilities.catalog_badges(tag)
    extra = capabilities.coding_badge(tag)
    out = _badge_list(found)
    return out + ((extra,) if extra and extra not in out else ())


def _sized(tag, list_gb, size_of):
    """(gb, source) for a download row. `size_of(tag, list_gb)` is the caller's resolver (see download_size.resolve);
    without one, only our own list number is known."""
    info = size_of(tag, list_gb) if size_of else ({"gb": list_gb, "source": "list"} if list_gb else None)
    return (info["gb"], info["source"]) if info and info.get("gb") else (None, None)


def build_menu(installed, vram_gb, ram_gb, catalog=CATALOG, recommended=None, backend="ollama",
               badges=None, library=None, media=None, size_of=None, upgrade=None, installed_info=None):
    """Installed models first (no download), then the upgrade row if given, then the hardware pick if given, then
    catalog models that can run here, then one row that explains how to type a Hugging Face model.

    `upgrade` is a better model that fits this PC ({"tag", "gb", "label", "fit"}, from run._upgrade_candidates).
    It is one row marked "recommended upgrade", so the menu stays one list with one prompt.

    `recommended` is the tier pick for this PC (run.hardware_tier_model). Its size is not known without a
    registry call, so the row says so instead of guessing.
    On an OpenAI-compatible server (backend="openai") only the models it lists are offered: we cannot download
    anything there, so no catalog rows and no Hugging Face row.

    `badges` maps a normalised installed tag to its badges (from /api/show); `library` is extra scanned rows
    ({"tag", "badges", "note"}); `media` are image/video/audio rows that are listed but never picked for an agent
    ({"tag", "badges", "note", "hint"}): choosing one only shows its hint.

    `installed_info` maps a normalised installed tag to {"size_gb", "digest"} (Ollama /api/tags). With it, installed
    rows get a size and a speed badge; a tag with no entry gets neither (never a guess). Two tags with the same
    digest are one file, so only one row is shown; if either digest is missing both stay and say so.
    """
    have = {_norm(m) for m in installed}
    info = {_norm(k): v for k, v in (installed_info or {}).items() if isinstance(v, dict)}
    tags = _one_row_per_file(sorted(installed), info)
    menu = []
    for m in tags:
        i = info.get(_norm(m)) or {}
        gb = i.get("size_gb") if isinstance(i.get("size_gb"), (int, float)) and i.get("size_gb") > 0 else None
        speed = (speed_label(gb, vram_gb, ram_gb, headroom=FIT_HEADROOM) or "Slow") if gb else None
        menu.append({"tag": m, "installed": True, "size_gb": gb, "size_source": "installed" if gb else None,
                     "fit": None, "speed": speed, "badges": _badges(m, badges),
                     "note": "already on this machine" if backend != "openai" else "loaded on your server",
                     "twin": _has_twin(m, tags, info)})
    if backend == "openai":
        return menu
    if upgrade and _norm(upgrade["tag"]) not in have:
        menu.append({"tag": upgrade["tag"], "installed": False, "size_gb": upgrade["gb"],
                     "size_source": upgrade.get("label"), "fit": upgrade.get("fit"),
                     "speed": speed_label(upgrade["gb"], vram_gb, ram_gb, headroom=FIT_HEADROOM),
                     "badges": _badges(upgrade["tag"]), "note": "recommended upgrade"})
        have.add(_norm(upgrade["tag"]))
    if recommended and _norm(recommended) not in have:
        gb, src = _sized(recommended, None, size_of)
        menu.append({"tag": recommended, "installed": False, "size_gb": gb, "size_source": src,
                     "fit": fit_label(gb, vram_gb, ram_gb, headroom=FIT_HEADROOM) if gb else None,
                     "speed": speed_label(gb, vram_gb, ram_gb, headroom=FIT_HEADROOM) if gb else None,
                     "badges": _badges(recommended), "note": "recommended for this PC"})
        have.add(_norm(recommended))
    shown = 0
    for tag, size, note in catalog:
        if _norm(tag) in have:
            continue
        gb, src = _sized(tag, size, size_of)
        fit = fit_label(gb, vram_gb, ram_gb, headroom=FIT_HEADROOM) if gb else None
        if fit == "too big":
            continue
        menu.append({"tag": tag, "installed": False, "size_gb": gb, "size_source": src, "fit": fit,
                     "speed": speed_label(gb, vram_gb, ram_gb, headroom=FIT_HEADROOM) if gb else None,
                     "badges": _badges(tag), "note": note, "hidden": shown >= TOP_DOWNLOADS})
        shown += 1
        have.add(_norm(tag))
    for row in library or []:
        if _norm(row["tag"]) not in have:
            have.add(_norm(row["tag"]))
            gb, src = _sized(row["tag"], None, size_of)
            menu.append({"tag": row["tag"], "installed": False, "size_gb": gb, "size_source": src,
                         "fit": fit_label(gb, vram_gb, ram_gb, headroom=FIT_HEADROOM) if gb else None,
                         "speed": speed_label(gb, vram_gb, ram_gb, headroom=FIT_HEADROOM) if gb else None,
                         "badges": _badge_list(row.get("badges")), "note": row.get("note", "from the Ollama library page"),
                         "hidden": True})
    loader = media if callable(media) else None  # a callable is asked only when the media row is picked
    for row in ([] if loader else media or []):
        if _norm(row["tag"]) in have:  # already listed (installed, catalog or library): one row per model
            continue
        have.add(_norm(row["tag"]))
        menu.append(_media_row(row))
    if any(m.get("hidden") and not m.get("media") for m in menu):
        menu.append({"tag": MORE_ROW_TAG, "installed": False, "size_gb": None, "fit": None, "more": True})
    if loader or any(m.get("media") for m in menu):
        menu.append({"tag": MEDIA_ROW_TAG, "installed": False, "size_gb": None, "fit": None, "media_row": True,
                     "loader": loader, "known": sorted(have)})
    menu.append({"tag": HF_ROW_TAG, "installed": False, "size_gb": None, "fit": None, "hf": True,
                 "note": "A Hugging Face model (type hf.co/user/repo:quant)"})
    return menu


def _one_row_per_file(tags, info):
    """Drop a tag whose digest equals another installed tag's (the same file under two names). Keep the longer,
    fuller name (hf.co/user/repo:quant over repo:quant). No digest on either side: keep both."""
    out = []
    for t in sorted(tags, key=lambda x: (-len(x), x)):
        d = (info.get(_norm(t)) or {}).get("digest")
        if d and any((info.get(_norm(o)) or {}).get("digest") == d for o in out):
            continue
        out.append(t)
    return sorted(out)


def _has_twin(tag, tags, info):
    """A short note when another shown row has the same repo:quant name: 'different file, same name' when both
    digests are known and differ, else 'may be the same file as <other>'. '' when there is no look-alike."""
    short = _norm(tag).split("/")[-1]
    for o in tags:
        if o == tag or _norm(o).split("/")[-1] != short:
            continue
        a, b = (info.get(_norm(tag)) or {}).get("digest"), (info.get(_norm(o)) or {}).get("digest")
        return "different file, same name" if a and b else "may be the same file as " + o
    return ""


def _media_row(row):
    return {"tag": row["tag"], "installed": False, "size_gb": None, "fit": None, "media": True, "hidden": True,
            "badges": _badge_list(row.get("badges")), "note": _text(row.get("note")), "hint": _text(row.get("hint"))}


def _visible(menu):
    """The rows on the main list, in order. Their position here is the number the user types."""
    return [m for m in menu if not m.get("hidden")]


def _is_pick(m):
    """A row that is a real model the user can choose (not a section row, not media)."""
    return not any(m.get(k) for k in ("hf", "media", "more", "media_row"))


def _has_tools(badges):
    return any(isinstance(b, str) and b.startswith("tools") for b in (badges or ()))


def _word(m):
    """One word on what the model can do. 'tools' only when confirmed; 'chat only' for an installed model with no
    tool badge at all. A guessed 'tools?' shows nothing on the main list (the Hugging Face list keeps it)."""
    badges = [b for b in (m.get("badges") or ()) if isinstance(b, str)]
    if "tools" in badges:
        return "tools"
    if any(b.startswith("tools") for b in badges):
        return ""
    return "chat only" if m.get("installed") else ""


def _row_line(i, m, default_tag, width):
    """One numbered row: number, name, speed, size, one word, then `current` or a short recommendation."""
    current = _norm(m["tag"]) == _norm(default_tag or "")
    star = "*" if current else " "
    if m.get("size_gb") is None:
        size = "size unknown" if not m.get("installed") else ""
    else:
        size = f"~{m['size_gb']:.1f} GB est." if m.get("size_source") == "estimate" else f"{m['size_gb']:.1f} GB"
    note = m.get("note") or ""
    suffix = "  ".join(x for x in ("current" if current else "", note if note.startswith("recommended") else "") if x)
    if m.get("twin"):
        suffix = (suffix + "  " if suffix else "") + m["twin"]
    cols = f"{m.get('speed') or '':<8}  {size:>12}  {_word(m):<9}  {suffix}"
    return f"       {star}{i:>2}. {m['tag']:<{width}}  {cols}".rstrip()


def render(menu, default_tag, backend="ollama"):
    rows = _visible(menu)
    width = min(50, max([len(m["tag"]) for m in rows if _is_pick(m)] or [0]))
    lines = []
    section = None
    for i, m in enumerate(rows, 1):
        if not _is_pick(m):
            if section != "special":
                section = "special"
                lines.append("")
            if m.get("more"):
                n = sum(1 for r in menu if r.get("hidden") and not r.get("media"))
                lines.append(f"        {i:>2}. {MORE_ROW_TAG} ({n} more)")
            elif m.get("media_row"):
                lines.append(f"        {i:>2}. {MEDIA_ROW_TAG} (not for coding)")
            else:
                lines.append(f"        {i:>2}. {m['note']}")
            continue
        want = "installed" if m["installed"] else "download"
        if want != section:
            if section:
                lines.append("")
            section = want
            lines.append("       " + (("Loaded on your server" if backend == "openai" else "On this PC, no download")
                                       if want == "installed" else "Worth downloading"))
        lines.append(_row_line(i, m, default_tag, width))
    if lines:
        lines.append("")
    lines.append(f"       {LEGEND}")
    lines.append(f"       tools = can edit files. Download list checked {CATALOG_VERIFIED}, not yet run through this project's agent loop.")
    keep = (f"Enter keeps {default_tag}" if default_tag
            else "Enter picks 1" if rows else "Enter continues with the automatic pick")
    what = "a model id your server lists" if backend == "openai" else "any Ollama tag"
    lines.append(f"       {keep}. Or type a number, or {what}.")
    return lines


def _search_size_text(r):
    """'  Q4_K_M 2.4 GB download' for a search row that was sized, '' when it was not."""
    if r.get("size_gb") is None:
        return ""
    approx = "~" if r.get("size_source") == "estimate" else ""
    quant = f"{r['quant']} " if r.get("quant") else ""
    tail = " (estimate)" if r.get("size_source") == "estimate" else ""
    return f"  {quant}{approx}{r['size_gb']:.1f} GB download{tail}"


def _search_pick(results, input_fn, out):
    """Show Hugging Face search results with their badges and let the user pick one. Returns hf.co/<repo> or None."""
    shown = [r for r in results if _is_repo_id(r.get("repo"))][:10]  # malformed repos are skipped before numbering
    for i, r in enumerate(shown, 1):
        badge_text = f"  ({capabilities.format_badges(r.get('badges'))})" if r.get("badges") else ""
        downloads = f"  {r['downloads']:,} downloads" if isinstance(r.get("downloads"), int) else ""
        out(f"       {i:>2}. {r['repo']}{badge_text}{downloads}{_search_size_text(r)}")
    out("       (a ? after a badge is a guess from the chat template; run python run.py --probe to check it)")
    try:
        raw = input_fn("       Pick a number, or Enter to go back > ").strip()
    except EOFError:
        return None
    if raw.isascii() and raw.isdigit() and len(raw) <= MAX_PICK_DIGITS and 1 <= int(raw) <= len(shown):
        return "hf.co/" + shown[int(raw) - 1]["repo"].lower()
    return None


def _gave_up(out, fallback, default_tag, default_label=None):
    """One line after three bad tries: which model we use instead, and why we stopped asking.
    `default_label` says what the default is ("current model" or "recommended pick"); the caller knows, we don't."""
    if not fallback:
        out("       No valid pick after 3 tries, using the automatic pick.")
        return
    if fallback == default_tag:
        label = default_label or "current model"
    else:
        label = "first option"
    out(f"       No valid pick after 3 tries, using {fallback} ({label}).")


def _ask_hf_tag(input_fn, out, fallback, search_fn=None, validate_fn=None, default_tag=None, default_label=None):
    """The Hugging Face row was picked: ask for a tag, or for words to search for. Blank returns the fallback.
    A tag that validate_fn rejects prints why and asks again. Three bad tries print one line and give the fallback."""
    prompt = "       hf.co tag (hf.co/user/repo:quant)" + (", or words to search for > " if search_fn else " > ")
    for _ in range(3):
        try:
            raw = input_fn(prompt).strip().lower()
        except EOFError:
            return fallback
        if not raw:
            return fallback
        if is_hf_tag(raw) and TAG_RE.match(raw):
            problem = validate_fn(raw) if validate_fn else None
            if problem is None:
                return raw
            out(problem)
            continue
        if search_fn and not is_hf_tag(raw) and raw not in YES_NO:
            results = search_fn(raw)
            if not results:
                out("       No GGUF models found (or Hugging Face could not be reached). Try other words.")
                continue
            picked = _search_pick(results, input_fn, out)
            if picked:
                problem = validate_fn(picked) if validate_fn else None
                if problem is None:
                    return picked
                out(problem)
            continue
        out("       That is not a Hugging Face tag. Use the form hf.co/user/repo:quant.")
    _gave_up(out, fallback, default_tag, default_label)
    return fallback


YES_NO = {"y", "yes", "n", "no"}


def _sub_list(rows, out):
    """Print a numbered side list (more downloads, or media). The numbers restart at 1 inside it."""
    width = min(50, max([len(m["tag"]) for m in rows] or [0]))
    for i, m in enumerate(rows, 1):
        if m.get("media"):
            b = capabilities.format_badges(m.get("badges"))
            out(f"       {i:>2}. {m['tag']:<{width}}  {b + '  ' if b else ''}{m.get('note') or ''}".rstrip())
        else:
            out(_row_line(i, m, None, width))


def _more_pick(menu, input_fn, out, validate_fn):
    """The 'More downloads' side list. Returns a tag, or None for 'go back to the main list'."""
    rows = [m for m in menu if m.get("hidden") and not m.get("media")]
    _sub_list(rows, out)
    for _ in range(3):
        try:
            raw = input_fn("       Pick a number, or Enter to go back > ").strip()
        except EOFError:
            return None
        if not raw:
            return None
        if raw.isascii() and raw.isdigit() and len(raw) <= MAX_PICK_DIGITS and 1 <= int(raw) <= len(rows):
            problem = validate_fn(rows[int(raw) - 1]["tag"]) if validate_fn else None
            if problem is None:
                return rows[int(raw) - 1]["tag"]
            out(problem)
            continue
        out(f"       Pick 1 to {len(rows)}, or press Enter to go back.")
    return None


def _media_rows(row, menu):
    """Media rows for the side list: the ones already in the menu plus whatever the lazy loader finds now."""
    rows = [m for m in menu if m.get("media")]
    if row.get("loader"):
        known = set(row.get("known") or ())
        try:
            found = row["loader"]() or []
        except Exception:  # noqa: BLE001 - a failed lookup is an empty list, never a crash
            found = []
        for r in found:
            if isinstance(r, dict) and r.get("tag") and _norm(r["tag"]) not in known:
                known.add(_norm(r["tag"]))
                rows.append(_media_row(r))
    return rows


def _media_loop(row, menu, input_fn, out):
    """The 'Image and video models' side list. A number prints how to run that model and stays here.
    Enter goes back to the main list. None of this is a bad try."""
    rows = _media_rows(row, menu)
    if not rows:
        out("       No image or video models found (or Hugging Face could not be reached).")
        return
    out("       Image and video models. This tool does not run them, so none of these can be picked.")
    _sub_list(rows, out)
    wrong = 0
    while wrong < 3:
        try:
            raw = input_fn("       Type a number to see how to run it, or Enter to go back > ").strip()
        except EOFError:
            return
        if not raw:
            return
        if raw.isascii() and raw.isdigit() and len(raw) <= MAX_PICK_DIGITS and 1 <= int(raw) <= len(rows):
            out(f"       {rows[int(raw) - 1].get('hint') or 'Media models are not used by coding agents.'}")
            continue
        wrong += 1
        out(f"       Pick 1 to {len(rows)}, or press Enter to go back.")


def choose(menu, default_tag, input_fn=None, out=print, backend="ollama", search_fn=None, validate_fn=None,
           default_label=None, result=None):
    """Return the chosen tag. Bad input re-asks, up to 3 tries. After 3 bad tries the default is used and one line
    says so, naming it with `default_label`. `validate_fn(tag)` vets a typed tag or a numbered pick: None when it is
    fine, else the line to print that says why not (for example "not on the registry"). Without it every tag passes.
    The main list shows only the rows not marked hidden. "More downloads" and "Image and video models" open side
    lists; looking at those is never a bad try, and Enter in them goes back to the main list.
    Pass a dict as `result` to learn how it ended: result["how"] is "enter", "pick", "gave_up" or "eof"."""
    input_fn = input_fn or input  # looked up now, not at import, so a terminal or a test can swap it
    how = result if isinstance(result, dict) else {}
    how["how"] = "pick"
    fallback = default_tag or next((m["tag"] for m in menu if _is_pick(m) and not m.get("hidden")), None)
    tries = 0
    show = True
    while tries < 3:
        if show:
            for line in render(menu, default_tag, backend):
                out(line)
            show = False
        try:
            raw = input_fn("       > ").strip()
        except EOFError:  # input closed (piped, CI): same as Enter. Ctrl+C is NOT caught: the caller must stop.
            how["how"] = "eof"
            return fallback
        if not raw:
            how["how"] = "enter"
            return fallback
        if raw.lower() in YES_NO:  # "y" is a valid-looking tag, but nobody means it as one
            out(f"       That looks like a yes/no answer. Type a number, a model tag, or press Enter for {fallback}.")
            tries += 1
            continue
        if raw.isascii() and raw.isdigit():
            rows = _visible(menu)
            n = int(raw) if len(raw) <= MAX_PICK_DIGITS else 0  # int() refuses 4300+ digits; no menu is that long
            if 1 <= n <= len(rows):
                row = rows[n - 1]
                if row.get("hf"):
                    return _ask_hf_tag(input_fn, out, fallback, search_fn, validate_fn, default_tag, default_label)
                if row.get("more"):
                    picked = _more_pick(menu, input_fn, out, validate_fn)
                    if picked:
                        return picked
                    show = True
                    continue
                if row.get("media_row"):
                    _media_loop(row, menu, input_fn, out)
                    show = True
                    continue
                problem = validate_fn(row["tag"]) if validate_fn else None
                if problem is None:
                    return row["tag"]
                out(problem)
                tries += 1
                continue
            out(f"       Pick 1 to {len(rows)}, or type a tag.")
            tries += 1
            continue
        if TAG_RE.match(raw.lower()):
            problem = validate_fn(raw.lower()) if validate_fn else None
            if problem is None:
                return raw.lower()
            out(problem)
            tries += 1
            continue
        out("       That is not a tag. Use a number, or something like qwen3.6:27b.")
        tries += 1
    _gave_up(out, fallback, default_tag, default_label)
    how["how"] = "gave_up"
    return fallback


def tag_exists(tag, timeout=4):
    """True/False from the public Ollama registry, None when we cannot tell (offline). Sends only the tag."""
    name, _, version = _norm(tag).rpartition(":")
    if "/" in name and "." in name.split("/")[0]:
        return None  # another registry (hf.co/..., host.example/...): ours cannot vouch for it, so do not refuse it
    if "/" not in name:
        name = "library/" + name
    try:
        with http._open(f"https://registry.ollama.ai/v2/{name}/manifests/{version}", timeout=timeout,
                        method="HEAD", headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"},
                        opener=_REGISTRY_OPENER):
            return True
    except urllib.error.HTTPError as e:
        return False if e.code == 404 else None  # a refused cross-host redirect lands here as a 3xx: unknown
    except Exception:
        return None


def registry_reachable(timeout=3):
    """True when registry.ollama.ai answers at all (any HTTP reply, even a 401), False when we cannot reach it.
    Used by --check-upgrades to say "couldn't check" instead of guessing. Sends no model name."""
    try:
        with http._open("https://registry.ollama.ai/v2/", timeout=timeout, method="HEAD", opener=_REGISTRY_OPENER):
            return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False
