"""Pick a local model with a short menu instead of silently taking the first one. Standard library only.

Why this exists: run.py used to grab whatever was already installed and call it "most capable".
Models move fast, so we show what is installed plus a short list of newer candidates, say what fits
this machine, and let the human choose. Enter keeps the current pick, so it costs one keypress.
"""
import json
import re
import urllib.error
import urllib.request

import capabilities

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


FIT_TEXT = {"gpu": "fits your GPU", "split": "runs, part on CPU (slow)", "too big": "too big for this PC"}


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


class _SameHostOnly(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only when it stays on the host we asked. Anything else is an error, not a new host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        from urllib.parse import urlsplit
        if urlsplit(newurl).netloc != urlsplit(req.full_url).netloc:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_HF_OPENER = urllib.request.build_opener(_SameHostOnly)
_REGISTRY_OPENER = urllib.request.build_opener(_SameHostOnly)  # registry.ollama.ai: a cross-host redirect is not followed
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
               badges=None, library=None, media=None, size_of=None, upgrade=None):
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
    """
    have = {_norm(m) for m in installed}
    menu = [{"tag": m, "installed": True, "size_gb": None, "fit": None, "badges": _badges(m, badges),
             "note": "already on this machine" if backend != "openai" else "loaded on your server"}
            for m in sorted(installed)]
    if backend == "openai":
        return menu
    if upgrade and _norm(upgrade["tag"]) not in have:
        menu.append({"tag": upgrade["tag"], "installed": False, "size_gb": upgrade["gb"],
                     "size_source": upgrade.get("label"), "fit": upgrade.get("fit"),
                     "badges": _badges(upgrade["tag"]), "note": "recommended upgrade"})
        have.add(_norm(upgrade["tag"]))
    if recommended and _norm(recommended) not in have:
        gb, src = _sized(recommended, None, size_of)
        menu.append({"tag": recommended, "installed": False, "size_gb": gb, "size_source": src,
                     "fit": fit_label(gb, vram_gb, ram_gb, headroom=FIT_HEADROOM) if gb else None,
                     "badges": _badges(recommended), "note": "recommended for this PC"})
        have.add(_norm(recommended))
    for tag, size, note in catalog:
        if _norm(tag) in have:
            continue
        gb, src = _sized(tag, size, size_of)
        fit = fit_label(gb, vram_gb, ram_gb, headroom=FIT_HEADROOM) if gb else None
        if fit == "too big":
            continue
        menu.append({"tag": tag, "installed": False, "size_gb": gb, "size_source": src, "fit": fit,
                     "badges": _badges(tag), "note": note})
        have.add(_norm(tag))
    for row in library or []:
        if _norm(row["tag"]) not in have:
            have.add(_norm(row["tag"]))
            gb, src = _sized(row["tag"], None, size_of)
            menu.append({"tag": row["tag"], "installed": False, "size_gb": gb, "size_source": src,
                         "fit": fit_label(gb, vram_gb, ram_gb, headroom=FIT_HEADROOM) if gb else None,
                         "badges": _badge_list(row.get("badges")), "note": row.get("note", "from the Ollama library page")})
    for row in media or []:
        if _norm(row["tag"]) in have:  # already listed (installed, catalog or library): one row per model
            continue
        have.add(_norm(row["tag"]))
        menu.append({"tag": row["tag"], "installed": False, "size_gb": None, "fit": None, "media": True,
                     "badges": _badge_list(row.get("badges")), "note": _text(row.get("note")), "hint": _text(row.get("hint"))})
    menu.append({"tag": HF_ROW_TAG, "installed": False, "size_gb": None, "fit": None, "hf": True,
                 "note": "Hugging Face model (type hf.co/user/repo:quant)"})
    return menu


def render(menu, default_tag, backend="ollama"):
    lines = [f"       Pick a model (list checked {CATALOG_VERIFIED}; not yet run through this project's agent loop):"]
    seen_media = False
    for i, m in enumerate(menu, 1):
        star = "*" if _norm(m["tag"]) == _norm(default_tag or "") else " "
        if m.get("media"):
            if not seen_media:
                seen_media = True
                lines.append("       Media models (for pictures, video or sound: not coding agents, never picked automatically):")
            badge_text = f"  ({capabilities.format_badges(m.get('badges'))})" if m.get("badges") else ""
            lines.append(f"       {star}{i:>2}. {m['tag']}  [media]{badge_text}  {m['note']}")
            continue
        if m.get("hf"):
            lines.append(f"       {star}{i:>2}. {m['note']}")
            continue
        if m["installed"]:
            detail = "loaded, no download" if backend == "openai" else "installed, no download"
        else:
            if m["size_gb"] is None:
                size = "size unknown"
            elif m.get("size_source") == "estimate":
                size = f"~{m['size_gb']:.1f} GB download (estimate)"
            else:
                size = f"{m['size_gb']:.1f} GB download"
            detail = size + (f", {FIT_TEXT[m['fit']]}" if m["fit"] else "")
        badge_text = f"  ({capabilities.format_badges(m.get('badges'))})" if m.get("badges") else ""
        lines.append(f"       {star}{i:>2}. {m['tag']}  [{detail}]{badge_text}  {m['note']}")
    keep = (f"Enter keeps {default_tag}" if default_tag
            else "Enter picks 1" if menu else "Enter continues with the automatic pick")
    what = "a model id your server lists" if backend == "openai" else "any other Ollama tag"
    lines.append(f"       Type a number, or {what}. {keep}. (* = current)")
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


def choose(menu, default_tag, input_fn=None, out=print, backend="ollama", search_fn=None, validate_fn=None,
           default_label=None, result=None):
    """Return the chosen tag. Bad input re-asks, up to 3 tries. After 3 bad tries the default is used and one line
    says so, naming it with `default_label`. `validate_fn(tag)` vets a typed tag or a numbered pick: None when it is
    fine, else the line to print that says why not (for example "not on the registry"). Without it every tag passes.
    Pass a dict as `result` to learn how it ended: result["how"] is "enter", "pick", "gave_up" or "eof"."""
    input_fn = input_fn or input  # looked up now, not at import, so a terminal or a test can swap it
    how = result if isinstance(result, dict) else {}
    how["how"] = "pick"
    fallback = default_tag or next((m["tag"] for m in menu if not m.get("hf") and not m.get("media")), None)
    for line in render(menu, default_tag, backend):
        out(line)
    for _ in range(3):
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
            continue
        if raw.isascii() and raw.isdigit():
            n = int(raw) if len(raw) <= MAX_PICK_DIGITS else 0  # int() refuses 4300+ digits; no menu is that long
            if 1 <= n <= len(menu):
                if menu[n - 1].get("hf"):
                    return _ask_hf_tag(input_fn, out, fallback, search_fn, validate_fn, default_tag, default_label)
                if menu[n - 1].get("media"):  # never a pick: say how to run it, then ask again
                    out(f"       {menu[n - 1].get('hint') or 'Media models are not used by coding agents.'}")
                    continue
                problem = validate_fn(menu[n - 1]["tag"]) if validate_fn else None
                if problem is None:
                    return menu[n - 1]["tag"]
                out(problem)
                continue
            out(f"       Pick 1 to {len(menu)}, or type a tag.")
            continue
        if TAG_RE.match(raw.lower()):
            problem = validate_fn(raw.lower()) if validate_fn else None
            if problem is None:
                return raw.lower()
            out(problem)
            continue
        out("       That is not a tag. Use a number, or something like qwen3.6:27b.")
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
    req = urllib.request.Request(
        f"https://registry.ollama.ai/v2/{name}/manifests/{version}", method="HEAD",
        headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"})
    try:
        with _REGISTRY_OPENER.open(req, timeout=timeout):
            return True
    except urllib.error.HTTPError as e:
        return False if e.code == 404 else None  # a refused cross-host redirect lands here as a 3xx: unknown
    except Exception:
        return None


def registry_reachable(timeout=3):
    """True when registry.ollama.ai answers at all (any HTTP reply, even a 401), False when we cannot reach it.
    Used by --check-upgrades to say "couldn't check" instead of guessing. Sends no model name."""
    req = urllib.request.Request("https://registry.ollama.ai/v2/", method="HEAD")
    try:
        with _REGISTRY_OPENER.open(req, timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False
