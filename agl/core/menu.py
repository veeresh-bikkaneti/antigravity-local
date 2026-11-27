"""The pure model-picker core: the catalog, tag shapes, fit and speed labels, and the menu build.

No network, no clock, no files (the Layer contract in docs/ARCHITECTURE.md puts this in core).
The HTTP functions and the interactive chooser stayed in model_wizard.py at the root;
Phase 4 injects them through agl.core.ports.
"""
import re

from agl.core import capabilities

# Re-check this list when you touch it: `curl -I https://registry.ollama.ai/v2/library/<name>/manifests/<tag>`
# must return 200, and sizes come from the manifest layers. Nothing here has been run through this
# project's agent loop yet, so the notes say what is reported, not what we measured.
# The list itself is CATALOG, just below.
CATALOG_VERIFIED = "2026-11-15"


# Sizes were read on each Ollama tag page: https://ollama.com/library/<model>/tags (checked 2026-11-15).
# Re-check this list when you touch it: `curl -I https://registry.ollama.ai/v2/library/<name>/manifests/<tag>`
# must return 200, and sizes come from the manifest layers. Nothing here has been run through this
# project's agent loop yet, so the notes say what is reported, not what we measured.
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

REPO_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*")  # used with fullmatch: one slash, no spaces or shell characters


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


def _badge_list(value):
    """Badges as a tuple of non-empty strings. A bare string is one badge (never split into letters); anything
    that is not a list or tuple, and any non-string item, counts as unknown and is dropped."""
    if isinstance(value, str):
        value = (value,)
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(b for b in value if isinstance(b, str) and b.strip())


def _note_text(value):
    """A note or hint as stripped text. Anything that is not a string, or is blank, becomes '.'."""
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
    menu = _installed_rows(tags, info, vram_gb, ram_gb, badges, backend)
    if backend == "openai":
        return menu
    if upgrade and _norm(upgrade["tag"]) not in have:
        menu.append(_upgrade_row(upgrade, vram_gb, ram_gb))
        have.add(_norm(upgrade["tag"]))
    if recommended and _norm(recommended) not in have:
        menu.append(_recommended_row(recommended, vram_gb, ram_gb, size_of))
        have.add(_norm(recommended))
    _catalog_rows(menu, have, catalog, vram_gb, ram_gb, size_of)
    _library_rows(menu, have, library, vram_gb, ram_gb, size_of)
    loader = _listed_media_rows(menu, have, media)
    _special_rows(menu, have, loader)
    return menu


def _installed_rows(tags, info, vram_gb, ram_gb, badges, backend):
    menu = []
    for m in tags:
        i = info.get(_norm(m)) or {}
        gb = i.get("size_gb") if isinstance(i.get("size_gb"), (int, float)) and i.get("size_gb") > 0 else None
        speed = (speed_label(gb, vram_gb, ram_gb, headroom=FIT_HEADROOM) or "Slow") if gb else None
        menu.append({"tag": m, "installed": True, "size_gb": gb, "size_source": "installed" if gb else None,
                     "fit": None, "speed": speed, "badges": _badges(m, badges),
                     "note": "already on this machine" if backend != "openai" else "loaded on your server",
                     "twin": _has_twin(m, tags, info)})
    return menu


def _upgrade_row(upgrade, vram_gb, ram_gb):
    return {"tag": upgrade["tag"], "installed": False, "size_gb": upgrade["gb"],
            "size_source": upgrade.get("label"), "fit": upgrade.get("fit"),
            "speed": speed_label(upgrade["gb"], vram_gb, ram_gb, headroom=FIT_HEADROOM),
            "badges": _badges(upgrade["tag"]), "note": "recommended upgrade"}


def _recommended_row(recommended, vram_gb, ram_gb, size_of):
    gb, src = _sized(recommended, None, size_of)
    return {
        "tag": recommended, "installed": False, "size_gb": gb, "size_source": src,
        "fit": fit_label(gb, vram_gb, ram_gb, headroom=FIT_HEADROOM) if gb else None,
        "speed": speed_label(gb, vram_gb, ram_gb, headroom=FIT_HEADROOM) if gb else None,
        "badges": _badges(recommended), "note": "recommended for this PC"}


def _catalog_rows(menu, have, catalog, vram_gb, ram_gb, size_of):
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


def _library_rows(menu, have, library, vram_gb, ram_gb, size_of):
    for row in library or []:
        if _norm(row["tag"]) not in have:
            have.add(_norm(row["tag"]))
            gb, src = _sized(row["tag"], None, size_of)
            menu.append({"tag": row["tag"], "installed": False, "size_gb": gb, "size_source": src,
                         "fit": fit_label(gb, vram_gb, ram_gb, headroom=FIT_HEADROOM) if gb else None,
                         "speed": speed_label(gb, vram_gb, ram_gb, headroom=FIT_HEADROOM) if gb else None,
                         "badges": _badge_list(row.get("badges")), "note": row.get("note", "from the Ollama library page"),
                         "hidden": True})


def _listed_media_rows(menu, have, media):
    loader = media if callable(media) else None  # a callable is asked only when the media row is picked
    for row in ([] if loader else media or []):
        if _norm(row["tag"]) in have:  # already listed (installed, catalog or library): one row per model
            continue
        have.add(_norm(row["tag"]))
        menu.append(_media_row(row))
    return loader


def _special_rows(menu, have, loader):
    """The 'More downloads' row when anything is hidden and plain, the media row, and the Hugging Face row."""
    if any(m.get("hidden") and not m.get("media") for m in menu):
        menu.append({"tag": MORE_ROW_TAG, "installed": False, "size_gb": None, "fit": None, "more": True})
    if loader or any(m.get("media") for m in menu):
        menu.append({"tag": MEDIA_ROW_TAG, "installed": False, "size_gb": None, "fit": None, "media_row": True,
                     "loader": loader, "known": sorted(have)})
    menu.append({"tag": HF_ROW_TAG, "installed": False, "size_gb": None, "fit": None, "hf": True,
                 "note": "A Hugging Face model (type hf.co/user/repo:quant)"})


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
            "badges": _badge_list(row.get("badges")), "note": _note_text(row.get("note")), "hint": _note_text(row.get("hint"))}


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
