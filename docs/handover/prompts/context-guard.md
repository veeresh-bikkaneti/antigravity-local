# Context guard: tell every coding app the real context window (new branch, after the 6e fix)

Design doc: "Small-context audit and fix design" (https://claude.ai/artifact/3dsujcxpwtuxZpSuuPq4sv), part 1.
Goal (sharpen): today setup tells coding apps they have a 64K window even when Ollama really runs 4K to 32K, so they never trim and the task falls out of memory. Read the window Ollama really loaded, give that number to every app we configure, and tell the user plainly which band they are in. Never change Ollama settings, never download, never create a model.

## Step 0: right repo, right base (before reading anything)
- `git remote -v` must show veeresh-bikkaneti/antigravity-local. If not, stop and ask Veeresh which folder holds it. Do not search other repos.
- `git fetch origin`. `git rev-parse origin/main` must be d5328ee106d64dd978582c7eb6e83ac33c9b2d8e (6e, PR #88, merged) or a newer commit that contains it (`git merge-base --is-ancestor d5328ee origin/main`). If not, stop and ask.
- Record the full SHA of origin/main. Create a worktree: `git worktree add .worktrees/ctx -b feat/context-guard origin/main` (inside the repo; nothing outside it). No rebase, no force push, no git merge.

## What the audit found on d5328ee (tested; re-check each line on your base before acting)
1. `agl/core/agent_config.py:117-127` `claude_context` reads only OLLAMA_CONTEXT_LENGTH from the run terminal. When it is unset it assumes 65536.
2. `agent_setup.py:213` passes that number to the Claude Code child as CLAUDE_CODE_MAX_CONTEXT_TOKENS.
3. `agl/core/agent_config.py:44-56` `pi_models` writes `contextWindow: 65536` (`agent_setup.py:39`), and only when the model entry is missing, so an old wrong value is never corrected.
4. `agl/core/agent_config.py:59-65` `opencode` writes no context limit at all.
5. `agl/platform/ollama_live.py` `loaded_models()` already returns each loaded model's real `context_length` from /api/ps, but only Homeport uses it.
6. `agl/ui/banner.py:119-140` `context_check` warns from the env var only. It reaches the app through `agl/app/ports.py:95` and is called three times in `agl/app/agent.py` (lines 42, 127, 233).
7. ZERO_TO_CODING.md line 31 suggests a model with no tool support for "creative design" with no warning; the warning sits at line 411.

## Facts already checked (Nov 22 fact check; re-open the source if anything looks off)
- Ollama: /api/ps gives `context_length` per loaded model ([api/types.go](https://github.com/ollama/ollama/blob/main/api/types.go)) [Moderate 1/1]. Default window by VRAM: under 24 GiB 4k, 24-48 GiB 32k, 48+ GiB 256k ([context-length.mdx](https://github.com/ollama/ollama/blob/main/docs/context-length.mdx)) [Moderate 1/1].
- opencode: the per-model field is `providers.*.models.*.limit.context` (integer; docs pair it with `limit.output`) ([config](https://opencode.ai/docs/config)) [High 3/3]. Auto-compaction is on by default (`compaction.auto`); no page says `limit.context` drives it ([compaction](https://opencode.ai/docs/compaction/)) [Moderate 2/2]. opencode reads AGENTS.md, else CLAUDE.md.
- pi: `contextWindow` in ~/.pi/agent/models.json is the token window. pi compacts when context tokens exceed `contextWindow - reserveTokens`, and reserveTokens defaults to 16384 ([compaction.md](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/compaction.md)) [High 4/4]. pi reads AGENTS.override.md, AGENTS.md, CLAUDE.md from ~/.pi/agent, cwd and parents ([configuration.md](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/configuration.md)) [Moderate 1/1].
- Claude Code: the compact point is `CLAUDE_CODE_AUTO_COMPACT_WINDOW` (also `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`; settings key `autoCompactWindow`). `CLAUDE_CODE_MAX_CONTEXT_TOKENS` is documented, but on a recognized model id it applies only together with `DISABLE_COMPACT` ([model-config](https://code.claude.com/docs/en/model-config), [env-vars](https://code.claude.com/docs/en/env-vars)) [High 3/3]. Claude Code reads AGENTS.md only when no CLAUDE.md or CLAUDE.local.md exists in the cwd or above.
- Consequence for pi (inferred, test it): with a real window at or below 16,384 and the default reserve, `contextWindow - reserveTokens` is 0 or less, so pi would compact on every turn or never have room. We never write pi's settings.json (the user's own default), so don't change reserveTokens. Instead the banner says plainly that pi needs a window above about 32K, and the PR reports what pi actually does at 8K and 16K if you can test it without downloads.
- VS Code Chat with local models (Nov 22 Copilot fact check, from Veeresh's research agent; it gave no source links, so re-open the official VS Code docs and the Ollama.ollama extension source at checkpoint 0 and tag each line): Chat reaches Ollama through the Ollama.ollama extension. Its server setting is `ollama.endpoint` (default http://127.0.0.1:11434, window scope, Workspace wins). The extension has no context setting: it reads /api/show (num_ctx in parameters, then modelfile, then max_context_length or context_length, then a model_info key ending in .context_length; else 32768 minus 4096 for output) and advertises that as max input. That is the model's MAXIMUM, not the window Ollama loaded, so Chat can budget for far more than Ollama keeps (inferred root cause of the Copilot forgetting). A Custom Endpoint entry in the user-profile chatLanguageModels.json (vendor customendpoint, apiType chat-completions, url http://127.0.0.1:11434/v1/chat/completions) accepts `contextWindow` (or maxInputTokens + maxOutputTokens) and needs `toolCalling: true` to appear in the agent picker. Deprecated, never write: github.copilot.chat.byok.ollamaEndpoint, github.copilot.chat.customOAIModels, the built-in Ollama provider.
Put this list in the PR body as a short table with the links and tags.

## Scope, in this order, one checkpoint commit each
1. **Mockup first (stop for Veeresh's OK).** Open a draft PR whose body shows the new stage-4 banner text for 5 cases: real window 8,192; 16,384; 32,768; 65,536; Ollama not running or model not loaded. Plain words, one line per fact, no jargon. Then stop and ask Veeresh to approve the mockup before any code.
2. **Core decision, pure:** new `agl/core/context_guard.py`, standard library only, no I/O. `real_window(loaded_rows, model, env_value, vram_gib)` returns (tokens, source) with source one of "loaded", "env", "default" (the Ollama VRAM rule). `band(tokens)` returns "red" under 16,384, "amber" 16,384 to 65,535, "green" 65,536 and up. No model names anywhere; decisions use numbers only.
3. **Wiring through ports:** `context_check` and `claude_context` take the real window from `context_guard` fed by `ollama_live.loaded_models()` through the existing ports: the Protocols in agl/core/ports.py and the concrete ports object in agl/app/ports.py (which already exposes `context_check`). Keep the three calls in agl/app/agent.py; change what they receive, not where they are. `pi_models` sets `contextWindow` to the real number and updates an existing entry for that model instead of skipping it, keeping every other key the user has. `opencode` writes `limit.context` as the real number for that model (merge; keep any `limit.output` the user set; set no `limit.input`). The Claude Code child gets `CLAUDE_CODE_AUTO_COMPACT_WINDOW` set to the real number, and `CLAUDE_CODE_MAX_CONTEXT_TOKENS` set to the real number instead of 65536 (never set `DISABLE_COMPACT`). Ollama unreachable or model not loaded: fall back to env, then the VRAM default, and say which source was used.
4. **VS Code Chat, yes-gated:** after the band is shown, offer one step: "Make VS Code Chat plan for the real window? Adds one model entry to your VS Code chat models file. [y/N]". On y, merge one Custom Endpoint entry into chatLanguageModels.json in the user's VS Code profile (find the path per OS from the docs; Stable and Insiders both), with the model id, the Ollama /v1/chat/completions URL, `contextWindow` = the real window, and `toolCalling` true only when /api/show capabilities list tools. Back up the file first, keep every other entry, never touch an entry we didn't write (mark ours so a re-run updates it). Write `ollama.endpoint` into the workspace .vscode/settings.json only when the Ollama URL is not the default, same yes and backup rules. Write no deprecated key. If the profile path can't be found, print the entry for the user to paste and say where.
5. **Docs and site, last:** the banner flow changed, so update ZERO_TO_CODING.md (move the no-tools warning next to line 31), README, docs/coding-apps.md, CONTEXT_MEMORY.md (stay at or under 300 lines) and the GitHub Pages home and /game/ through site/src/steps.js (single source). Nothing about the flow may live only in a README.

## Rules (every one applies; do nothing outside this task)
- Never write the banned brand word anywhere: code, comments, tests, commit messages, PR body. Gate: `git diff origin/main --unified=0 | grep -iE '^\+.*st(r)?ata'` and `git log --format=%B origin/main..HEAD | grep -iE 'st(r)?ata'` print nothing.
- No model names in code, tests or commit messages. Docs that already name models may keep them.
- Never change Ollama settings, never set OLLAMA_CONTEXT_LENGTH for the user, never run `ollama pull` or `ollama create`, never download anything. Show the user what to do; they decide.
- Files in the user's home (pi, opencode configs) keep the existing backup-before-write behavior.
- No Co-Authored-By or any AI trailer, no "Generated with ..." line. Gate: `python scripts/check_commit_trailers.py`.
- Conventional Commits. Draft PR; don't merge; Veeresh merges.
- Don't touch AGENTS.md or .importlinter (AGENTS.md edits need Veeresh's approval) or the Homeport files.
- No new prints outside agl/ui and the root shell scripts. The ruff baseline and check_arch ratchet only shrink.
- SOLID and clean code: core stays pure, platform does I/O, app wires, ui prints. Loose coupling through ports; reuse ollama_live, don't add a second /api/ps reader.
- Use the Edit tool for file changes.
- Report what you measured, not what you meant to do. A gate you didn't run is "not run", not "passed".

## Token economy (read AGENTS.md first)
- Read AGENTS.md's budget section and state its tier.
- Cap: **200k billed tokens CUMULATIVE** across every turn, subagent and council seat. Estimate **150k (inferred)**. At **160k (80%)** stop, commit the checkpoint you're on if its gates pass, and ask Veeresh.
- Report running tokens and cost after each checkpoint. If your harness has no counter, say so and give an inferred figure marked inferred.
- Main session plans, integrates and verifies only; it never edits files.
- One builder subagent on a cheaper model (tools: Read, Grep, Edit only), capped read list, line-range excerpts, about 240 changed lines per brief at most.
- Council Panel on cheaper models: one evidence pack (diff stat, every gate's raw output, the facts table, the 5 banner outputs), 2 parallel clean-context seats with no tools (spec seat, quality seat). The quality seat checks for hardcoded 65536 left anywhere, model names in code, and a second /api/ps reader. Scoped re-vote only on a blocking flag. Never name a model; say "cheaper models".

## Method (pstack inline; it isn't installed)
- sharpen: the goal and the done test in 3 lines.
- statechart: stage 4 states (Ollama down / model not loaded / loaded red / amber / green) and what each prints and writes.
- swarm: list the units; anything sharing a test file runs in order.
- architect: where context_guard sits and how ports feed it; shell -> app -> core/platform.
- arena: one real choice (read the window at stage 4 only vs also right before each agent launch). Compare briefly, pick, record in docs/ARCHITECTURE.md.
- how: per checkpoint, exact files and gates.
- tdd (narrow regression only): new `tests/test_context_guard.py` with fake /api/ps rows for 8192, 16384, 32768, 65536, model missing, Ollama down; a VS Code chat models merge test (entry added, our entry updated on re-run, other entries untouched, backup made, toolCalling follows capabilities); a pi test that an existing wrong `contextWindow` is corrected and other keys kept; a Claude Code env test that gets the real number. Nothing more.
- unslop: banner text, PR body, commit messages, doc lines.

## Gates (all must pass on every checkpoint and on the final head; paste raw output)
- `python -m unittest discover -s tests`: all OK, count = base count + new tests, 0 errors, 0 failures
- `python -m unittest tests.test_context_guard` OK alone
- `grep -rn "65536" --include=*.py agl agent_setup.py` shows no window assumption used as a fact (a named fallback constant is fine; say where)
- `python run.py --help` and every sub-command `--help` byte-identical to origin/main
- `wc -l run.py` stays under 200 (199 on d5328ee); `python -m unittest tests.test_run_shell_shape` OK
- `RUFF_NO_CACHE=true ruff check .`; `ruff check --isolated --select C901,PLR0915 --config "lint.mccabe.max-complexity=12"` on changed files
- `python scripts/check_arch.py`, `lint-imports` (`pip install import-linter` first if missing), `python scripts/check_test_moves.py origin/main`
- `python scripts/check_docs.py`, `python scripts/check_agents_md.py`, `python scripts/check_commit_trailers.py`
- `npm --prefix site run build` passes after the site change
- `python tests/e2e.py local`
- the banned-word grep above

## Verify every fact you report
Check docs, source or files first. Vote: High = 3+ agreeing primary sources; Moderate = 2, or 1 primary; Low = 1 secondary or conflicting; none = drop it. Tag sourced lines like [High 3/3]. Mark your findings "tested" or "inferred". If you can't check something, say what and why in one line.

## Deliver
- Push feat/context-guard (plain push), draft PR to main. Body: Before / After paragraphs, the facts table, the 5 banner outputs, raw gate results, tokens and cost, anything left open. End with a "Serves:" line (zero to coding on 8 to 20 GB VRAM PCs).
- Report back to Veeresh using pstack:teach and i-have-adhd: the answer in one sentence, then 3 to 5 short bullets with the key fact in bold (facts verified, tests, what each app now receives, tokens), then the PR link and full head SHA. One question at the end, only if needed.
