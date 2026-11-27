# Real context window

Stage 4 should tell you the window this model will really run with, in short lines. If that window is too small for a coding agent, it offers a bigger copy of the same weights. It does not download anything, and it does not cut your prompt.

This file is the mockup. No product code yet. PR A (read the real window) waits until D3 PR B merges. PR B (the offer and the copy) waits until C4 B3 merges.

Base: `origin/main` `2ba43232f456fd1e6faa4052c09e4065c2266f58`.

## What is wrong today

Read on that commit, not guessed.

1. `agl/core/context_guard.py` `real_window` checks the loaded row (`/api/ps`), then `OLLAMA_CONTEXT_LENGTH`, then a VRAM default. It never reads the model's own `num_ctx`.
2. `agl/core/agent_config.py` `claude_context` still says the default is 4096 and then assumes 65536 when the env var is unset. Both can be wrong, and 65536 disagrees with the VRAM defaults.
3. After the stage line, `agl/ui/banner.py` prints a pile of lines, including a server restart command. We do not change Ollama settings, so that command should go.

The stage line itself stays the one `stage()` already prints. Stage 4 of 5 fills 16 of the 20 bar cells (`round(20 * 4 / 5)`). On this Windows console the bar is `#` and `-`. A console that can print the block glyph uses that instead. Same words either way.

## 1. Facts

Tags: High = 3 or more agreeing primary sources. Moderate = 2 agreeing, or 1 primary. Low = 1 secondary, or sources that fight. A row with no source is not here.

Read on 2026-11-27. Nothing in this table was run on this machine. The one `ollama create` test is still waiting for a yes, and for a quiet machine.

| Fact | Tag | Source |
|---|---|---|
| `POST /api/show` returns `parameters` as a string of `name value` lines. The official example includes a `num_ctx 2048` line. `model_info` holds `<family>.context_length` (the example is `gemma4.context_length` 131072). | Moderate | One primary: [Show model details](https://docs.ollama.com/api-reference/show-model-details). The Nov 22 note in the project log said the same shape. Confirmed there. Not proved: that the `num_ctx` line is omitted when the model sets none. |
| With nothing else set, the server picks 4096 under about 24 GiB of VRAM, 32768 from about 24 GiB, and 262144 from about 48 GiB. | High | [Context length](https://docs.ollama.com/context-length) (4k / 32k / 256k). Commit [`0cab1b6`](https://github.com/ollama/ollama/commit/0cab1b6) sets 4096, 32768, and 262144, and its env help says `4k/32k/256k based on VRAM`. The FAQ still says a flat 4096. The Modelfile table still says `num_ctx` default 2048. Those two are the old lines. The code cuts at 23 and 47 GiB, not 24 and 48, "to account for small differences." |
| A model's `num_ctx` beats `OLLAMA_CONTEXT_LENGTH`. The env var beats the VRAM default. A `num_ctx` on the request beats all three. | High | The same commit's `TestModelOptionsNumCtxPriority`: "model overrides env var" expects 16384 when the env is 8192; "env var overrides vram default"; "request overrides everything". A maintainer comment on [issue 18229](https://github.com/ollama/ollama/issues/18229) (2026-09-04) states that order. Not re-read on Ollama's main tip today. |
| The OpenAI-compatible endpoint does not take `num_ctx`. | Low | That same maintainer comment: `context_length` is not in the OpenAI API, so the compatible endpoint ignores it. One source. This is why a bigger window has to be a new tag. A flag on `/v1/chat/completions` will not do it. |
| `ollama create` from a model you already have reuses the weight layers. | Moderate | [API create](https://github.com/ollama/ollama/blob/main/docs/api.md) example, `from` an existing model, streams `using already created layer sha256:...`. Not run here. |
| Agents and coding tools should be set to at least 64000 tokens. | Moderate | [Context length](https://docs.ollama.com/context-length), one primary. The same page says a bigger window needs more memory. |
| How many tokens fit in free VRAM. | dropped | No formula on those pages. The third term of the target rule stays 32,768. |

`context_guard` already uses 4096 / 32768 / 262144 and the doc's 24 / 48 GiB lines. `claude_context` still talks as if 4096 and 65536 were the whole story. PR A makes them agree with the row above: the model's `num_ctx` when it has one, otherwise the env var, otherwise the VRAM default. The 23 vs 24 GiB cut stays as the code already has it (24 in our guard, 23 in Ollama's server). We do not retune that in this mockup.

## 2. Advisor guidance

The advisor skill is in the repo. This host has no `advisor-subagent` type, so there is no second-model verdict to paste. A stand-in writer was stopped before it could touch a file. The lines below are the main session applying the context-length page, which the brief says to follow when it beats a guess.

On a 16 GB GPU, ask for 32,768 tokens, not 64,000.

The docs want at least 64,000 for coding tools. The same docs put a 16 GB card in the 4,096 default tier, and they give no formula for what fits in free VRAM. The brief then says: take the smallest of that 64,000, the model's trained maximum, and 32,768. So 32,768 wins on this GPU, unless the model itself tops out lower. Do not call 32,768 "enough" in the 64,000 sense. Call it the size we ask for here.

Do not print a server restart, and do not print `OLLAMA_CONTEXT_LENGTH=...`. We do not change Ollama's settings. The offer is one question, `[y/N]`, and it says the copy reuses the weights you have.

If the running window is already at that target, or already at the model's trained maximum, do not offer a copy. A copy past the trained maximum would be a lie.

## 3. Stage 4 text

Every line below is under 100 columns and about 15 words. The indent is the seven spaces `context_check` already prints. The names are the sample from the Nov 27 run (`qwen2.5:14b-omb-32k` and `qwen2.5:14b`). The digits come from the target rule. If the trained maximum is lower, those digits shrink (see the rule).

### The model's num_ctx is already the target

```
STAGE 4/5  CONTEXT  [################----]  check the context window
       qwen2.5:14b-omb-32k runs with a 32,768 token window.
       That is the size we ask for on this GPU. No copy needed.
```

If the running window is the model's trained maximum, and that maximum is under the target, say this instead of offering a copy:

```
       qwen2.5:14b runs with an 8,192 token window.
       That is as high as this model goes. A bigger copy will not help.
```

(8,192 in that pair is a stand-in for whatever `trained_max` returned. Inferred example, not a measured model.)

### Nothing set, and the default is too small

```
STAGE 4/5  CONTEXT  [################----]  check the context window
       qwen2.5:14b runs with Ollama's default 4,096 tokens.
       Coding agents want about 32,768 on a 16 GB GPU.
       Make a 32K copy now? It reuses your weights. No download. [y/N]
```

Only `y` or `yes` goes on. Anything else, including end of input:

```
       Keeping qwen2.5:14b. Later: ollama create, PARAMETER num_ctx 32768.
```

Nothing is written. Ollama is not called.

### Yes, and the copy is made

```
       Made qwen2.5:14b-ctx32k. It uses the weights you already have.
       This run will use qwen2.5:14b-ctx32k, with a 32,768 token window.
```

Stage 4 then saves that tag the same way stage 3 saves the model you picked.

### The copy fails

```
       Could not make qwen2.5:14b-ctx32k. Keeping qwen2.5:14b.
       Reason: the create command failed. Nothing was downloaded.
```

The second line's reason is the real error, cut to one short line. The sample above is the fallback when the error text is empty. The model tag does not change.

## 4. Target window rule

The number we ask for is the smallest of these three:

| Term | Number | Mark |
|---|---|---|
| Coding-tools line on the context-length page | 64,000 | tested, one primary page |
| Trained maximum, `model_info` key ending in `.context_length` | per model | tested shape, the value is per model |
| What fits in free VRAM, or 32,768 when no formula exists | 32,768 | inferred fallback. No sourced fit formula, so this term is 32,768 |

On a 16 GB GPU that product is 32,768, unless the trained maximum is smaller. Then we ask for the maximum, and we do not offer a copy.

Floor for step mode: 8,192. Inferred from this brief, not from Ollama. It is the smallest window we still call ok for `/steps`. It is not a window we invent past the trained maximum. If the model tops out under 8,192, we say so, we do not create a copy, and `/steps` is still offered when a prompt does not fit.

`context_guard` today calls 65,536 "green" and 16,384 the amber line. Those bands stay until a later PR. This mockup does not print RED, AMBER, or GREEN. It prints the sentences above. Stage 4 must not print 65536 unless that is the real window.

## 5. Big prompts

Nothing is cut, and nothing is refused before it reaches the model, in the normal shell.

When a typed prompt is over the window (`checkpoint.tokens` says so), print one line and offer the copy or `/steps`. A typed `y` still sends the prompt unchanged. `n`, anything else, or end of input does not send it.

```
       That prompt is over this 4,096 token window.
       Make a 32K copy, or type /steps? A y still sends it. [y/N]
```

On `n` or end of input:

```
       Not sent. Nothing was cut, and the model was not changed.
```

The 4,096 and 32K in those two lines follow the same rule as stage 4. They are the sample, not fixed strings.

## 6. Name of the copy

`<tag>-ctx32k` when the target is 32,768. The number matches the target in thousands: 8,192 becomes `ctx8k`. No other brand word.

`qwen2.5:14b` becomes `qwen2.5:14b-ctx32k`.

The create command is a list, never a shell string, and it is never `pull`:

```
ollama create qwen2.5:14b-ctx32k -f <temp Modelfile>
```

The Modelfile is two lines:

```
FROM qwen2.5:14b
PARAMETER num_ctx 32768
```

## States

window read, then either it is enough (go on) or it is too small (offer the copy). Yes creates the copy: created, switch to it, or failed, keep the model and say why. No or end of input keeps the model and prints the one later line.

## Where the code will go

Not in this PR. Written here so the later diffs have a shape to match.

PR A, after D3 PR B merges. Both touch the stage 3/4 UI.

- `agl/platform` Ollama module: `show(tag)` calls `/api/show` and returns the dict, or None on any error. Same client. No new HTTP path.
- `context_guard.real_window` gains `shown`. Order: loaded row, then the model's `num_ctx`, then the env var, then the default. New source label: `"model"`. `trained_max(shown)` reads `model_info` `*.context_length`. Pure. No I/O.
- `claude_context` stops assuming 65536. It takes the real window.
- `banner.context_check` prints the lines in this file.

PR B, after C4 B3 merges. Both edit `_run_shell`.

- `agl/app/window_offer.py`: `offer(tag, shown, *, create, input_fn, out)`. One question. Only `y` or `yes` continues.
- `create` is injected. The platform side writes the two-line Modelfile and runs `["ollama", "create", new_tag, "-f", path]` through `process.run`, with a timeout, no shell. It never pulls.
- On success, stage 4 switches the run to the new tag and saves it like stage 3.
- The over-window lines live in `_run_shell`, few enough to pass the ruff gate.

Tests that must match this file exactly, later, not now: the four message cases; `real_window` order with a fake `shown` dict (`num_ctx` present, absent, junk); `trained_max` present and absent; yes creates and switches; no and end of input change nothing; a failed create keeps the model; the create command is a list; a big prompt is sent on `y` and not sent on `n`.
