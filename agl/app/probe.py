"""Probe and memory use cases (Phase 5b): live tool-call probe and memory indexing.

Nothing here writes directly to stdout: output goes through `out`.
Collaborators are injected through `ports`.
"""


def check_or_update_memory(*, ports, out):
    """Ensure the 3-Tier Memory Fabric (.memory/index.sqlite) is indexed and up to date."""
    try:
        stats = ports.index_memory()
        if stats and stats.get("indexed", 0) > 0:
            out(f"[*] Memory Fabric auto-indexed {stats['indexed']} updated files ({stats['chunks']} chunks).")
    except Exception as exc:
        out(f"Memory index skipped: {exc}")  # the run goes on without the index


def run_probe_command(args, *, ports, out):
    """`python run.py --probe [model]`: one live tool call, recorded in the local ledger. Returns the exit code.
    It runs before the venv step and never starts or pulls anything: it only talks to a server that is already up."""
    ports._load_env()
    base_api = ports.config.llm_base_url()
    backend = ports.detect_backend(base_api)
    if backend is None:
        out(f"❌ Nothing answered at {base_api}. Start your model server, then run --probe again.")
        return 1
    host = base_api.replace("/v1", "").rstrip("/")
    entries = ports.get_ledger_entries()
    model = args.model or ports.environ_get("LOCAL_LLM_MODEL")
    if not model and backend == "ollama":
        names = sorted(n for n in ports.get_installed_ollama_models(host) if ":" in n or "/" in n)
        best = ports.ranking.best_for_agent(
            ports._installed_candidates(names, ports.get_installed_details(host), ports.get_hardware_profile(), entries)
        )
        model = best["tag"] if best else None
    if not model:
        out("❌ No model to probe. Name one: python run.py --probe <model>")
        return 1
    out(f"🔬 Probing {ports._printable_tag(model)}: one live tool call (read a file, write a file)...")
    if ports.ledger.fresh_pass(model, entries):
        out("       It passed a few minutes ago, so we are not repeating it (a pass is trusted for 5 minutes).")
        return 0
    result = ports.probe.run_probe(base_api, model)
    ok, warning = ports.ledger.append(model, result["verdict"], result["reason"], runtime=backend, harness="probe")
    if result["verdict"] == "pass":
        out(f"       ✅ Passed: {result['reason']}.")
    else:
        out(f"       ❌ Failed: {result['reason']}.")
        out("          Models that fail are ranked below ones we have not tried, but you can still pick them.")
    if result["tok_s"] is not None:
        out(f"       slow on this PC ({result['tok_s']} tok/s)" if result["tok_s"] < 5 else f"       Speed: {result['tok_s']} tok/s")
    if not ok:
        out(f"       Warning: {warning}")
    return 0 if result["verdict"] == "pass" else 1
