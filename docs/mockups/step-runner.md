# Step runner (mockup)

This is a design mockup for C4. No code exists yet. The lines in the fences are the words the shell will print, so a later change to the code has to change this file first.

A small local model forgets a long task once the window fills. Step mode walks the task one step at a time. Each step is a new chat. The chat holds the checkpoint, that one step, and room for the reply. After the step, the runner checks the work and writes `.agl/checkpoint.md`. If the run dies, or you come back on another model, the next run starts at the first open step.

The shell is the built-in one (`_run_shell` in `agl/app/agent.py`). You type `/steps` and the task. This does not use `--resume-from`. That flag already means a Claude Code transcript (`run.py` line 71).

## How a run moves

idle, then planned, then step N running, then step N checking, then step N done, and so on until all done.

A failed check goes to step N blocked and asks you. Ctrl+C, or a crash, goes to interrupted. The checkpoint already has every finished step. Resume goes back to step N running, for the first step that is still `[ ]`.

## 1. How a run starts

Type this at the `You >` prompt:

```text
You > /steps Add a health page and a test that opens it
Step mode. Window: 8192 tokens. Each step is a fresh chat.
Planning. Nothing runs until you type y.
```

On a later shell start, if `.agl/checkpoint.md` still has open steps, the shell asks before the first `You >`. Here step 3 of 5 is the first open one. End of input counts as no, and the shell just continues.

```text
Resume at step 3 of 5? [y/N] y
```

The number and the total come from the checkpoint. `y` resumes. `n`, Enter, or end of input does not.

## 2. The plan step

The model sees only the task and must return 2 to 8 short steps, one line each, no commands. The runner prints them and waits. Nothing is written, and no step runs, until you type `y`.

```text
  1. Add health.html with one status line
  2. Add test_health.py that reads that file
  3. Run the test you type at plan time
  4. Note both files in the checkpoint
  5. Leave a one-line note for the next session
Accept this plan? [y/N] y
Test command (empty skips it): python -m unittest test_health
Wrote <repo>\.agl\checkpoint.md with 5 open steps.
```

The test command is optional. You type it here, or you leave it empty. The runner stores your words. It never stores a command the model wrote.

`n` or end of input drops the plan. The runner writes no file.

```text
Accept this plan? [y/N] n
Plan dropped. Nothing was written.
```

```text
Accept this plan? [y/N]
Plan dropped. Nothing was written.
```

The second prompt is end of input. Same result.

Accepted steps go into Plan as `[ ]` lines. A goal line you already had stays put. This is the file just after a yes, before any step runs:

```markdown
# Checkpoint

<!-- agl-checkpoint v1 -->
updated: 2026-11-27T12:00:00+00:00 (example)

## Plan

- The goal: a health page and a test that opens it.
- [ ] Add health.html with one status line
- [ ] Add test_health.py that reads that file
- [ ] Run the test you type at plan time
- [ ] Note both files in the checkpoint
- [ ] Leave a one-line note for the next session

## Done

- (none yet)

## Next

- [ ] Add health.html with one status line

## Files

- (none yet)

## Notes

- User: keep the page to one line. Do not add a framework.
```

The `User:` note is yours. Later writes keep it.

## 3. One 5-step run at 8K

Window is 8192 tokens. Each step header is the start. `Check passed.` means the check said the step is done. `Saved.` means the checkpoint was written before the next step started.

```text
--- step 1 of 5 ---
Add health.html with one status line
Agent > Wrote health.html.
Check passed. health.html is new.
Saved. Step 1 is done. Next is step 2.
--- step 2 of 5 ---
Add test_health.py that reads that file
Agent > Done. You should run pytest now.
Check failed. test_health.py is not in the file list.
A command in the reply was not run.
Retry, skip or stop? [r/s/S] r
--- step 2 of 5 ---
Add test_health.py that reads that file
Agent > Wrote test_health.py.
Check passed. test_health.py is new.
Saved. Step 2 is done. Next is step 3.
--- step 3 of 5 ---
Run the test you type at plan time
^C
Interrupted on step 3. Steps 1 and 2 are saved.
```

`r` retries the same step in a new chat. `s` skips it (marks it done and moves on). `S` and end of input both stop. The open step stays `[ ]`.

A stop from a failed check, as its own short scene:

```text
Retry, skip or stop? [r/s/S]
Stopped. Step 2 is still open.
```

That blank answer is end of input.

Ctrl+C lost only step 3. The checkpoint on disk already has steps 1 and 2 under Done, and your note is still there:

```markdown
## Plan

- The goal: a health page and a test that opens it.
- [ ] Run the test you type at plan time
- [ ] Note both files in the checkpoint
- [ ] Leave a one-line note for the next session

## Done

- [x] Add health.html with one status line
- [x] Add test_health.py that reads that file

## Next

- [ ] Run the test you type at plan time

## Notes

- User: keep the page to one line. Do not add a framework.
```

Start the shell again. It offers resume. `y` runs step 3, then 4, then 5. Steps 1 and 2 do not run again. A different model name changes nothing about which step is next. The checkpoint decides.

```text
Resume at step 3 of 5? [y/N] y
--- step 3 of 5 ---
Run the test you type at plan time
Agent > The test you typed finished with exit 0.
Check passed.
Saved. Step 3 is done. Next is step 4.
--- step 4 of 5 ---
Note both files in the checkpoint
Agent > Noted health.html and test_health.py.
Check passed.
Saved. Step 4 is done. Next is step 5.
--- step 5 of 5 ---
Leave a one-line note for the next session
Agent > Noted: keep the page to one line.
Check passed.
Saved. Step 5 is done.
All 5 steps are done.
```

The test command from plan time runs only inside the check, and only because you typed it. The `pytest` line from step 2 was the model's idea. It was not run.

If git already tracks `.agl/checkpoint.md`, the runner refuses before it writes. The sentence is the one in `agl/app/checkpoint_offer.py` around line 152 (`Not changed: ... is already tracked by git`). Nothing is written.

If the step prompt does not fit the window, the runner does not send it:

```text
This step does not fit the window. It was not sent.
```

## 4. Budget math

`tokens` is `len(text) // 4` from `agl.core.checkpoint.tokens`. The system prompt is `MAIN_SYSTEM_PROMPT`. The checkpoint cap is `CAP_TOKENS` (1,500). Step text and the reply reserve are planning numbers, not a measurement of a live call.

A step is sent only when system + checkpoint + step text + reply reserve is at most the window. The real window comes from `agl.core.context_guard.real_window`, the same way C1 reads it.

| Window | Tokens | System prompt | Checkpoint cap | Step text | Reply reserve | Left | Basis |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 8K | 8192 | 665 | 1500 | 200 | 1024 | 4803 | system tested, rest inferred |
| 16K | 16384 | 665 | 1500 | 200 | 1024 | 12995 | system tested, rest inferred |
| 32K | 32768 | 665 | 1500 | 200 | 1024 | 29379 | system tested, rest inferred |

Left = window minus the four costs. 8K fits. Headroom is 4,803 tokens. Nothing needs a cut.

Replace 665, and recompute Left, if your own measurement is not 665. Keep step text at 200 and the reply reserve at 1024, both inferred.

## 5. Sanity check

The model answers a fixed yes/no, "Is this step done?", and the runner shows the file list from `agl/core/task_report.py`; a test command runs only when you typed it at plan time, through `agl/platform/process.py` `run` with a timeout and no shell, and a command the model suggests is never run.
