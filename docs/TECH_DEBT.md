# Tech Debt Ledger

Architecture plan complete: Phases 0 through 6e are closed.

One row per open item, kept short on purpose. Each row says where the debt lives, which layer owns it
in the target design, and when we plan to clear it: "Fixes in" points at phases of the refactor
roadmap and nothing else. The machine-readable copy of today's boundary violations is the
`[lint.per-file-ignores]` baseline in `ruff.toml`; this page is the human one, so the two should
agree. Sizes are relative effort for one focused PR, and Evidence says how firm the number is.

| Where | What | Layer it belongs in | Fixes in | Size | Evidence |
|---|---|---|---|---|---|
| run.py (root) | Closed in Phase 6e (run.py is a 199-line thin shell, black-clean at 100 columns, parts moved to app, core, platform, ui) | shell | Closed in Phase 6e | L | tested |
| run.py shims | Closed in the Phase 6e follow-up (every alias, tuple alias and forwarder deleted; tests/test_run_shell_shape.py fails if one returns) | per the Layer contract | Closed in Phase 6e | M | tested |
| Patch-target-only aliases | Closed in Phase 6e (23 aliases removed across hardware, probe, download_size, model_wizard; the follow-up removed run.py's ~40 tuple and lambda aliases) | tests follow the code | Closed in Phase 6e | S | tested |
| model_wizard.py | 401 lines (was 693). Still one file holding the catalog, HTTP, and choose(). The input_fn/out seam stays | core (catalog, menu building) + platform (HTTP) + ui (choose) | D3 | L | tested: wc -l model_wizard.py |
| memory.py | Closed in Phase 6e (5 shims removed, callers use agl.platform directly, timeout=60 on graphify) | platform + core | Closed in Phase 6e | L | tested |
| Duplicate HTTP helpers | Still open. download_size.py:53 _get_json, hf_search.py:52 fetch_json, and ollama_models.py:19 _get_json duplicate agl/platform/hub.py:217 fetch_json and agl/platform/ollama.py:88 _get_json. run.py _http_get is gone | platform (one helper, timeout required) | D3 | M | tested: grep -rn -E def _get_json, def fetch_json, def _http_get in *.py and agl |
| Duplicate hardware probes | Closed. The only definitions are agl/platform/hardware.py:18 get_system_ram_gb and agl/platform/hardware.py:54 get_hardware_profile. Matches in agl/core/ports.py and agl/app/ports.py are port methods | platform | Closed | S | tested: grep def get_hardware_profile or get_system_ram_gb in Python files, tests excluded |
| Small duplicate names | render in handoff.py, model_wizard.py and task_report.py; summarize in handoff.py and task_report.py; _stamp in ledger.py and runlog.py | wherever the owner layer lands | Phases 3 to 6 | S | tested |
| Base URL literal | 4 left in 3 non-test files (was 18 across 8): agl/platform/config.py, agl/app/server.py, agl/core/vscode_models.py | platform (one base-URL default) | D3 | S | tested: grep localhost:11434 in Python files, tests excluded |
| Picker bypass | code_agent.py, agent_with_workspace.py and test_local.py skip the model picker (one path since 6c; menu still skipped) | app (shared session entry) | Phase 6 | M | inferred (known open item) |
| Agent scripts vs the picker | owner call: route agent scripts through the picker (arena B) instead of the one resolve_model path in agl/app/agent_session.py (arena A, since 6c) | shell/app | Phase 6d | S | inferred |
| Site step lists | Closed in Phase S (#73). site/src/steps.js is the one source and site/scripts/check-steps.mjs fails on drift. The check said the 8 guide steps match | site | Closed | S | tested: node site/scripts/check-steps.mjs |
| Site file sizes | scene.js is 861 lines (was 846). site/public/game/index.html is 1498 lines | site | open | L | tested: wc -l site/src/scene.js site/public/game/index.html |
| Test seams | 31 lines under tests still name run.main, run._main, run._SETUP_ONLY, or run._run_shell (was 18). A search for patch("run.") finds 0. None of the 31 are run.PROJECT_DIR | tests follow the code | Phase 1 | S | tested: grep those run names under tests, then wc -l |
| AGENTS.md stale line | Closed. AGENTS.md line 4 now says the site has site/package.json | docs (rule text, needs maintainer approval) | Closed | S | tested: sed -n 4p AGENTS.md |
| Today's boundary violations | Closed in Phase 6e (ratcheted baseline to 16, run.py and memory.py removed from ruff.toml) | per the Layer contract | Closed in Phase 6e | M | tested |
| Audit follow-ups | docs/audit-2026-11-18.md: no open High; its one Medium (the --model docs) was fixed by PR #66; its Lows and Proposed fix PRs stay there - link, do not re-audit | mixed | Phases 2 to 6 | S | tested |

| check_test_moves whitelist | scripts/check_test_moves.py allows only import and patch-target removals; moving `run.X` test calls to the owner module (138 lines in the 6e follow-up, no assertion touched) is flagged | scripts/check_test_moves.py | open | S | tested |
| run.py eager memory import | run.py imports memory at startup so build_ports can pass memory.index_for_probe; it used to import lazily inside the index call | shell | open | S | tested |
| RealSigint test | win32-skipped on this machine; its stand_in now accepts the ports/out/input_fn kwargs, unverified until CI runs it on Linux | tests | CI | S | inferred |
| banner reaches agent_setup via sys.modules | agl/ui/banner.py:167 gets agent_setup with `sys.modules.get("agent_setup")`, not an import, so the layer rules cannot see that dependency (pre-existing) | app (pass it in as a port) | open | S | inferred |
| banner and launch reads can disagree | the stage 4 banner (agl/ui/banner.py:174) and setup_run (agl/app/agent_session.py:101) each read the Ollama window, so the number shown and the number written can differ if the model reloads between them | app | open | S | inferred |
| hardware probe on every read | agent_setup.py:196 live_window calls hardware.get_hardware_profile() each time with no cache, so every window read pays the GPU probe again | app | open | S | inferred |
| HANDOFF.md vs checkpoint overlap | HANDOFF.md (written at a rate limit or before a compaction) and .agl/checkpoint.md (plan, done, next) both carry hand-off state. Both stay for now, and the checkpoint pointer names HANDOFF.md as extra reading. Decide later whether one should feed the other | app | open | S | judgment |

Seed: ruff baseline at c90a615 plus the Phase 0 findings sweep, 2026-11-19. Architecture plan: all refactor roadmap phases (0 through 6e) are closed with the 6e follow-up; the open rows above are the leftovers.
