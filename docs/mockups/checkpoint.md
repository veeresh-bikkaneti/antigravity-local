# Checkpoint file and pointers (mockup)

This is a design mockup for C3 in `docs/handover/SPECS.md`. No code exists yet. Everything here is proposed text, so the real wording can change once the code is written.

The idea is simple. Coding apps forget things when the window fills up or when you switch models. A small file in the project, `.agl/checkpoint.md`, holds the plan, what is done, what is next, and which files were touched. Every app reads it first and updates it before it stops. A yes-gated pointer block in each app's instruction file tells the app to do that.

## 1. Checkpoint template

This is the file the app writes into `.agl/checkpoint.md`. The shape matches the HANDOFF.md renderer in `agl/core/handoff.py`: a title, a marker comment, a written line, then sections.

```markdown
# Checkpoint

<!-- agl-checkpoint v1 -->
updated: 2026-11-26T10:00:00+00:00 (example value)

## Plan

- The goal in one or two lines, in the user's own words.
- The steps, in order, as short checkboxes.

## Done

- [x] Step that is finished, with the commit or file that proves it.

## Next

- [ ] The one step to start with when the app wakes up.

## Files

- `path/to/file.py`: what changed and why, in one line.

## Notes

- Open questions for the user.
- Gotchas the next session must not repeat.
```

Rules for the template:

- The `updated:` line is the first thing a reader checks. The app rewrites it every time it saves.
- The marker comment is how we know we wrote the file. A file without the marker was not ours.
- The file must stay under about 1,500 tokens. That number is a target taken from the C3 spec (`docs/handover/SPECS.md`, "capped near 1,500 tokens"). It is inferred, NOT measured. Nothing has counted a real file yet.
- When the app is over the cap, it trims `Done` to one line per step first. It never drops `Next`.

## 2. Pointer block

The pointer block goes into each app instruction file. It sits between two marker comments, so a re-run replaces only our block and leaves the rest of the file alone.

```markdown
<!-- agl-checkpoint:begin -->
Before you start, read `.agl/checkpoint.md`. It holds the plan, what is done, and what is next.
Before you stop, update it: plan, done, next, files, notes, and the `updated:` line.
Keep it under about 1,500 tokens. If `HANDOFF.md` exists, read it too for extra context.
Do not merge HANDOFF.md into the checkpoint and do not rename it.
<!-- agl-checkpoint:end -->
```

Rules for the pointer block:

- The chosen app's file is always written: `AGENTS.md` for pi, opencode and codex, `CLAUDE.md` for Claude Code. If it is missing, the same yes creates it.
- `.github/copilot-instructions.md` and `.continue/rules/` get a pointer only when they already exist. In `.continue/rules/` the block goes in `agl-checkpoint.md`.
- A write happens only after a yes. A backup of each existing file is made first, the same way `agent_files` backs up config files.
- A re-run finds the begin and end markers and replaces only what is between them. If only one marker is found, we stop and ask. We never guess.
- The block names HANDOFF.md as extra reading. It never merges or renames it.

## 3. Stage 4 terminal text (proposed)

This is proposed text for `python run.py --agent pi`. It works like the VS Code offer in
`agl/app/vscode_chat.py`. Only a typed yes writes anything. Anything else counts as no,
and so does the end of input. The lines use the same 7-space indent as the other stage 4 lines.

### 3a. First offer

```text
       Checkpoint: a short file your coding app reads first and updates before it stops.
       It keeps the plan, what is done, what is next, and the files you touched.
       File     : C:\projects\my-app\.agl\checkpoint.md
       Pointers : AGENTS.md (missing, will be created)
                  .github\copilot-instructions.md, .continue\rules\ (found)
       Add a pointer block for each. We back up each existing file first.
       The same yes also adds .agl/ to the project's .gitignore.
       Add the checkpoint file and the pointers? [y/N]
```

### 3b. Everything already in place

```text
       Checkpoint: already in place. Nothing to do.
       File     : C:\projects\my-app\.agl\checkpoint.md (up to date)
       Pointers : AGENTS.md, .github\copilot-instructions.md, .continue\rules\ (all current)
```

### 3c. User says no

```text
       Add the checkpoint file and the pointers? [y/N] n
       Not changed. Nothing was written, and .gitignore is untouched. Run this again any time.
```

Notes on the text:

- Every line in this section is 100 columns or fewer.
- The Copilot and Continue pointers are listed only when found.
- The paths are examples. Real output uses the user's own project folder.

## 4. Fact table

Each row says which file an app reads at start, where we read that, and how many independent sources agree. The rows follow the spec list in `docs/handover/SPECS.md` (C3).

| App | Instruction file it reads at start | Source link | Vote tag | Notes |
|---|---|---|---|---|
| opencode | AGENTS.md. Falls back to CLAUDE.md when a directory has no AGENTS.md | [opencode instructions](https://opencode.ai/docs/instructions/) | Moderate 1/1 primary | Page says: "In any directory without an `AGENTS.md`, OpenCode reads `CLAUDE.md` instead." The repo [sst/opencode](https://github.com/sst/opencode) is silent on this, which is not a conflict. |
| pi | AGENTS.md or CLAUDE.md, both recognized | [pi configuration](https://docs.pi.dev/latest/configuration.md) | Moderate 1/1 primary | Opened through a redirect from pi.dev. Page says context files load from the agent folder, the working folder, and its parents. It does not say when at startup. The repo [pi-mono](https://github.com/badlogic/pi-mono) is silent on this, which is not a conflict. |
| codex | AGENTS.md, one file per folder | [Codex AGENTS.md guide](https://learn.chatgpt.com/docs/agent-configuration/agents-md) | Moderate 1/1 primary | Opened through a redirect from developers.openai.com. Page says Codex reads AGENTS.md before doing any work. The repo [openai/codex](https://github.com/openai/codex) is silent on this, which is not a conflict. |
| Claude Code | CLAUDE.md. AGENTS.md can stand in for it | [Claude Code memory](https://code.claude.com/docs/en/memory) | Med 2/3 | Page says Claude can read a repository's AGENTS.md in place of CLAUDE.md. The mockup does not use that stand-in: Claude Code gets `CLAUDE.md`. Second source [claude-code repo](https://github.com/anthropics/claude-code) names CLAUDE.md, but does not describe how it is loaded. |
| VS Code Copilot | .github/copilot-instructions.md | [GitHub repository instructions](https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions) | Med 2/3 | Page says the nearest AGENTS.md wins for agent work. A single CLAUDE.md or GEMINI.md at the root is also accepted. Second source [VS Code custom instructions](https://code.visualstudio.com/docs/copilot/customization/custom-instructions) names .github/copilot-instructions.md. |
| Continue | Markdown files in .continue/rules/ | [Continue rules](https://docs.continue.dev/customize/deep-dives/rules) | Moderate 1/1 primary | Page does not mention AGENTS.md. A third-party guide says Continue reads AGENTS.md too. That claim is not verified, so it is not used. The repo [continuedev/continue](https://github.com/continuedev/continue) is silent on this, which is not a conflict. |

### Legend

- Moderate 1/1 primary: one official docs page, opened, names the file. A repo that is silent is not a conflict.
- Med 2/3: two sources, both opened, agree on the file name.
- Low or None: no official docs page names the file. No row votes this.
- `unverified` in the link cell means the page was not opened. No row uses it today.

### Pointer targets

No target is dropped.

- Chosen app's file, created if missing: `AGENTS.md` (pi, opencode, codex) or `CLAUDE.md` (Claude Code).
- Only when already present: `.github/copilot-instructions.md` and `.continue/rules/`.
