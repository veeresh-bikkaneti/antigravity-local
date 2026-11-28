# Connect your coding app

You picked a model. Now let's point your editor at it. Ollama holds the model and every app below just knocks on its door at `http://localhost:11434`. Apps that speak the OpenAI style use `http://localhost:11434/v1`.

Checked 2026-11-18. Confidence tags: High means three or more primary sources agree. Moderate means two sources, or one primary source. Low means secondary or conflicting.

Two things before you start:

- Start Ollama first, and pull your model (`ollama list` shows it).
- Coding tools want a 64k context window. Ollama's default is 4k on a PC with under 24 GB of VRAM. On Windows, run `$env:OLLAMA_CONTEXT_LENGTH=65536; ollama serve`. On macOS or Linux, run `OLLAMA_CONTEXT_LENGTH=65536 ollama serve`. Or use the context slider in the Ollama app. Check with `ollama ps`. Source: [Ollama context length](https://docs.ollama.com/context-length) [Moderate]. Setup stage 4 says the window your model runs with and the largest one this GPU can hold, and offers to make a copy of the model with that window (no download).

`python run.py --coding-apps` prints a short version of this page with your model filled in.

## VS Code (Ollama extension)

VS Code's built-in Ollama provider is deprecated. Use the official Ollama extension instead.

1. Update VS Code (1.127 or newer) and Ollama (0.17.6 or newer recommended).
2. Install the extension with the ID `Ollama.ollama`.
3. Open Chat, open the model picker, and choose your model under **Ollama**.
4. If the model is missing, run **Ollama: Refresh Models** from the command palette. **Ollama: Diagnose Models** says what it sees.

Good to know: local models work without a GitHub sign-in or a Copilot plan. Completions and semantic search still need GitHub. On Business and Enterprise plans, an admin policy named "Bring Your Own Language Model Key in VS Code" controls this, and it is on by default. Agent mode hides any model that does not support tool calling, so pick one with the `tools` badge.

Sources: [VS Code language models](https://code.visualstudio.com/docs/agent-customization/language-models), [Ollama VS Code guide](https://docs.ollama.com/integrations/vscode), [GitHub changelog, 2026-04-22](https://github.blog/changelog/2026-04-22-bring-your-own-language-model-key-in-vs-code-now-available/) [Moderate]. Checked 2026-11-18.

## Continue (VS Code or JetBrains)

1. Install Continue and open its settings.
2. Open `config.yaml` from there.
3. Add your model. The `model` value must match `ollama list` exactly:

   ```yaml
   models:
     - name: My local model
       provider: ollama
       model: qwen2.5:14b
       apiBase: http://localhost:11434
       roles: [chat, edit]
       capabilities: [tool_use]   # needed for agent mode
   ```
4. Pick the model in Continue's chat box.

Source: [Continue Ollama guide](https://docs.continue.dev/guides/ollama-guide) [Moderate, one primary source, written for Continue 1.1.x]. Checked 2026-11-18.

## Terminal agents

1. Run `python run.py --agent pi` from your project. Swap `pi` for `opencode`, `codex` or `claude`.
2. Say `y` if it offers to install the agent. It adds only an Ollama entry to that agent's own config.
3. Prefer Ollama's own helper? `ollama launch pi` does a similar job.

Sources: this repo's `agent_setup.py` (covered by the offline tests), [Ollama pi guide](https://docs.ollama.com/integrations/pi) [Moderate]. The `ollama launch` app list in the README was checked on 2026-11-14 and not re-checked. Checked 2026-11-18.

## Antigravity app

The Antigravity app and its agent window have no documented setting for a local model. The plans page says it has no support for "Bring-your-own-key (BYOK) or bring-your-own-endpoint for additional rate limits". That wording is about rate limits, so read it as "no documented setting", not "impossible". Google's local-model page covers the SDK only.

What works today:

1. Open the app's built-in terminal in your project.
2. Run `python <path>\antigravity-local\run.py --agent pi`, using the full path to where you cloned this repo.

For your own SDK code, `LocalOpenAIAgentConfig(model="<tag>", base_url="http://localhost:11434/v1")` is the local option, and `LiteRTAgentConfig` is the other. This repo's code uses the first one.

Sources: [Antigravity plans](https://antigravity.google/docs/plans), [Antigravity SDK local models](https://antigravity.google/docs/sdk/local-models/) [Moderate]. Checked 2026-11-18.

## Gemini CLI

Gemini CLI has no native local-model support. A feature request ([#24166](https://github.com/google-gemini/gemini-cli/discussions/24166), 2026-03-29) has no maintainer reply, and [#23385](https://github.com/google-gemini/gemini-cli/issues/23385) was closed as a possible duplicate [Moderate].

The only route we know is a LiteLLM proxy. It is experimental and **not tested by us**.

1. Run a LiteLLM proxy in front of Ollama, with a `model_group_alias` that maps the Gemini model name to your Ollama model.
2. Set `GOOGLE_GEMINI_BASE_URL=http://localhost:4000`.
3. Set `GEMINI_API_KEY` to your LiteLLM key.

One report says the CLI ignores `GOOGLE_GEMINI_BASE_URL` when cached Google credentials exist ([#15430](https://github.com/google-gemini/gemini-cli/issues/15430)) [Low]. Source for the route: [LiteLLM tutorial](https://docs.litellm.ai/docs/tutorials/litellm_gemini_cli) [Moderate]. Checked 2026-11-18.

## Your own code

Any OpenAI-style client works.

1. Set the base URL to `http://localhost:11434/v1`.
2. Set the model to your tag, for example `qwen2.5:14b`.
3. Use any non-empty string as the API key. Ollama ignores it.

Sources: [Antigravity SDK local models](https://antigravity.google/docs/sdk/local-models/), [Ollama pi guide](https://docs.ollama.com/integrations/pi), [Ollama VS Code guide](https://docs.ollama.com/integrations/vscode) [High]. Checked 2026-11-18.

## Step mode: `/steps <task>`

Type `/steps <task>` in the built-in shell to walk a long task one step at a time. The plan waits for your `y`. Each step runs in a fresh chat, so a small window never fills with old turns. The checkpoint keeps what is done, and the next start offers to resume. An optional test command, typed after the plan, must exit 0 before a step counts as done. It is kept for that run only. A prompt bigger than the window is never cut. The shell says so and asks `Send anyway? [Y/n]`: Enter sends it unchanged, `n` or end of input holds it, and `/steps` turns it into a step-mode task.

## Shared checkpoint file

Long tasks can outgrow a coding app's window, and switching models can drop the plan. So stage 4 can offer one shared file for every app: `.agl/checkpoint.md` in your project. It keeps the plan, what is done, what is next, the files you touched, and a few notes. It is capped near 1,500 tokens, and when it grows past that, the oldest finished steps get trimmed first. The next step is never dropped.

Say y at the stage 4 question and we do three things, after showing you what will change:

1. Create or update `.agl/checkpoint.md`.
2. Add a short pointer block (between two marker lines, so we can find it again) to each instruction file that applies: `AGENTS.md` (created if missing), plus `CLAUDE.md`, `.github/copilot-instructions.md`, or `.continue/rules/` when they already exist.
3. Add `.agl/` to your `.gitignore`.

Anything we did not write gets a backup first. Your own lines outside the pointer block stay exactly as they are. A second run with y changes no bytes. Say n, or press Enter, and nothing is written.

If git already tracks `.agl/checkpoint.md`, we refuse and write nothing, because notes in there would be committed. The fix is to run `git rm --cached .agl/checkpoint.md` (this keeps your file), then run the offer again. `HANDOFF.md` is separate: the pointer tells the app it can read `HANDOFF.md` as extra reading, and we never merge or rename it.

## Not covered

We did not re-check Cline steps today (the README still has them), and we found nothing for Claude Desktop or an Antigravity command-line tool called `agy`.

## Web check (optional)

You can also let the shell check a claim on the web. It uses a local SearXNG at `AGL_SEARXNG_URL` first. Tavily runs only if `TAVILY_API_KEY` is set and SearXNG is unset or out of reach. If neither is there, every claim is "Data not available." No model is pulled. Notes live in [mockups/verifier.md](mockups/verifier.md).
