"""The model pick use case (Phase 5a): pick a model, plan the download, ask the gate, check for upgrades.

Nothing here writes to the terminal or reads the keyboard by itself: text leaves only through the injected
`out` callable, the menu choice arrives through `ask`, the progress banner through `stage`, and every run.py
helper or root module through the one `ports` object.
"""


def _upgrade_candidates(installed, hw, free_vram, free_ram, *, ports):
    """Catalog picks plus the hardware tier pick that beat the best installed model and fit this PC right now.
    Each row: {'tag', 'gb', 'label' (where the size came from), 'note', 'fit'}. Report only: nothing is pulled."""
    best = ports._best_installed(installed)
    best_score = ports.get_model_capability_score(best) if best else 0.0
    have = {ports.model_wizard._norm(m) for m in installed}
    options = [(tag, size, note) for tag, size, note in ports.model_wizard.CATALOG]
    tier = ports.hardware_tier_model(hw["vram_gb"], hw["ram_gb"])
    if tier not in {t for t, _, _ in options}:
        options.append((tier, None, "the pick for this PC's hardware"))
    rows, seen = [], set()
    for tag, size, note in options:
        key = ports.model_wizard._norm(tag)
        if key in have or key in seen or ports.get_model_capability_score(tag) <= best_score:
            continue
        seen.add(key)
        info = ports.download_size.resolve(tag, list_gb=size)
        if info and info.get("gb"):
            gb, label = float(info["gb"]), info["source"]
        elif size:
            gb, label = size, "catalog"
        else:
            continue
        fit = ports.model_wizard.fit_label(gb, free_vram, free_ram, headroom=ports.model_wizard.FIT_HEADROOM)
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
        free_vram, free_ram = ports._free_for_fit(hw, ports.get_free_resources())
        installed = ports.get_installed_ollama_models(ollama_host)
        best = ports._best_installed(installed)
        out(f"Best installed model: {best or 'none'}")
        rows = ports._upgrade_candidates(installed, hw, free_vram, free_ram)
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
    if not text.isascii() or ".." in text or not ports.model_wizard.TAG_RE.fullmatch(text.lower()):
        out(f"       {tag!r} is not a model tag (ASCII letters, digits, . _ - / : only, and it cannot start with a dash).")
        return None
    free_vram, free_ram = ports._free_for_fit(hw, res)
    plan = {"tag": tag, "quant": None, "size_gb": None, "size_source": None, "license": None, "gated": False,
            "free_disk_gb": res["free_disk_gb"], "disk_total_gb": res["disk_total_gb"]}
    parsed = ports.model_wizard.parse_hf_tag(tag) if ports.model_wizard.is_hf_tag(tag) else None
    if not parsed:
        info = ports.download_size.resolve(tag, ports._catalog_size(tag))
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
    plan = ports._plan_download(tag, hw, res)
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
    if ports.is_model_installed(cli_requested_model, installed_models):
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
    if configured_env_model and ports.is_model_installed(configured_env_model, installed_models):
        if ports._find_candidate(configured_env_model, ports.ranking.agent_candidates(pool)):
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
        out(f"       (Note: You can also try 'deepseek-coder-v2:16b', 'command-r:35b', or 'codestral:22b')")
    elif target_to_pull == "qwen2.5-coder:7b":  # Mid-tier PC
        out(f"       PC Build: Mid-tier hardware ({vram_gb:.1f}GB VRAM, {ram_gb:.1f}GB RAM)")
        out(f"       Selected cutting-edge agent model: '{target_to_pull}'")
        out(f"       (Note: You can also try 'hf.co/mradermacher/nanbeige4.1-3b-gguf:q4_k_m', 'deepseek-coder:6.7b', or 'glm4:9b')")
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
    free_vram, free_ram = ports._free_for_fit(hw, res)
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
    pool = ports._installed_candidates(display_names, details, hw, entries)
    best = ports.ranking.best_for_agent(pool)  # None when nothing installed can drive a coding agent
    # 1a. A better model that fits this PC (interactive only). It is a "recommended upgrade" row in the menu below,
    #     not a separate question, so there is one list and one prompt.
    upgrade = ports.offer_upgrade(installed_models, hw, free_vram, free_ram) if interactive and not requested_model else None
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
    return ports._pull_with_gate(target_to_pull, interactive, hw, res)
