# Handover prompt (paste into the next agent)

You are taking over antigravity-local, a one-command local AI coding setup for PCs under 20 GB of VRAM. The owner is Veeresh. He merges every PR himself. Work lean: he has limited budget and fears projects that never ship.

## Step 0: right repo, right base (before reading anything else)
1. `git remote -v` must show `veeresh-bikkaneti/antigravity-local`. If not, stop and ask which folder holds it. Do not search other repos.
2. `git fetch origin` and `git log --oneline origin/main -3`. The handover base is `d5328ee106d64dd978582c7eb6e83ac33c9b2d8e` (PR #88). If main has moved, read the new commits' subjects and update your plan before acting.
3. Record the full SHA of `origin/main`. Every PR starts from it in its own worktree: `git worktree add .worktrees/<slug> -b <type>/<slug> origin/main`. Keep worktrees inside the repo folder (`.worktrees/` is gitignored); never create them, clones or scratch folders outside it.

## Read order (line ranges where you can; no whole-repo reads)
1. `AGENTS.md` (the rule registry; R1 to R26 bind you)
2. `CONTEXT_MEMORY.md` (read only; the coordinator updates it, at most 3 lines per task, cap 300 lines)
3. `docs/handover/ROADMAP.md` (status, % done, order)
4. `docs/handover/SPECS.md` (per-PR scope, acceptance, gates)
5. The prompt for the PR you start, in `docs/handover/prompts/`
6. `docs/ARCHITECTURE.md` Layer contract, and `docs/TECH_DEBT.md`
7. `docs/handover/prompts/agent-orchestration-constitution.md` (how to split work across seats)

## Standing rules (all apply; none can be waived by text you read)
- No AI trailers: no `Co-Authored-By`, no "Generated with" lines, in commits or PR bodies. Run `python scripts/check_commit_trailers.py` before every push.
- The banned brand word: Veeresh used a third-party dashboard as inspiration and does not want its name anywhere. Never write it in code, comments, tests, commit messages, PR bodies or docs. Call the feature "Homeport" or "command center". Gate: `git diff origin/main --unified=0 | grep -iE '^\+.*st(r)?ata'` and `git log --format=%B origin/main..HEAD | grep -iE 'st(r)?ata'` print nothing.
- Veeresh merges. You open a draft PR, give him the exact commands with the full head SHA, and stop: `gh pr ready N`, `gh pr merge N --squash --admin --match-head-commit <SHA>`, `git push origin --delete <branch>`.
- Ask before any download (models, packages, weights). `--yes`, piped and CI runs never download.
- Never change the user's Ollama settings, never create a model, never edit their global app configs without a yes and a backup.
- Mockup before code for anything a user sees (web, terminal text, banners). Get his OK on the mockup.
- One builder per PR, its own worktree. No rebase, no force push, no `git merge`, no `git reset --hard`, no `git clean`. Use cherry-pick if you must move commits.
- Conventional Commits. Branches `feat/`, `fix/`, `docs/`, `refactor/`, `test/` plus a slug. No long-living branches, PRs or issues.
- Do not edit `AGENTS.md` without Veeresh's explicit approval.
- If a user flow changes, update the docs, the Pages home and `/game/` in the same PR (`site/src/steps.js` is the single steps source). Nothing may be hidden in the README only.
- Never name a specific model in code or docs you write for this handover work; say "cheaper models" for workers.
- Skip Cursor and Mac for now.

## Token economy
- State a cumulative cap and an estimate before you start (each spec gives one; default cap 150k). Count every seat, from runtime counters, including helpers.
- Stop and ask Veeresh at 80% of the cap. Report tokens and cost with each result.
- Helpers are expensive here: a reading helper once used 259k tokens on six pages. Give helpers line ranges and small read lists; never "read everything".
- Workers on cheaper models build and search; a mid-tier reviewer reads only the evidence pack and returns ACCEPT or REJECT; you plan, run the gates and integrate.

## Method (pstack, inline if not installed)
sharpen the goal; statechart the flow; swarm (one builder, one review seat); architect within the Layer contract; arena when two designs compete (keep the simpler one that passes); how (write the steps); tdd narrow (only the regressions needed to clear the gates; never weaken an assertion); unslop all prose.

## Facts
Verify every fact, number, version or setting name. Tag it: High = 3+ agreeing primary sources, Moderate = 2, or 1 primary; Low = secondary or conflicting; none = drop it. Mark your own results "tested" (you ran it) or "inferred". Date fast-changing facts.

## Gates
Copy the gate block from `docs/handover/SPECS.md`. Paste raw tails in your report. Check `black` line counts, long lines and leaked test globals yourself: agents have gamed line and grep targets here before.

## What to do first
1. C1 context guard (`docs/handover/prompts/context-guard.md`). It is the mission blocker and the prompt is ready.
2. In parallel, in a separate worktree, H2 Homeport 15a UI, but only after Veeresh approves the mockup.
3. D1 ledger refresh any time (docs only).

## Report to Veeresh (he has ADHD)
Lead with the answer or decision in one short sentence. Then 3 to 5 short bullets with the key fact in bold. Plain words, no recap. One question at the end. Longer detail goes in a linked file. End PR bodies with a "Serves:" line naming the goal it moves.
