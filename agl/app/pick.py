"""The model pick use case (Phase 5a): pick a model, plan the download, ask the gate, check for upgrades.

Nothing here writes to the terminal or reads the keyboard by itself: text leaves only through the injected
`out` callable, the menu choice arrives through `ask`, the progress banner through `stage`, and every run.py
helper or root module through the one `ports` object.
"""
import re

try:
    import model_wizard
except ImportError:
    model_wizard = None

_SAFE_TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@+-]*$")


def _printable_tag(tag):
    """A model name as it may be printed. A safe name is quoted as-is. Anything else is escaped (repr, cut to 60
    characters) and marked unsafe, so a newline cannot forge a printed line and a shell character cannot sit in a
    copy-paste command."""
    text = str(tag)
    if _SAFE_TAG_RE.fullmatch(text):
        return f"'{text}'"
    return f"{repr(text)[:60]} (unsafe name, shown escaped)"


def _with_tag(name):
    """'qwen2.5-coder' -> 'qwen2.5-coder:latest' (Ollama's implicit tag). '' stays ''."""
    name = (name or "").strip().lower()
    return name if not name or ":" in name.split("/")[-1] else name + ":latest"


def is_model_installed(target_model, installed_models):
    """Exact match (an implicit ':latest' tag counts). No substring or bare-family matching."""
    target = _with_tag(target_model or "")
    if not target:
        return False
    installed = {_with_tag(m) for m in installed_models}
    return target in installed or target.split("/")[-1] in installed


def _free_for_fit(hw, res):
    """(free_vram, free_ram) to fit models against. An unknown GPU counts as 0 VRAM (fit on RAM only);
    unknown free RAM falls back to total RAM so we never fit against zero by accident."""
    vram = res["free_vram_gb"] if res.get("gpu_known") else 0.0
    ram = res.get("free_ram_gb") or hw.get("ram_gb") or 0.0
    return vram, ram


def _is_hf_short_alias(name, names, details):
    """True when `name` is only the short alias of a longer hf.co name (u/m:q4 for hf.co/u/m:q4). With details, a name
    the details know by its own key is kept, so two namespaces that share a short name are both candidates."""
    if details:
        return name not in details and any(k.endswith("/" + name) for k in details)
    return any(o != name and o.endswith("/" + name) for o in names)


def _catalog_size(tag, *, ports=None):
    """Download size in GB for a curated tag, or None."""
    mw = getattr(ports, "model_wizard", None) if ports else None
    if mw is None:
        import model_wizard
        mw = model_wizard
    want = mw._norm(tag)
    return next((size for t, size, _ in mw.CATALOG if mw._norm(t) == want), None)


def _find_candidate(name, pool, *, ports=None):
    """The candidate for a tag. A short name also finds an hf.co model (run.py lists that short alias),
    but never a model from any other namespace."""
    mw = getattr(ports, "model_wizard", None) if ports else None
    if mw is None:
        import model_wizard
        mw = model_wizard
    want = mw._norm(name or "")
    for c in pool:
        have = mw._norm(c.get("tag", ""))
        if have == want or (have.startswith("hf.co/") and have.rsplit("/", 1)[-1] == want):
            return c
    return None


def _best_installed(installed, *, ports=None):
    """Highest-scoring installed chat-style tag (embedding and namespaced junk ignored), or None."""
    names = [m for m in installed if ":" in m or "/" in m]
    if not names:
        return None
    score_fn = getattr(ports, "get_model_capability_score", None) if ports else None
    if score_fn is None:
        return max(names)
    return max(names, key=score_fn, default=None)


def _installed_candidates(names, details, hw, entries, *, ports=None):
    """One ranking candidate per installed model. Fit uses this PC's TOTAL memory, because a model that is loaded
    right now is already holding some of the free memory and must not look too big to itself."""
    names = [n for n in names if not _is_hf_short_alias(n, names, details)]  # drop hf.co short aliases
    vram, ram = hw.get("vram_gb") or 0.0, hw.get("ram_gb") or 0.0
    pool = []
    ollama_models = getattr(ports, "ollama_models", None) if ports else None
    ledger = getattr(ports, "ledger", None) if ports else None
    capabilities = getattr(ports, "capabilities", None) if ports else None
    model_wizard = getattr(ports, "model_wizard", None) if ports else None
    capability_rank_key = getattr(ports, "capability_rank_key", None) if ports else None
    if ollama_models is None:
        import ollama_models
    if ledger is None:
        import ledger
    if capabilities is None:
        import capabilities
    if model_wizard is None:
        import model_wizard
    for name in names:
        d = ollama_models.lookup(details, name)
        caps = d["caps"] if d else None
        status = ledger.status(name, entries)
        badges = capabilities.ollama_badges(caps)
        if status == "pass":
            badges = capabilities.confirm_tools(badges)
        size = d["size_gb"] if d else None
        fit_headroom = getattr(model_wizard, "FIT_HEADROOM", 0.1)
        name_score = capability_rank_key(name) if capability_rank_key else 0.0
        pool.append({
            "tag": name,
            "kind": capabilities.kind_from_ollama(caps),
            "fit": model_wizard.fit_label(size, vram, ram, headroom=fit_headroom) if size and (vram or ram) else None,
            "badges": badges,
            "installed": True,
            "ledger": status,
            "last_modified": d["modified_at"] if d else None,
            "downloads": None,
            "size_gb": size,
            "name_score": name_score,
        })
    return pool


def hf_menu_search(words=None, pipeline_tag="text-generation", limit=20, *, ports=None, out=None):
    """Hugging Face GGUF search for the menu. Cached 24 h; offline gives [] and one warning line for the whole run."""
    hf_search = getattr(ports, "hf_search", None) if ports else None
    userdata = getattr(ports, "userdata", None) if ports else None
    if hf_search is None:
        import hf_search
    if userdata is None:
        import userdata
    token = None
    if ports and hasattr(ports, "environ_get"):
        token = (ports.environ_get("HF_TOKEN") or "").strip() or None
    else:
        import os
        token = (os.environ.get("HF_TOKEN") or "").strip() or None
    rows, source = hf_search.search_models(userdata.data_dir() / "cache", query=words, pipeline_tag=pipeline_tag,
                                           limit=limit, token=token)
    pick_menu = getattr(ports, "pick_menu", None) if ports else None
    if pick_menu is None:
        import sys
        pick_menu = sys.modules.get("agl.ui.pick_menu")
    warn_out = out or getattr(ports, "out", None)
    if pick_menu and warn_out:
        if source == "offline":
            pick_menu._warn_once("hf", "Could not reach Hugging Face. Showing installed and curated models only.", out=warn_out)
        elif source == "stale":
            pick_menu._warn_once("hf", "Could not reach Hugging Face. Showing results saved earlier.", out=warn_out)
    return rows


def hf_menu_search_sized(words, free_vram, free_ram, limit=10, *, ports=None, out=None):
    """hf_menu_search, plus the size of the quant each of the first rows would pull (one Hub tree read per repo)."""
    download_size = getattr(ports, "download_size", None) if ports else None
    model_wizard = getattr(ports, "model_wizard", None) if ports else None
    if download_size is None:
        import download_size
    if model_wizard is None:
        import model_wizard
    download_size.new_lookup_window()
    search_fn = getattr(ports, "hf_menu_search", hf_menu_search) if ports else hf_menu_search
    try:
        rows = search_fn(words, ports=ports, out=out)
    except TypeError:
        rows = search_fn(words)
    sized = 0
    for r in rows:
        if sized >= limit:
            break
        if not model_wizard._is_repo_id(r.get("repo")):
            continue
        sized += 1
        user, repo = r["repo"].split("/", 1)
        info = download_size.hf_quant_size(user, repo, free_vram, free_ram)
        if info:
            r.update(size_gb=info["gb"], quant=info["quant"], size_source=info["source"])
    return rows


def get_media_rows(backend="ollama", *, ports=None, out=None):
    """Picture, video and sound models for their own menu section. Listed, never picked for an agent."""
    if backend != "ollama":
        return []
    import sys
    is_darwin = ports.sys.platform == "darwin" if (ports and hasattr(ports, "sys")) else sys.platform == "darwin"
    capabilities = getattr(ports, "capabilities", None) if ports else None
    if capabilities is None:
        import capabilities
    if is_darwin:
        return [{"tag": tag, "badges": (badge,), "note": note,
                 "hint": f'Run it yourself with: ollama run {tag} "your prompt"' + (" (the 9B Klein is non-commercial)" if nc else "")}
                for tag, badge, note, nc in capabilities.MEDIA_MODELS]
    rows = []
    search_fn = getattr(ports, "hf_menu_search", hf_menu_search)
    for pipeline in ("text-to-image", "text-to-video"):
        try:
            p_rows = search_fn(None, pipeline, 3, ports=ports, out=out)
        except TypeError:
            p_rows = search_fn(None, pipeline, 3)
        for r in p_rows[:3]:
            rows.append({"tag": "huggingface.co/" + r["repo"], "badges": r["badges"], "note": pipeline.replace("-", " "),
                         "hint": f"Needs a separate runtime (for example ComfyUI or diffusers); this tool does not run it. "
                                 f"https://huggingface.co/{r['repo']}"})
    return rows


def get_library_rows(scan=False, *, ports=None, out=None):
    """Extra models read off the Ollama library page. Only with --scan-library, because that page is read as HTML."""
    if not scan:
        return []
    ollama_library = getattr(ports, "ollama_library", None) if ports else None
    if ollama_library is None:
        import ollama_library
    rows = ollama_library.scan()
    pick_menu = getattr(ports, "pick_menu", None) if ports else None
    if not rows and pick_menu and out:
        pick_menu._warn_once("library", "Could not read the Ollama library page (--scan-library is fragile). Using the curated list.", out=out)
    return [{"tag": r["name"], "badges": r["badges"],
             "note": ("sizes " + ", ".join(r["sizes"]) + ": " if r["sizes"] else "") + r["note"]}
            for r in rows[:25]]


def offer_upgrade(installed, hw, free_vram, free_ram, now=None, *, ports=None):
    """Interactive runs only. Returns the best fitting upgrade as a menu row ({"tag", "gb", "label", "fit"}) plus
    "current" (the installed model it would replace), or None. It never prompts: the model menu shows the row as
    "recommended upgrade", so there is one list and one question. Enter on that menu is a stay, remembered by
    _remember_upgrade_stay for UPGRADE_STAY_SECONDS per model."""
    best_fn = getattr(ports, "_best_installed", None) if ports else None
    current = best_fn(installed) if best_fn else _best_installed(installed, ports=ports)
    if not current:
        return None  # nothing installed yet: the normal path already offers the hardware pick
    time_mod = getattr(ports, "time", None) if ports else None
    if time_mod is None:
        import time
        time_mod = time
    now = time_mod.time() if now is None else now
    upgrade_state_file = getattr(ports, "UPGRADE_STATE_FILE", None)
    if upgrade_state_file is None:
        project_dir = getattr(ports, "PROJECT_DIR", "")
        upgrade_state_file = getattr(ports, "path_join", lambda *a: "/".join(a))(project_dir, ".antigravity_upgrade_state.json")
    state = getattr(ports, "state", None) if ports else None
    stays = state.read_upgrade_state(upgrade_state_file).get("stay_until") if state else None
    stay_until = stays.get(current) if isinstance(stays, dict) else None
    if isinstance(stay_until, (int, float)) and stay_until > now:
        return None  # a recent "stay" on this model: no upgrade row for the rest of the week
    rows = _upgrade_candidates(installed, hw, free_vram, free_ram, ports=ports)
    if not rows:
        return None
    return dict(rows[0], current=current)


def _upgrade_candidates(installed, hw, free_vram, free_ram, *, ports):
    """Catalog picks plus the hardware tier pick that beat the best installed model and fit this PC right now.
    Each row: {'tag', 'gb', 'label' (where the size came from), 'note', 'fit'}. Report only: nothing is pulled."""
    best_fn = getattr(ports, "_best_installed", None) if ports else None
    best = best_fn(installed) if best_fn else _best_installed(installed, ports=ports)
    best_score = ports.get_model_capability_score(best) if (best and ports) else 0.0
    model_wizard = getattr(ports, "model_wizard", None) if ports else None
    if model_wizard is None:
        import model_wizard
    download_size = getattr(ports, "download_size", None) if ports else None
    if download_size is None:
        import download_size
    have = {model_wizard._norm(m) for m in installed}
    options = [(tag, size, note) for tag, size, note in model_wizard.CATALOG]
    tier = ports.hardware_tier_model(hw["vram_gb"], hw["ram_gb"]) if ports else None
    if tier and tier not in {t for t, _, _ in options}:
        options.append((tier, None, "the pick for this PC's hardware"))
    rows, seen = [], set()
    for tag, size, note in options:
        key = model_wizard._norm(tag)
        score = ports.get_model_capability_score(tag) if ports else 0.0
        if key in have or key in seen or score <= best_score:
            continue
        seen.add(key)
        info = download_size.resolve(tag, list_gb=size)
        if info and info.get("gb"):
            gb, label = float(info["gb"]), info["source"]
        elif size:
            gb, label = size, "catalog"
        else:
            continue
        headroom = getattr(model_wizard, "FIT_HEADROOM", 0.1)
        fit = model_wizard.fit_label(gb, free_vram, free_ram, headroom=headroom)
        if fit != "too big":
            rows.append({"tag": tag, "gb": gb, "label": label, "note": note, "fit": fit})
    return rows


def run_check_upgrades(base_url=None, *, ports, out):
    """`python run.py --check-upgrades`: one line per better model that fits this PC. Never pulls. Always returns 0."""
    ports._load_env()
    base_api = base_url or ports.config.llm_base_url()
    ollama_host = base_api.replace("/v1", "").rstrip("/")
    try:
        if not ports.model_wizard.registry_reachable():
            out("couldn't check: registry.ollama.ai did not answer, so there is no upgrade list. Nothing was changed.")
            return 0
        hw = ports.get_hardware_profile()
        free_vram, free_ram = getattr(ports, "_free_for_fit", _free_for_fit)(hw, ports.get_free_resources())
        installed = ports.get_installed_ollama_models(ollama_host)
        best = _best_installed(installed, ports=ports)
        out(f"Best installed model: {best or 'none'}")
        rows = _upgrade_candidates(installed, hw, free_vram, free_ram, ports=ports)
        if not rows:
            out("No upgrade found: nothing in the catalog beats your best installed model and fits this PC.")
        for r in rows:
            out(f"  {r['tag']}  {r['gb']:.1f} GB ({r['label']})  {r['note']}  [{ports.model_wizard.FIT_TEXT[r['fit']]}]")
        out("Report only. To pull one, run: python run.py <tag>")
    except Exception as exc:
        out(f"couldn't check: {exc}. Nothing was changed.")
    return 0


def _plan_download(tag, hw, res, *, ports, out):
    """Work out what pulling `tag` really means: final tag (with the quant we picked for a typed Hugging Face repo),
    size, licence, gated or not, disk numbers. Returns the plan for pull_gate.ask_pull, or None (with a reason printed)
    when it cannot fit or the quant the user typed does not exist."""
    text = tag or ""
    # ASCII only (the Kelvin sign lowercases to a plain k), no "..", and the usual tag shape.
    mw = getattr(ports, "model_wizard", None) or model_wizard
    if not text.isascii() or ".." in text or not mw.TAG_RE.fullmatch(text.lower()):
        out(f"       {tag!r} is not a model tag (ASCII letters, digits, . _ - / : only, and it cannot start with a dash).")
        return None
    free_vram, free_ram = _free_for_fit(hw, res)
    plan = {"tag": tag, "quant": None, "size_gb": None, "size_source": None, "license": None, "gated": False,
            "free_disk_gb": res["free_disk_gb"], "disk_total_gb": res["disk_total_gb"]}
    parsed = ports.model_wizard.parse_hf_tag(tag) if ports.model_wizard.is_hf_tag(tag) else None
    if not parsed:
        catalog_sz = getattr(ports, "_catalog_size", _catalog_size)(tag)
        info = ports.download_size.resolve(tag, catalog_sz)
        if info:
            plan.update(size_gb=info["gb"], size_source=info["source"])
        return plan
    user, repo, typed_quant = parsed
    if ports.model_wizard._STATE["offline"]:
        info = {"status": "unknown", "gated": False, "license": None}  # the Hub is down this run: do not ask again
    else:
        info = ports.model_wizard.hf_repo_info(user, repo)
    if info["status"] == "missing":
        out(f"       '{user}/{repo}' was not found on Hugging Face (404). Check the user and repo name.")
        return None
    plan["license"], plan["gated"] = info["license"], info["gated"]
    if plan["gated"]:
        return plan
    files = [] if ports.model_wizard._STATE["offline"] else ports.model_wizard.hf_tree_files(user, repo)
    if not files:
        out("       Could not read the file sizes from Hugging Face. Asking you with the tag as typed.")
        return plan
    pick = ports.quant_pick.pick_quant(files, free_vram, free_ram, wanted=typed_quant)
    if pick is None:
        if typed_quant:
            have = sorted({q for q in (ports.quant_pick.quant_of(f["name"]) for f in files) if q})
            out(f"       No {typed_quant.upper()} file in that repo. Quants it has: {', '.join(have) or 'none'}.")
        else:
            out(f"       No quant in {user}/{repo} fits {free_vram:.1f} GB free VRAM + {free_ram:.1f} GB free RAM. Try a smaller model.")
        return None
    if pick["fit"] == "too big":
        out(f"       {typed_quant.upper()} does not fit: {pick['why']}.")
        return None
    est = " (estimate)" if pick["estimated"] else ""
    out(f"       Quant picked: {pick['quant']}, {pick['size_gb']:.1f} GB{est}. {pick['why']}.")
    plan.update(tag=f"hf.co/{user}/{repo}:{pick['quant']}", quant=pick["quant"], size_gb=pick["size_gb"],
                size_source="estimate" if pick["estimated"] else "hugging face")
    return plan


def _pull_with_gate(tag, interactive, hw, res, *, ports, out):
    """The only way a model gets downloaded. Asks first, every time, whatever the size. Only a typed y pulls.
    --yes, piped input and CI never download: they print the exact command and return None."""
    plan_fn = getattr(ports, "_plan_download", None)
    if plan_fn is not None:
        try:
            plan = plan_fn(tag, hw, res, ports=ports, out=out)
        except TypeError:
            plan = plan_fn(tag, hw, res)
    else:
        plan = _plan_download(tag, hw, res, ports=ports, out=out)
    if plan is None:
        return None
    decision = ports.pull_gate.ask_pull(plan, interactive)
    if decision == "non_interactive":
        out(f"\n🛑 '{plan['tag']}' is not installed, and this run cannot ask you. Nothing was downloaded.")
        out(f"   To get it yourself: ollama pull {plan['tag']}\n")
        return None
    if decision == "yes":
        out(f"\n📥 Downloading '{plan['tag']}' via Ollama...")
        try:
            ports.process.check_call(["ollama", "pull", plan["tag"]])
        except Exception as exc:
            out(f"\n❌ Failed to pull model: {exc}")
            out(f"   You can manually pull it via: ollama pull {plan['tag']}\n")
            return None
        ports._FACTS["source"] = "pulled"
        out(f"✅ Model '{plan['tag']}' successfully pulled!\n")
        ports.update_env_model(plan["tag"])  # so the next run's menu default and --yes start from this pick
        return plan["tag"]
    if decision == "no":
        out("       Nothing downloaded.")
    return None


def _print_vitals(hw, res, free_vram, free_ram, *, out):
    """The detected PC build line and the free-resources line, said through `out`."""
    ram_gb = hw["ram_gb"]
    vram_gb = hw["vram_gb"]
    gpu_name = hw["gpu_name"]
    ram_txt = f"{ram_gb:.1f} GB RAM" if ram_gb else "RAM unknown"
    out(f"       Detected PC Build: {gpu_name} ({vram_gb:.1f} GB VRAM) | {ram_txt}")
    gpu_txt = f"{free_vram:.1f} GB VRAM free" if res.get("gpu_known") else "GPU unknown (fitting on RAM only)"
    out(f"       Free right now: {gpu_txt} | {free_ram:.1f} GB RAM free | {res['free_disk_gb']:.0f} GB disk free")


def _cli_pick(cli_requested_model, installed_models, pool, entries, from_menu, *, ports, out):
    """Decide the CLI-requested model: keep the installed one, refuse an impossible pick, or name the pull target."""
    if is_model_installed(cli_requested_model, installed_models):
        if ports._refuse_non_chat(cli_requested_model, pool):
            return ("refuse", None)
        ports._ledger_warning(cli_requested_model, entries)
        out(f"       ✅ Using explicitly requested model: '{cli_requested_model}' (Found locally. Skipping download!)")
        ports.update_env_model(cli_requested_model)
        return ("use", cli_requested_model)
    out(f"       User explicitly requested model '{cli_requested_model}' which is not in local inventory.")
    if not from_menu and ports.model_wizard.is_hf_tag(cli_requested_model) and not ports._hf_tag_ok(cli_requested_model):
        return ("refuse", None)
    return ("pull", cli_requested_model)


def _installed_pick(best, configured_env_model, installed_models, pool, entries, *, ports, out):
    """Reuse an installed model: the configured one if it can drive an agent, else the most capable one."""
    # Check if .env model is installed (and can drive a coding agent: an embedding model never can)
    if configured_env_model and is_model_installed(configured_env_model, installed_models):
        if _find_candidate(configured_env_model, ports.ranking.agent_candidates(pool), ports=ports):
            out(f"       ✅ Using configured local model: '{configured_env_model}' (Found locally. Zero download needed!)")
            ports._ledger_warning(configured_env_model, entries)
            return configured_env_model
        out(f"       '{configured_env_model}' (from .env) is an embedding or media model, which a coding agent cannot use. Choosing another.")
    # Rank the installed models: fits this PC, not failed, has tools, installed, probe passed, newer, name score last
    top_model = best["tag"]
    top_score = ports.get_model_capability_score(top_model)
    badge_text = ports.capabilities.format_badges(best["badges"])
    out(f"       🏆 Auto-selected MOST CAPABLE installed model: '{top_model}' (Capability Score: {top_score:.1f}/100"
        f"{'; ' + badge_text if badge_text else ''})")
    out("       ✅ Zero download needed—reusing existing local weights on this machine.")
    ports._ledger_warning(top_model, entries)
    ports.update_env_model(top_model)
    return top_model


def _tier_pick(display_names, vram_gb, ram_gb, *, ports, out):
    """Nothing usable is installed: read the hardware tier and say the cutting-edge pick for this build."""
    if display_names:
        out("       None of the installed models can drive a coding agent (embedding or media models only). "
            "Looking at the hardware pick instead...")
    else:
        out("       Zero models found on machine. Evaluating hardware build for optimal cutting-edge model...")
    target_to_pull = ports.hardware_tier_model(vram_gb, ram_gb)
    if target_to_pull == "qwen2.5-coder:14b":  # Workstation / Enthusiast PC
        out(f"       PC Build: High-performance workstation ({vram_gb:.1f}GB VRAM, {ram_gb:.1f}GB RAM)")
        out(f"       Selected cutting-edge agent model: '{target_to_pull}' (100% VRAM tool fit, flagship coding)")
        out("       (Note: You can also try 'deepseek-coder-v2:16b', 'command-r:35b', or 'codestral:22b')")
    elif target_to_pull == "qwen2.5-coder:7b":  # Mid-tier PC
        out(f"       PC Build: Mid-tier hardware ({vram_gb:.1f}GB VRAM, {ram_gb:.1f}GB RAM)")
        out(f"       Selected cutting-edge agent model: '{target_to_pull}'")
        out("       (Note: You can also try 'hf.co/mradermacher/nanbeige4.1-3b-gguf:q4_k_m', 'deepseek-coder:6.7b', or 'glm4:9b')")
    else:  # Entry-level / CPU
        out(f"       PC Build: Compact / CPU hardware ({ram_gb:.1f}GB RAM)")
        out(f"       Selected compact agent model: '{target_to_pull}'")
    return target_to_pull


def select_and_pull_model(base_url, requested_model=None, interactive=False, scan_library=False,
                          *, ports, out, ask, stage):
    """
    Engineering Best Practice:
    1. NEVER download if compatible models are already present on the machine!
    2. Check local Ollama inventory FIRST across all modern open-source models:
       (Nanbeige, DeepSeek, Qwen 2.5 Coder, Command-R, Codestral, GLM-4, LLaMA, Gemma).
    3. If multiple models exist locally, automatically rank and select the MOST CAPABLE one.
    4. Only if the machine has ZERO models installed, evaluate the PC build (RAM, GPU, VRAM)
       and recommend/pull the optimal cutting-edge model tailored to the hardware.
    """
    stage(3, 5, "MODEL", "match a model to this machine's memory")

    # Load .env if present
    ports._load_env()
    # Inspect hardware profile
    hw = ports.get_hardware_profile()
    res = ports.get_free_resources()
    ram_gb = hw["ram_gb"]
    vram_gb = hw["vram_gb"]
    free_vram, free_ram = getattr(ports, "_free_for_fit", _free_for_fit)(hw, res)
    _print_vitals(hw, res, free_vram, free_ram, out=out)
    # Check existing models locally FIRST
    installed_models = ports.get_installed_ollama_models(base_url)
    display_names = sorted(list(set(m for m in installed_models if ":" in m or "/" in m)))
    if display_names:
        out(f"       Found {len(display_names)} local model(s) in machine inventory: {', '.join(display_names)}")
    else:
        out("       No local models found in machine inventory.")
    details = ports.get_installed_details(base_url)
    entries = ports.get_ledger_entries()
    pool = _installed_candidates(display_names, details, hw, entries, ports=ports)
    best = ports.ranking.best_for_agent(pool)  # None when nothing installed can drive a coding agent
    # 1a. A better model that fits this PC (interactive only). It is a "recommended upgrade" row in the menu below,
    #     not a separate question, so there is one list and one prompt.
    upgrade = getattr(ports, "offer_upgrade", offer_upgrade)(installed_models, hw, free_vram, free_ram, ports=ports) if interactive and not requested_model else None
    cli_requested_model = requested_model  # 1. Did the user explicitly pass a model via CLI command-line?
    # 1b. On a real terminal, offer a short menu (installed + newer candidates) instead of silently auto-picking.
    #     Enter keeps the current pick. Piped runs, CI and --yes skip this, and they never download.
    from_menu = False
    if interactive and not cli_requested_model:
        cli_requested_model = ask(display_names, installed_models, vram_gb, ram_gb, free_vram, free_ram,
                                  pool=pool, scan_library=scan_library, upgrade=upgrade)
        from_menu = True  # the menu already vetted a typed tag

    if cli_requested_model:
        kind, value = _cli_pick(cli_requested_model, installed_models, pool, entries, from_menu, ports=ports, out=out)
        if kind != "pull":
            return value
        target_to_pull = value
    elif best:  # 2. ZERO-DOWNLOAD BEST PRACTICE: If models are already installed on this machine, REUSE THEM!
        return _installed_pick(best, ports.environ_get("LOCAL_LLM_MODEL"), installed_models, pool, entries,
                               ports=ports, out=out)
    else:  # 3. No models installed on machine at all: evaluate PC build and select optimal cutting-edge model
        target_to_pull = _tier_pick(display_names, vram_gb, ram_gb, ports=ports, out=out)
    # 4. Not installed: the gate asks first (and --yes, piped input and CI never download)
    out(f"\n📥 Model '{target_to_pull}' is not installed on this machine.")
    return _pull_with_gate(target_to_pull, interactive, hw, res, ports=ports, out=out)


def pick_model(args, base_api, ollama_host, backend, interactive, *, ports, out):
    """Check local inventory & auto-select or pull most capable model."""
    try:
        if backend == "openai":
            model = ports.pick_menu.select_openai_model(
                base_api, getattr(args, "model", None), interactive=interactive, ports=ports, out=out
            )
        else:
            model = select_and_pull_model(
                ollama_host,
                getattr(args, "model", None),
                interactive=interactive,
                scan_library=getattr(args, "scan_library", False),
                ports=ports,
                out=out,
                ask=lambda *a, **k: ports.pick_menu.ask_which_model(*a, ports=ports, out=out, **k),
                stage=ports.stage,
            )
    except KeyboardInterrupt:
        out("\nStopped with Ctrl+C. Nothing was saved. Run python run.py to start again.")
        ports.sys.exit(130)
    if not model:
        ports.sys.exit(1)
    return model
