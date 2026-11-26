# Specs for each pending PR

Base for every PR: fresh `origin/main` (at handover, `d5328ee106d64dd978582c7eb6e83ac33c9b2d8e`). One PR per spec, one builder, its own worktree, draft PR, Veeresh merges.
Prompts in `docs/handover/prompts/` were written against `b6545b1`; their Step 0 asks for "#88 merged on top of b6545b1", which is now true. Re-check every `path:line` they cite on your base before acting.

## Gates for every PR (paste raw tails in the report)

```
python -m unittest discover -s tests
python scripts/check_arch.py            # needs: pip install ruff import-linter
python scripts/check_docs.py
python scripts/check_agents_md.py
python scripts/check_commit_trailers.py
python scripts/check_test_moves.py origin/main
ruff check --isolated --select C901,PLR0915 --config "lint.mccabe.max-complexity=12" <changed .py files>
black --check -l 100 <changed .py files>
git diff origin/main --unified=0 | grep -iE '^\+.*st(r)?ata'      # must print nothing
git log --format=%B origin/main..HEAD | grep -iE 'st(r)?ata|co-authored-by|generated with'   # must print nothing
```
Touching `serve.py`, `Dockerfile` or run scripts also needs `python tests/e2e.py local` and `python tests/e2e.py docker` (AGENTS.md R12).

---

## D1 ledger refresh (docs only, small)
- Scope: update `docs/TECH_DEBT.md` rows found stale in ROADMAP.md (model_wizard size, hardware probes, site step lists, AGENTS.md package.json line, base URL count).
- Files: `docs/TECH_DEBT.md` only.
- Accept: every changed row cites the command that proves it; `check_docs.py` green.
- Cap 30k, estimate 15k (inferred).

## C1 context guard (mission blocker, do first)
- Prompt: `docs/handover/prompts/context-guard.md` (cap 200k, estimate 150k there).
- Scope: read the window Ollama really loaded (`/api/ps` `context_length`, `/api/show` for the model max); write that number to opencode `limit.context`, pi `contextWindow`, Claude Code `CLAUDE_CODE_AUTO_COMPACT_WINDOW`; band warning (<16K, 16K-63K, 64K+); pi needs about 32K+ because it reserves 16384 [High, per fact check]; yes-gated step writes a VS Code `chatLanguageModels.json` entry with `contextWindow` = real window.
- Files (inferred): `agl/core/agent_config.py`, `agent_setup.py`, `agl/platform/ollama_live.py`, `agl/ui/banner.py`, new tests.
- Accept: no setup path ever writes 65536 unless Ollama reports it; nothing changes Ollama settings, downloads, or creates a model; Claude Code note goes into both CLAUDE.md and AGENTS.md pointers only on yes (Claude Code skips AGENTS.md when CLAUDE.md exists [High, per fact check]).

## C2 local relay trial
- Scope: a localhost relay between Copilot (or any OpenAI-style client) and Ollama that trims history to the real window and writes the checkpoint after each answer. Trial behind a flag, off by default.
- Files (inferred): `agl/app/relay.py`, `agl/platform/http.py` reuse, `agl/core/` trim math, tests with fakes.
- Accept: bind 127.0.0.1 only; a fake 8K window never receives a prompt over 8K tokens (estimated); stop cleanly on Ctrl+C; no change to the user's Ollama settings.
- Cap 150k, estimate 100k (inferred). Needs a mockup of the banner text first.

## C3 checkpoint file and pointers
- Scope: `.agl/checkpoint.md` in the user's project (plan, done, next, files), capped near 1,500 tokens (per doc); yes-gated pointer blocks in `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`, `.continue/rules`.
- Accept: pointers are written only on yes, with a backup; file stays under the cap; re-running is idempotent.
- Cap 120k, estimate 80k (inferred).

## C4 step runner with sanity check and resume
- Scope: chunk a big task into steps, update the checkpoint each step, run a sanity check before "done", resume from the checkpoint after a crash or a model switch. Idea source: Veeresh cites a todo-style tool in another CLI.
- Accept: test with fakes at 8K and 32K windows; a killed run resumes at the next step; the 5-step task finishes at 8K (stream acceptance).
- Cap 150k, estimate 110k (inferred).

## C5 project-rooted memory and handoff
- Scope: `memory.py` indexes the user's project root, not this repo (today `REPO_ROOT` is antigravity-local itself, tested by the audit); HANDOFF.md for apps beyond Claude Code; Graphify call gets a timeout.
- Accept: index root is the project passed in; no file outside it is read.
- Cap 150k, estimate 100k (inferred).

## C6 Homeport shows real window and progress (after C1 and H2)
- Scope: Homeport tiles show the real loaded window, the band, and checkpoint progress.
- Cap 80k, estimate 50k (inferred).

## H2 Homeport 15a UI (read-only web center plus terminal view)
- Template: `docs/handover/prompts/homeport-slice-1-backend.md` (same rules, new scope). Spec and mockup: the Homeport spec doc and mockup page (links in the channel notes; ask Veeresh if you can't open them).
- Scope: read-only web page and terminal view over the slice 1 readers (`agl/app/homeport.py`, `agl/core/usage.py`, `agl/platform/ollama_live.py`, `gpu.py`, `homeport_store.py`); fixed default port, scan only if taken; island novice view with plain-words captions, raw numbers below; prefers-reduced-motion stops animation.
- Fix: `context_fill` is always None because `/api/ps` has no `used_tokens` (inferred); compute fill from the last request's prompt tokens, or show "unknown".
- Accept: bind 127.0.0.1; no POST routes in this slice; terminal fits 118 columns; mockup approved by Veeresh before code.
- Cap 150k, estimate 110k (inferred). Never write the banned brand word; the product name is Homeport.

## H3 to H6 Homeport 15b to 15e
- 15b pass-through, request log, timeline (about 450 lines); 15c lifecycle start, stop, start at login (about 400); 15d model actions with confirms, switch lists pulled models only, downloads behind a yes with size (about 550); 15e agents, memory, test prompt, logs, downloads (about 450). Sizes per spec, inferred.
- Every POST needs a per-session token; unload and switch ask first if a reply is in progress.
- Write one prompt per slice from the H2 prompt once H2 merges.

## D2 docs sync and gemma2 warning
- Scope: `ZERO_TO_CODING.md` line 31 warning that gemma2 is not for coding apps; keep README, the Pages home and `/game/` consistent (`site/src/steps.js` is the single steps source).
- Accept: `check_docs.py` green; the Pages build shows the same steps as the docs.

## D3 model_wizard split and HTTP helper dedupe
- Scope: split `model_wizard.py` into core (catalog, menu), platform (HTTP), ui (choose), keeping the `input_fn`/`out` seam; replace the private HTTP helpers in `download_size.py`, `hf_search.py`, `ollama_models.py` with `agl/platform/http.py`; remove the last 3 `localhost:11434` literals.
- Accept: golden tests unchanged; arch baseline only shrinks.
- Cap 150k, estimate 100k (inferred); max about 240 moved lines per PR, so split in two if bigger.
