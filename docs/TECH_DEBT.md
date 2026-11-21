# Tech Debt Ledger

One row per open item, kept short on purpose. Each row says where the debt lives, which layer owns it
in the target design, and when we plan to clear it: "Fixes in" points at phases of the refactor
roadmap and nothing else. The machine-readable copy of today's boundary violations is the
`[lint.per-file-ignores]` baseline in `ruff.toml`; this page is the human one, so the two should
agree. Sizes are relative effort for one focused PR, and Evidence says how firm the number is.

| Where | What | Layer it belongs in | Fixes in | Size | Evidence |
|---|---|---|---|---|---|
| run.py (root) | 1,466 lines, 66 functions, 121 prints, 15 subprocess and 24 env sites; select_and_pull_model 114 lines, _main 109, _run_agent_session 100 | shell now; the parts move to app, core, platform | Phase 5 | L | tested |
| run.py shims | 34 "moved, shim" re-exports left in run.py after Phase 6d, pinned by the 164 patch.object(run, ...) targets; deleting them moves test lines, so it is one PR | per the Layer contract | Phase 6e | M | tested |
| Patch-target-only aliases | names kept in root modules only so tests can patch them, with no internal user: hardware.shutil and hardware.sys (10 sites), probe.tempfile (3), download_size._OPENER and download_size.time (5), model_wizard._HF_OPENER and _REGISTRY_OPENER (5). They alias the same module objects as the agl owner, so patching the root name reaches the owner's call | tests follow the code | Phase 6e | S | tested |
| model_wizard.py | 693 lines: catalog data, HTTP to Hugging Face and the Ollama registry, and interactive choose() in one file; the input_fn/out injection is a good seam, keep it | core (catalog, menu building) + platform (HTTP) + ui (choose) | Phases 3 and 4 | L | tested |
| memory.py | 826 lines: SQLite, embedding HTTP, subprocess and 52 prints together; search() is 129 lines | platform (state, HTTP, subprocess) + core (fusion and ranking) | Phase 6 | L | tested |
| Duplicate HTTP helpers | _get_json in download_size.py and ollama_models.py, _http_get in run.py, fetch_json in hf_search.py | platform (one helper, timeout required) | Phase 2 | M | tested |
| Duplicate hardware probes | get_hardware_profile and get_system_ram_gb live in both run.py and hardware.py | platform | Phase 2 | S | tested |
| Small duplicate names | render in handoff.py, model_wizard.py and task_report.py; summarize in handoff.py and task_report.py; _stamp in ledger.py and runlog.py | wherever the owner layer lands | Phases 3 to 6 | S | tested |
| Base URL literal | http://localhost:11434 typed 18 times across 8 product files (measured at c90a615) | platform (one base-URL default) | Phase 2 | S | tested |
| Picker bypass | code_agent.py, agent_with_workspace.py and test_local.py skip the model picker (one path since 6c; menu still skipped) | app (shared session entry) | Phase 6 | M | inferred (known open item) |
| Agent scripts vs the picker | owner call: route agent scripts through the picker (arena B) instead of the one resolve_model path in agl/app/agent_session.py (arena A, since 6c) | shell/app | Phase 6d | S | inferred |
| Site step lists | the 8 steps are defined 4 times (scene.js STEPS, main.js LAYER_SHORT, index.html stack list, game HOPS); scene.js is 846 lines with an if/else chain per layer; the game is one 1,498-line HTML file | site | Phase S | L | tested (counts) |
| Test seams | tests patch run.py internals: patch.object(run, ...) 116 sites over 24 names (PROJECT_DIR 15, is_in_venv 12, check_ollama_service 11); code moves need the targets re-pointed, Phase 1 amends R13 for that | tests follow the code | Phase 1 | M | tested |
| AGENTS.md stale line | says "no package.json"; site/package.json exists | docs (rule text, needs maintainer approval) | Phase 1 | S | tested |
| Today's boundary violations | the [lint.per-file-ignores] table in ruff.toml, generated at c90a615 (added in pass 2 of this PR) | per the Layer contract | Phases 2 to 6 | M | tested |
| Audit follow-ups | docs/audit-2026-11-18.md: no open High; its one Medium (the --model docs) was fixed by PR #66; its Lows and Proposed fix PRs stay there - link, do not re-audit | mixed | Phases 2 to 6 | S | tested |

Seed: ruff baseline at c90a615 plus the Phase 0 findings sweep, 2026-11-19.
