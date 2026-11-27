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

Read on 2026-11-27. Nothing in this table was run on this machine. The one `ollama create` test is still waiting for a yes, and for a quiet machine. The fit table below does not call `/api/show`. Its model shape is the Hugging Face config.

| Fact | Tag | Source |
|---|---|---|
| `POST /api/show` returns `parameters` as a string of `name value` lines. The official example includes a `num_ctx 2048` line. `model_info` holds `<family>.context_length` (the example is `gemma4.context_length` 131072). | Moderate | One primary: [Show model details](https://docs.ollama.com/api-reference/show-model-details). The Nov 22 note in the project log said the same shape. Confirmed there. Not proved: that the `num_ctx` line is omitted when the model sets none. |
| With nothing else set, the server picks 4096 under about 24 GiB of VRAM, 32768 from about 24 GiB, and 262144 from about 48 GiB. | High | [Context length](https://docs.ollama.com/context-length) (4k / 32k / 256k). Commit [`0cab1b6`](https://github.com/ollama/ollama/commit/0cab1b6) sets 4096, 32768, and 262144, and its env help says `4k/32k/256k based on VRAM`. The FAQ still says a flat 4096. The Modelfile table still says `num_ctx` default 2048. Those two are the old lines. The code cuts at 23 and 47 GiB, not 24 and 48, "to account for small differences." |
| A model's `num_ctx` beats `OLLAMA_CONTEXT_LENGTH`. The env var beats the VRAM default. A `num_ctx` on the request beats all three. | High | The same commit's `TestModelOptionsNumCtxPriority`: "model overrides env var" expects 16384 when the env is 8192; "env var overrides vram default"; "request overrides everything". A maintainer comment on [issue 18229](https://github.com/ollama/ollama/issues/18229) (2026-09-04) states that order. Not re-read on Ollama's main tip today. |
| The OpenAI-compatible endpoint does not take `num_ctx`. | Low | That same maintainer comment: `context_length` is not in the OpenAI API, so the compatible endpoint ignores it. One source. This is why a bigger window has to be a new tag. A flag on `/v1/chat/completions` will not do it. |
| `ollama create` from a model you already have reuses the weight layers. | Moderate | [API create](https://github.com/ollama/ollama/blob/main/docs/api.md) example, `from` an existing model, streams `using already created layer sha256:...`. Not run here. |
| Agents and coding tools should be set to at least 64000 tokens. | Moderate | [Context length](https://docs.ollama.com/context-length), one primary. The same page says a bigger window needs more memory. The offer treats 64000 as a ceiling too: we do not write a `num_ctx` above it. |
| KV bytes = tokens x layers x kv heads x (key length + value length) x bytes per value. f16 is 2. q8_0 is 34/32 (1.0625). q4_0 is 18/32 (0.5625). | Moderate | One primary: [llama.cpp discussion 10068](https://github.com/ggml-org/llama.cpp/discussions/10068). The same note checks gemma-2-9b: 42 layers x 8 KV heads x (256 + 256) x 2 = 344064 bytes per token, x 3072 = 1008 MiB, the printed `KV self size`. GGUF keys: `<arch>.block_count`, `<arch>.attention.head_count_kv` (sum the layers when it is an array), `<arch>.attention.key_length` and `value_length`, else `embedding_length / attention.head_count`. |
| The compute graph has no closed form. It is a dry run, separate from the KV line. | Moderate | The same discussion: compute buffers have no closed form. `common/fit.h` `common_get_device_memory_data` returns model, context, and compute bytes with `no_alloc`. Ollama's `GGML.GraphSize` is the project name for that allocator. Its body was not re-read this round, so the table subtracts no graph number. |
| `qwen2.5:14b` on the Ollama library is Q4_K_M and the page says 9.0GB. | Moderate | [Library tag](https://ollama.com/library/qwen2.5:14b), digest `7cdf5a0187d5`. The page does not say whether GB is 10^9 or 2^30. |
| Qwen2.5-14B shape used below. | Moderate | [config.json](https://huggingface.co/Qwen/Qwen2.5-14B/raw/main/config.json), read 2026-11-27. `num_hidden_layers` 48, `num_attention_heads` 40, `num_key_value_heads` 8, `hidden_size` 5120, `max_position_embeddings` 131072, `use_sliding_window` false, `sliding_window` 131072. No `key_length` field. |

`context_guard` already uses 4096 / 32768 / 262144 and the doc's 24 / 48 GiB lines. `claude_context` still talks as if 4096 and 65536 were the whole story. PR A makes them agree with the read order above, and adds the fit in section 4. The 23 vs 24 GiB server cut stays as the code already has it. We do not retune that in this mockup.

## 2. Advisor guidance

The advisor skill is in the repo. This host has no `advisor-subagent` type, so there is no second-model verdict to paste. A stand-in writer was stopped before it could touch a file. The lines below follow the context-length page and the KV note in section 1.

Ask for the largest rung this GPU can hold, not a fixed 32,768. The docs want at least 64,000 for coding tools, and they also say a bigger window needs more memory. Section 4 is that memory check. Do not call a smaller rung "enough" in the 64,000 sense. Name the number the table picked.

Do not print a server restart, and do not print `OLLAMA_CONTEXT_LENGTH=...`. We do not change Ollama's settings. The copy question is `[y/N]`. The later big-prompt question is a different line, `[Y/n]`, and it does not offer the copy.

If the running window is already at the target, or already at the model's trained maximum, do not offer a copy. A copy past the trained maximum would be a lie.

## 3. Stage 4 text

Every line below is under 100 columns and about 15 words. The indent is the seven spaces `context_check` already prints. The names are the sample from the Nov 27 run (`qwen2.5:14b-omb-32k` and `qwen2.5:14b`). The digits are the 16 GiB row of section 4, because that row is the one that still offers a copy and does not flip when 9.0GB is read as decimal. A 24 GiB row would print 64,000 and `ctx64k` instead.

### The model's num_ctx is already the target

On the 16 GiB row the target is 16,384, so a tag that already runs at 32,768 is past it:

```
STAGE 4/5  CONTEXT  [################----]  check the context window
       qwen2.5:14b-omb-32k runs with a 32,768 token window.
       That covers the 16,384 this GPU can give. No copy needed.
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
       Coding agents want about 16,384 on this GPU.
       Make a 16K copy now? It reuses your weights. No download. [y/N]
```

Only `y` or `yes` goes on. Anything else, including end of input:

```
       Keeping qwen2.5:14b. I'll offer the copy again next start.
```

Nothing is written. Ollama is not called. The next start asks again. We do not print an `ollama create` line for later.

### Yes, and the copy is made

```
       Made qwen2.5:14b-ctx16k. It uses the weights you already have.
       This run will use qwen2.5:14b-ctx16k, with a 16,384 token window.
```

Stage 4 then saves that tag the same way stage 3 saves the model you picked.

### The copy fails

```
       Could not make qwen2.5:14b-ctx16k. Keeping qwen2.5:14b.
       Reason: the create command failed. Nothing was downloaded.
```

The second line's reason is the real error, cut to one short line. The sample above is the fallback when the error text is empty. The model tag does not change.

### The rung does not fit

8 GiB and 12 GiB in the table. Same words. The table says which reason.

```
       qwen2.5:14b runs with Ollama's default 4,096 tokens.
       This GPU cannot fit an 8,192 window on top of the weights.
       No copy. A long prompt can use /steps.
```

## 4. Target window rule

Room for the cache, in GiB (2^30). Inferred until a `/api/ps` `size_vram` delta checks it:

```
pool = get_free_vram_gb
```

`get_free_vram_gb` is `agl/platform/hardware.py`. It reads `nvidia-smi memory.free` and divides MiB by 1024.

When this model is already loaded, add its `size_vram` from `/api/ps` back, so the weights are not counted twice. Then subtract the weight reservation. The reservation is the existing `FIT_HEADROOM` of 1.2 in `agl/core/menu.py` (`size x 1.2`). There is no extra 1.5 GiB knob.

```
room = pool - (weight_bytes x 1.2)
```

KV bytes, f16, one sequence. Tested arithmetic once the shape is known:

```
tokens x layers x kv_heads x (key_length + value_length) x 2
```

Graph bytes sit on the next line and are not in `room`. Discussion 10068 says they have no closed form. Measure them later with `common_get_device_memory_data` or with a `size_vram` delta. This table uses KV only.

Cache type is f16 unless `OLLAMA_KV_CACHE_TYPE` is set. q8_0 stores 1.0625 bytes per value (0.53125 of f16). q4_0 stores 0.5625 (0.28125 of f16). Both factors are the discussion's block sizes, not a measurement on this GPU. `OLLAMA_NUM_PARALLEL` multiplies the cache. The table assumes 1.

If `attention.sliding_window` is in use, those layers keep `min(tokens, sliding_window)` cells, not the full rung. This config sets `use_sliding_window` to false, and `sliding_window` equals the trained max (131072), so every rung below pays full KV.

The rungs are 8192, 16384, 32768, and 65536. Take the largest whose KV bytes fit in `room` and whose size is at most the trained max (`model_info` key ending in `.context_length`). Then cap at 64000. 65536 is over that cap, so a fit at 65536 is written as 64000. The copy name uses thousands of the written number: 8192 is `ctx8k`, 16384 is `ctx16k`, 32768 is `ctx32k`, 64000 is `ctx64k`.

Under 8192, or a negative room: say so, offer `/steps`, do not create a copy.

`context_guard` today calls 65536 "green" and 16384 the amber line. Those bands stay until a later PR. This mockup does not print RED, AMBER, or GREEN. It prints the sentences above. Stage 4 must not print 65536 unless that is the real running window.

### Shape for qwen2.5:14b

From the config, not from `/api/show`. Key length is inferred: the config has no `key_length`, so `5120 / 40 = 128`. Value length is the same inference. Trained max for the cap is `max_position_embeddings` 131072, the stand-in for `qwen2.context_length`.

| Input | Value | Mark |
|---|---|---|
| layers | 48 | tested, config |
| KV heads | 8, one number | tested, config. Not an array, so nothing to sum |
| key length and value length | 128 and 128 | inferred from `hidden_size / num_attention_heads` |
| bytes per value | 2 | assumed f16 |
| bytes per token | 48 x 8 x (128 + 128) x 2 = 196608 (192 KiB) | tested arithmetic |
| 8192 tokens | 1.5 GiB | tested arithmetic |
| 16384 tokens | 3.0 GiB | tested arithmetic |
| 32768 tokens | 6.0 GiB | tested arithmetic |
| 65536 tokens | 12.0 GiB | tested arithmetic |
| 64000 tokens | 11.71875 GiB | tested arithmetic |
| weights | 9.0 GB on the library page | tested label. Counted below as 9.0 GiB, inferred |
| reservation | 9.0 x 1.2 = 10.8 GiB | inferred |

The model is not loaded in these rows, so `size_vram` adds nothing. Card sizes are the scenario, not a probe reading.

| Card (GiB) | Room | Largest rung that fits | Written target | Name | Mark |
|---|---|---|---|---|---|
| 8 | 8 - 10.8 = -2.8 | none. Weights do not fit | none | none | inferred |
| 12 | 12 - 10.8 = 1.2 | none. 1.2 < 1.5 | none | none | inferred |
| 16 | 16 - 10.8 = 5.2 | 16384 (3.0 fits, 6.0 does not) | 16384 | `ctx16k` | inferred |
| 24 | 24 - 10.8 = 13.2 | 65536 (12.0 fits), then the 64000 cap | 64000 | `ctx64k` | inferred |

If the library's 9.0GB means 9 x 10^9 bytes, the reservation is about 10.06 GiB. The 8, 16, and 24 rows do not change. The 12 GiB room becomes about 1.94 GiB, so 8192 fits and the offer becomes `ctx8k`. That fork is inferred. The stage 4 sample stays the 16 GiB row.

## 5. Big prompts

Nothing is cut, and nothing is refused before it reaches the model, in the normal shell.

Stage 4 already offered the copy. This line does not offer it again. When a typed prompt is over the window (`checkpoint.tokens` says so), ask whether to send it. Empty Enter, `y`, or `yes` sends the prompt unchanged. `n` or `no` holds it. End of input holds it too: a closed pipe is not a typed Enter. The model is not changed on either path.

```
       Over the 4,096 window, so the model may forget the start.
       Send anyway? [Y/n] (or type /steps)
```

On `n`, `no`, or end of input:

```
       Not sent. Nothing was cut, and the model was not changed.
```

The 4,096 in the question is the running window for this sample, not a fixed string.

## 6. Name of the copy

The number matches the written target in thousands. No other brand word.

On the 16 GiB sample, `qwen2.5:14b` becomes `qwen2.5:14b-ctx16k`. On the 24 GiB row it becomes `qwen2.5:14b-ctx64k` and `num_ctx` is 64000, not 65536.

The create command is a list, never a shell string, and it is never `pull`:

```
ollama create qwen2.5:14b-ctx16k -f <temp Modelfile>
```

The Modelfile is two lines. `FROM` is the bare tag, not a quoted path:

```
FROM qwen2.5:14b
PARAMETER num_ctx 16384
```

## States

Window read, then either it already covers the target (go on), the model cannot go higher (say so), the GPU cannot hold 8192 more (say so, offer `/steps`), or the default is under the target (offer the copy). Yes creates the copy: created, switch to it, or failed, keep the model and say why. No or end of input keeps the model and says the offer returns next start.

A prompt over the window is a later question. Enter or yes sends it whole. No holds it. That question does not create a tag.

## Where the code will go

Not in this PR. Written here so the later diffs have a shape to match.

PR A, after D3 PR B merges. Both touch the stage 3/4 UI.

- `agl/platform` Ollama module: `show(tag)` calls `/api/show` and returns the dict, or None on any error. Same client. No new HTTP path.
- `context_guard.real_window` gains `shown`. Order: loaded row, then the model's `num_ctx`, then the env var, then the default. New source label: `"model"`. `trained_max(shown)` reads `model_info` `*.context_length`. The fit in section 4 is pure too: KV bytes from `model_info`, room from `get_free_vram_gb`, plus `size_vram` when this tag is loaded, minus `weight_bytes x 1.2`. No I/O inside the pure function. The probe and `/api/ps` stay in platform and app.
- `claude_context` stops assuming 65536. It takes the real window.
- `banner.context_check` prints the lines in this file. The digits come from the fit, not from a constant.

PR B, after C4 B3 merges. Both edit `_run_shell`.

- `agl/app/window_offer.py`: `offer(tag, shown, *, create, input_fn, out)`. One question. Only `y` or `yes` continues. No or end of input prints the next-start line.
- `create` is injected. The platform side writes the two-line Modelfile and runs `["ollama", "create", new_tag, "-f", path]` through `process.run`, with a timeout, no shell. It never pulls.
- On success, stage 4 switches the run to the new tag and saves it like stage 3.
- The over-window lines live in `_run_shell`. They do not call `create`. Empty Enter, `y`, or `yes` sends the text. `n`, `no`, or end of input does not.

Tests that must match this file exactly, later, not now: the message cases, including the 16,384 sample and the no-fit lines; `real_window` order with a fake `shown` dict (`num_ctx` present, absent, junk); `trained_max` present and absent; the fit picks 16384 for the 16 GiB row and 64000 for the 24 GiB row, and picks nothing when room is under 1.5 GiB; yes creates and switches; no and end of input change nothing and the next-start line is exact; a failed create keeps the model; the create command is a list; a big prompt is sent on Enter, `y`, and `yes`, and not sent on `n`, `no`, or end of input.
