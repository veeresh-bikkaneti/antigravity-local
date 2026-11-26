# antigravity-local roadmap and progress (handover, 2026-11-22)

Base: `main` at `d5328ee106d64dd978582c7eb6e83ac33c9b2d8e` (PR #88 merged). Every number below is tagged:
**tested** = a command was run on that SHA; **inferred** = read or estimated, not measured; **per doc** = taken from a planning doc, not re-checked.

## Overall: about 37% of the end goal is done (inferred)

| Workstream | Weight | Done | Weighted |
|---|---|---|---|
| 1. Architecture refactor (planned phases) | 25% | 100% of phases, leftover debt open | 25% |
| 2. Small-context fixes (the mission blocker) | 30% | about 5% (design and fact checks only, no code) | 1.5% |
| 3. Homeport command center | 30% | about 10% (backend half of slice 15a) | 3% |
| 4. Docs and site consistency | 15% | about 50% | 7.5% |
| **Total** | 100% | | **about 37%** |

Weights and percentages are inferred (judgment by scope size, not measured). The phase and PR counts under them are tested from `git log`.

## The goal (Veeresh's words, from channel notes)

- Mission: "local anti-gravity project is to help users with pc that have low specs... anything under 20 gigabytes of VRAM." Graphify, local memory and AI context exist so "they record where they left off, and the other cloud or on-prem models can take over and complete the project."
- The blocker: small-context forgetting "was the biggest bottleneck why Ulama out of the box does not help anybody."
- Tagline: "from zero to coding with 1 bootstrapped command and setup wizard". Zero to coding means no headaches from the bootstrap command, and no lock-in to a few models.
- End state: `run.py` does all logic; shared, always-current context so agents can switch; recommend the best upgrade; never re-pull; always give the choice; step-by-step wizard, readable logs, a game-style feel.
- Docs rule: "live github pages need to show all details; nothig should be hidden away in readme". Anyone following the Pages site does not need README.md.

## Workstream 1: architecture refactor and tech debt

All planned phases are merged (tested, `git log` on d5328ee). The repo now has layers `agl/{core,platform,app,ui}`, `run.py` is 199 lines (tested), and 1018 tests pass with 1 skipped and 3 expected failures (tested on Windows, 2026-11-26, `python -m unittest discover -s tests`, 240 s).

| Phase | PR | Merge SHA | Status |
|---|---|---|---|
| 0 guardrails (report-only) | #68 | 2cf760e | done |
| 1 AGENTS.md R13 and R26 | #70 | db16d68 | done |
| 2 agl package, one HTTP helper, arch check blocking | #71 | 139557b | done |
| 3 pure core into agl/core | #72 | 2655f46 | done |
| S site single steps source | #73 | 1387ad0 | done |
| 4a network adapters | #74 | c9d10f3 | done |
| 4b process, hardware, state adapters | #75 | a4e8067 | done |
| 5a pick-and-pull use case | #76 | add6ecd | done |
| 5b server check, agent session, probe to app | #77 | 097260d | done |
| 6a memory adapters | #79 | 710b5d3 | done |
| 6b memory search and index | #80 | 123f90a | done |
| 5c ui banners, pick menu | #82 | 2fe3c08 | done |
| 6c agents and handoff, one resolve_model | #83 | 54542ee | done |
| probe and serve debt split | #84 | eb7f871 | done |
| 6d lane A memory CLI | #85 | f1fc942 | done |
| 6d lane B shim removal | #87 | b6545b1 | done |
| 6e thin run.py shell, plan closed | #88 | d5328ee | done |

Phase names: the original plan doc called shim removal "6c", but the repo and the Homeport spec use 6c for agents and handoff, and 6d for shims. The table above follows the repo (tested from commit subjects).

### Leftover debt (from `docs/TECH_DEBT.md`, re-checked where noted)

| Item | Status | Evidence |
|---|---|---|
| model_wizard.py split (catalog, HTTP, choose) | open; now 401 lines, ledger still says 693 | tested (`wc -l`), ledger row stale |
| Duplicate HTTP helpers | open: `download_size.py`, `hf_search.py`, `ollama_models.py` still define their own | tested (grep `def _get_json\|def fetch_json`) |
| Duplicate hardware probes | likely closed: defs now only in `agl/platform/hardware.py` | tested (grep); ledger row stale |
| Base URL literal `localhost:11434` | 3 non-test files left (was 18) | tested (grep) |
| Small duplicate names (render, summarize, _stamp) | open | per doc |
| Picker bypass in code_agent.py, agent_with_workspace.py, test_local.py | open | inferred |
| Agent scripts vs picker (arena A vs B) | needs Veeresh's call | per doc |
| Site step lists | Phase S (#73) merged; ledger row not updated | inferred |
| Test seams naming `run` | ledger says 18 sites | per doc |
| AGENTS.md stale "no package.json" line | fixed in AGENTS.md text on d5328ee; ledger row not updated | tested (AGENTS.md line 4) |
| check_test_moves whitelist too strict | open | per doc |
| run.py eager memory import | open | per doc |
| RealSigint test only verified on Linux CI | open | inferred |

Done for workstream 1 means: every row above is closed or explicitly parked, and the ledger matches the code. A small "ledger refresh" PR fixes the stale rows first (see SPECS.md, D1).

## Workstream 2: small-context fixes (mission blocker)

Design doc: "Small-context audit and fix design" (claude.ai page, 2026-11-22). Audit on b6545b1 found (tested by that audit): pi gets a hardcoded 65536 `contextWindow`, Claude Code gets `CLAUDE_CODE_MAX_CONTEXT_TOKENS=65536` when the env is unset, opencode gets no limit, and there is no checkpoint or step code. Apps are told 64K while Ollama may load 4K to 8K, so they never trim.

| Step | Status | Prompt |
|---|---|---|
| Design and audit | done | design doc |
| Fact check: opencode, pi, Claude Code context settings | done (Veeresh's agent) | `prompts/context-facts-check.md` |
| Fact check: Copilot via Ollama extension | done (Veeresh's agent) | `prompts/copilot-facts-check.md` |
| C1 context guard (real window to every app, band warning, yes-gated Copilot entry) | pending, prompt ready | `prompts/context-guard.md` |
| C2 local relay trial (between Copilot and Ollama, trims to real window, writes checkpoint) | pending, Veeresh said yes | SPECS.md C2 |
| C3 checkpoint file `.agl/checkpoint.md` plus yes-gated pointers | pending | SPECS.md C3 |
| C4 step runner with sanity check and resume | pending | SPECS.md C4 |
| C5 memory and handoff rooted at the user's project, not this repo | pending | SPECS.md C5 |
| C6 Homeport shows real window and progress | pending, after H2 | SPECS.md C6 |

Done is about 5% (inferred: 3 of about 9 deliverables are planning, no code shipped). Acceptance for the whole stream: one 5-step task finishes at an 8K window (per doc).

## Workstream 3: Homeport command center

Spec: "Homeport command center: spec (PR 15)" (claude.ai doc, 2026-11-21). Mockup: Homeport mockup page (v10). Name: Homeport for the UI; logo Floating cursor; novice view low-poly island. Rules: bind 127.0.0.1 only, POST actions need a per-session token, one command engine for web and terminal, nothing downloads without a yes (per doc).

| Slice | Scope | Size (per doc, inferred) | Status |
|---|---|---|---|
| 15a backend | read-only readers, usage math, settings | 736 lines added | done, #86 `1478505` (tested `git show --shortstat`) |
| 15a UI (slice 2) | read-only web center plus terminal view | about 650 | pending, next |
| 15b | pass-through proxy, request log, timeline | about 450 | pending |
| 15c | lifecycle: start, stop, start at login | about 400 | pending |
| 15d | model actions (switch, unload, context, test, keep) | about 550 | pending |
| 15e | agents, memory, test prompt, logs, downloads | about 450 | pending |
| 9b | flexibility and observability: settings panel, history, slow-cause, export | about 400 spread over 15a/b/d | pending; mockup does not show it yet |

Done is about 10% (inferred: half of one of five slices). Known gap (inferred): the snapshot reads `used_tokens` but `/api/ps` has no such field, so `context_fill` is always None; fix it in H2.

Open decision (Veeresh): add the settings panel, history zoom and slow-cause explainer to the mockup before H2? Unanswered.

## Workstream 4: docs and site consistency

- Done: Phase S single steps source (#73); Pages renders README, Zero to coding and coding-apps guides (#59) (tested from git log).
- Pending: `ZERO_TO_CODING.md` line 31 pitches gemma2:27b with no coding-app warning (Gemma 2 has an 8K window [Moderate, per earlier check]); each user-flow change must update docs, the home page and `/game/` together (Veeresh's rule); Homeport and context-guard user docs once they ship.
- Done is about 50% (inferred).

## Later list (not scheduled)

Game scenes for "coding app" and "venv"; Ollama check before the venv switch; HANDOFF.md memory hits; live `--probe`; `--agent` stage 5 banner; demo "query missing" on 3B models; site sway ignores reduced-motion; phones show less of layers 4 to 8; issue 39 (needs two decisions from Veeresh); brag.mp4 re-record; Cursor support is skipped for now (his words: "skip cursor for now").

## Pending order and dependencies

```
D1 ledger refresh (docs only) ─┐
C1 context guard ──> C2 relay trial ──> C3 checkpoint file ──> C4 step runner ──> C5 project memory
                                                     │
H2 Homeport 15a UI ──> H3 15b ──> H4 15c ──> H5 15d ──> H6 15e
                         └──> C6 real window and progress in Homeport (needs C1 + H2)
D2 gemma2 warning and docs sync (any time)
D3 model_wizard split + HTTP helper dedupe (after C1, touches different files)
```

Do C1 first: it is the mission blocker and its prompt is ready. H2 can run beside C1 in its own worktree, because they touch different files (inferred; confirm with `git diff --stat` before starting).
