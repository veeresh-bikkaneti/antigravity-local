"""Interactive pick menu, tag validation, and OpenAI model selector.

The ui layer: terminal text and prompts, with input/output injected.
Imports app and core only (no platform, no root modules).
"""
import os
import re
import sys

from agl.core import capabilities, menu, ranking

_SAFE_TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@+-]*$")


def printable_tag(tag) -> str:
    """A model name as it may be printed safely to the console."""
    text = str(tag)
    if _SAFE_TAG_RE.fullmatch(text):
        return f"'{text}'"
    return f"{repr(text)[:60]} (unsafe name, shown escaped)"


def find_candidate(name, pool, *, norm_fn=None):
    """The candidate for a tag. A short name also finds an hf.co model."""
    _norm = norm_fn or menu._norm
    want = _norm(name or "")
    for c in pool:
        have = _norm(c["tag"])
        if have == want or (have.startswith("hf.co/") and (have.rsplit("/", 1)[-1] == want or have[6:] == want)):
            return c
    return None


def ledger_warning(tag, entries, *, ports=None, out=print) -> None:
    """Warns, never refuses: a model that failed the probe can still be picked."""
    ledger_mod = getattr(ports, "ledger", None) if ports else None
    if ledger_mod and hasattr(ledger_mod, "status"):
        st = ledger_mod.status(tag, entries)
    else:
        lm = sys.modules.get("ledger")
        st = lm.status(tag, entries) if lm and hasattr(lm, "status") else None
    if st == "fail":
        hint = f" Check again with: python run.py --probe {tag}" if _SAFE_TAG_RE.fullmatch(str(tag)) else ""
        out(f"       Warning: {printable_tag(tag)} failed a tool-call probe on this PC, so it may not work as a coding agent."
            f"{hint}")


def refuse_non_chat(tag, pool, *, ports=None, out=print) -> bool:
    """True (after saying why) when a model cannot drive a coding agent: an embedding or media model."""
    norm_fn = getattr(getattr(ports, "model_wizard", None), "_norm", None) if ports else None
    cand = find_candidate(tag, pool, norm_fn=norm_fn)
    if cand and capabilities.resolve_kind(cand["kind"], cand["tag"]) in ("embedding", "media"):
        out(f"       {printable_tag(tag)} is an embedding or media model, so a coding agent cannot use it. Pick a chat model.")
        return True
    return False


def hf_tag_problem(tag, *, ports=None, out=print):
    """The reason a typed hf.co tag is clearly wrong, or None."""
    mw = getattr(ports, "model_wizard", None) if ports else None
    if mw and hasattr(mw, "hf_check"):
        status, detail = mw.hf_check(tag)
    else:
        mw_mod = sys.modules.get("model_wizard")
        if mw_mod and hasattr(mw_mod, "hf_check"):
            status, detail = mw_mod.hf_check(tag)
        else:
            status, detail = "ok", ()
    if status == "bad_tag":
        return f"       '{tag}' is not a Hugging Face tag. Use hf.co/{{username}}/{{repository}}:{{quantization}}."
    if status == "missing":
        return f"       '{tag}' was not found on Hugging Face (404). Check the user and repo name."
    if status == "no_quant":
        have = ", ".join(detail) if detail else "none (no .gguf files in that repo)"
        out(f"       Warning: no .gguf file in that repo matches the quant in '{tag}'. Quants it has: {have}.")
    return None


def hf_tag_ok(tag, *, ports=None, out=print) -> bool:
    """Vet a typed hf.co tag against the Hugging Face API."""
    problem = hf_tag_problem(tag, ports=ports, out=out)
    if problem:
        out(problem)
        return False
    return True


def typed_tag_problem(tag, installed_models, *, ports=None, out=print):
    """None when a tag can be pulled or used, else the line that says why not."""
    is_installed = getattr(ports, "is_model_installed", None) if ports else None
    if is_installed and is_installed(tag, installed_models):
        return None
    mw = getattr(ports, "model_wizard", None) if ports else None
    if mw is None:
        mw = sys.modules.get("model_wizard")
    is_hf = getattr(mw, "is_hf_tag", lambda t: str(t).startswith("hf.co/"))
    if is_hf(tag):
        return hf_tag_problem(tag, ports=ports, out=out)
    tag_exists = getattr(mw, "tag_exists", lambda t: True)
    if tag_exists(tag) is False:
        return f"       '{tag}' is not on the Ollama registry. Type another tag, or a number from the list."
    return None


def _resolve_default(pool, configured, installed_models, ports, norm_fn):
    """Determine the default model for the menu."""
    usable = ranking.agent_candidates(pool)
    best = ranking.best_for_agent(pool)
    is_inst = getattr(ports, "is_model_installed", lambda t, inst: t in inst)
    if configured and is_inst(configured, installed_models) and find_candidate(configured, usable, norm_fn=norm_fn):
        return configured, "current model"
    if best:
        return best["tag"], "current model"
    return None, "recommended pick"


def _build_menu_object(display_names, vram_gb, ram_gb, free_vram, free_ram, pool, scan_library, upgrade, installed_info, ports, norm_fn, tier, best):
    """Construct the interactive menu object from catalog, library, and installed models."""
    dl_size = getattr(ports, "download_size", None) or sys.modules.get("download_size")
    if dl_size and hasattr(dl_size, "new_lookup_window"):
        dl_size.new_lookup_window()
    size_of = getattr(dl_size, "resolve", lambda tag: None) if dl_size else (lambda tag: None)

    badges = {norm_fn(c["tag"]): c["badges"] for c in pool}
    get_lib = getattr(ports, "get_library_rows", lambda scan: [])
    get_med = getattr(ports, "get_media_rows", lambda: [])
    get_info = getattr(ports, "get_installed_info", lambda: {})
    info = get_info() if installed_info is None else installed_info

    mw = getattr(ports, "model_wizard", None) or sys.modules.get("model_wizard")
    build_menu = getattr(mw, "build_menu", menu.build_menu)
    return build_menu(
        display_names,
        vram_gb if free_vram is None else free_vram,
        ram_gb if free_ram is None else free_ram,
        recommended=None if best else tier,
        badges=badges,
        library=get_lib(scan_library),
        media=get_med,
        size_of=size_of,
        upgrade=upgrade,
        installed_info=info,
    )


def ask_which_model(display_names, installed_models, vram_gb, ram_gb, free_vram=None, free_ram=None, pool=None,
                    scan_library=False, upgrade=None, installed_info=None, *, ports=None, out=print):
    """Run the wizard. Returns the chosen tag, or None to keep the installed model."""
    env_get = ports.environ_get if (ports and hasattr(ports, "environ_get")) else os.environ.get
    configured = env_get("LOCAL_LLM_MODEL")
    if pool is None:
        inst_cands = getattr(ports, "_installed_candidates", None)
        pool = inst_cands(display_names, {}, {"vram_gb": vram_gb, "ram_gb": ram_gb}, []) if inst_cands else []
    mw = getattr(ports, "model_wizard", None) or sys.modules.get("model_wizard")
    norm_fn = getattr(mw, "_norm", menu._norm)
    best = ranking.best_for_agent(pool)
    hw_tier = getattr(ports, "hardware_tier_model", lambda v, r: None)
    tier = hw_tier(vram_gb, ram_gb)

    default, label = _resolve_default(pool, configured, installed_models, ports, norm_fn)
    if not default:
        default = tier

    menu_obj = _build_menu_object(
        display_names, vram_gb, ram_gb, free_vram, free_ram, pool,
        scan_library, upgrade, installed_info, ports, norm_fn, tier, best,
    )

    fv = vram_gb if free_vram is None else free_vram
    fr = ram_gb if free_ram is None else free_ram
    ended = {}
    hf_search = getattr(ports, "hf_menu_search_sized", lambda w, v, r: [])
    choose_fn = getattr(mw, "choose", None)
    if choose_fn:
        chosen = choose_fn(
            menu_obj,
            default,
            search_fn=lambda words: hf_search(words, fv, fr),
            validate_fn=lambda tag: typed_tag_problem(tag, installed_models, ports=ports, out=out),
            default_label=label,
            result=ended,
        )
    else:
        chosen = default

    if upgrade and ended.get("how") == "enter":
        rem = getattr(ports, "_remember_upgrade_stay", None)
        if rem:
            rem(upgrade["current"])

    is_inst = getattr(ports, "is_model_installed", lambda t, inst: t in inst)
    if not chosen or norm_fn(chosen) == norm_fn(default or ""):
        return None if chosen and is_inst(chosen, installed_models) else chosen
    return chosen


def select_openai_model(base_url, requested_model=None, interactive=False, *, ports=None, out=print):
    """Pick a model from an OpenAI-compatible server (LM Studio, llama.cpp, vLLM)."""
    st_fn = getattr(ports, "stage", None)
    if st_fn:
        st_fn(3, 5, "MODEL", "pick the model your server already has loaded")
    load_env_fn = getattr(ports, "_load_env", None)
    if load_env_fn:
        load_env_fn()
    list_models_fn = getattr(ports, "list_openai_models", None)
    ids = list_models_fn(base_url) if list_models_fn else []
    if not ids:
        out("       The server answered but lists no models. Load a model in your server, then re-run.")
        return None
    out(f"       Found {len(ids)} model(s) on the server: {', '.join(ids)}")
    by_name = {m.lower(): m for m in ids}
    if requested_model:
        chosen = by_name.get(requested_model.strip().lower())
        if not chosen:
            out(f"       '{requested_model}' is not loaded on this server. Load it there, or pick one it lists.")
            return None
    else:
        env_get = ports.environ_get if (ports and hasattr(ports, "environ_get")) else os.environ.get
        configured = (env_get("LOCAL_LLM_MODEL") or "").strip().lower()
        rank_key = getattr(ports, "capability_rank_key", str)
        default = by_name.get(configured) or max(ids, key=rank_key)
        chosen = default
        if interactive:
            mw = getattr(ports, "model_wizard", None) or sys.modules.get("model_wizard")
            menu_obj = mw.build_menu(ids, 0.0, 0.0, backend="openai")
            picked = mw.choose(menu_obj, default, backend="openai")
            chosen = by_name.get((picked or "").lower())
            if not chosen:
                out(f"       '{picked}' is not loaded on this server. Keeping '{default}'.")
                chosen = default
    out(f"       ✅ Using '{chosen}' from your server. Nothing to download.")
    update_fn = getattr(ports, "update_env_model", None)
    if update_fn:
        update_fn(chosen)
    return chosen
