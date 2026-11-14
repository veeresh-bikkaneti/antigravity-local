"""Pick a local model with a short menu instead of silently taking the first one. Standard library only.

Why this exists: run.py used to grab whatever was already installed and call it "most capable".
Models move fast, so we show what is installed plus a short list of newer candidates, say what fits
this machine, and let the human choose. Enter keeps the current pick, so it costs one keypress.
"""
import re
import urllib.request

# Re-check this list when you touch it: `curl -I https://registry.ollama.ai/v2/library/<name>/manifests/<tag>`
# must return 200, and sizes come from the manifest layers. Nothing here has been run through this
# project's agent loop yet, so the notes say what is reported, not what we measured.
CATALOG_VERIFIED = "2026-11-14"
CATALOG = [
    # (tag, size_gb, note)
    ("devstral-small-2:24b", 15.2, "Built for agentic coding and multi-file edits (Mistral)"),
    ("gpt-oss:20b", 13.8, "OpenAI open-weight model, native tool calling"),
    ("qwen3.6:27b", 17.8, "Qwen3 line with native tool calling, the established pick"),
    ("qwen3.8:27b", 17.7, "Newest Qwen; strongest reported coding, but tool calling is new and unproven"),
    ("qwen3-coder:30b", 18.6, "Coding-tuned mixture-of-experts, fast for its size"),
    ("laguna-xs.2:latest", 23.1, "Long-horizon agent model; reported by third-party guides only"),
]


TAG_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]*(:[a-z0-9._-]+)?$")


def _norm(tag):
    tag = tag.strip().lower()
    return tag if ":" in tag.split("/")[-1] else tag + ":latest"


def fit_label(size_gb, vram_gb, ram_gb):
    """'gpu' if it should sit in VRAM with room for context, 'split' if it spills to RAM, else 'too big'."""
    if size_gb <= vram_gb * 0.9:
        return "gpu"
    if size_gb <= vram_gb + ram_gb * 0.7:
        return "split"
    return "too big"


FIT_TEXT = {"gpu": "fits your GPU", "split": "runs, part on CPU (slower)", "too big": "too big for this PC"}


def build_menu(installed, vram_gb, ram_gb, catalog=CATALOG, recommended=None):
    """Installed models first (no download), then the hardware pick if given, then catalog models that can run here.

    `recommended` is the tier pick for this PC (run.hardware_tier_model). Its size is not known without a
    registry call, so the row says so instead of guessing.
    """
    have = {_norm(m) for m in installed}
    menu = [{"tag": m, "installed": True, "size_gb": None, "fit": None, "note": "already on this machine"}
            for m in sorted(installed)]
    if recommended and _norm(recommended) not in have:
        menu.append({"tag": recommended, "installed": False, "size_gb": None, "fit": None,
                     "note": "recommended for this PC"})
        have.add(_norm(recommended))
    for tag, size, note in catalog:
        if _norm(tag) in have:
            continue
        fit = fit_label(size, vram_gb, ram_gb)
        if fit == "too big":
            continue
        menu.append({"tag": tag, "installed": False, "size_gb": size, "fit": fit, "note": note})
    return menu


def render(menu, default_tag):
    lines = [f"       Pick a model (list checked {CATALOG_VERIFIED}; not yet run through this project's agent loop):"]
    for i, m in enumerate(menu, 1):
        star = "*" if _norm(m["tag"]) == _norm(default_tag or "") else " "
        if m["installed"]:
            detail = "installed, no download"
        else:
            size = f"{m['size_gb']:.1f} GB download" if m["size_gb"] is not None else "size unknown"
            detail = size + (f", {FIT_TEXT[m['fit']]}" if m["fit"] else "")
        lines.append(f"       {star}{i:>2}. {m['tag']}  [{detail}]  {m['note']}")
    keep = (f"Enter keeps {default_tag}" if default_tag
            else "Enter picks 1" if menu else "Enter continues with the automatic pick")
    lines.append(f"       Type a number, or any other Ollama tag. {keep}. (* = current)")
    return lines


def choose(menu, default_tag, input_fn=None, out=print):
    """Return the chosen tag. Bad input re-asks up to 3 times, then falls back to the default."""
    input_fn = input_fn or input  # looked up now, not at import, so a terminal or a test can swap it
    fallback = default_tag or (menu[0]["tag"] if menu else None)
    for line in render(menu, default_tag):
        out(line)
    for _ in range(3):
        try:
            raw = input_fn("       > ").strip()
        except (EOFError, KeyboardInterrupt):
            return fallback
        if not raw:
            return fallback
        if raw.isdigit():
            n = int(raw)
            if 1 <= n <= len(menu):
                return menu[n - 1]["tag"]
            out(f"       Pick 1 to {len(menu)}, or type a tag.")
            continue
        if TAG_RE.match(raw.lower()):
            return raw.lower()
        out("       That is not a tag. Use a number, or something like qwen3.6:27b.")
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
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except urllib.error.HTTPError as e:
        return False if e.code == 404 else None
    except Exception:
        return None
