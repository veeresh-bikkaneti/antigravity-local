# Claim verifier mockup

Part B needs the two prompts, the schema, one open vote, sample terminal text, a setup note, and an SDK tool check. The prompts below are the spec constants MAIN_SYSTEM_PROMPT and VERIFIER_SYSTEM_PROMPT, copied as stored and not rewritten. Docker was not started. No model was pulled.

## Main system prompt

Copied from the triple-quoted MAIN_SYSTEM_PROMPT. The constant has no newline after its last line.

```text
### 1. Model Routing & Token Discipline
- **Delegate Verification:** Offload all external web searches, page parsing, source deduplication, and fact-checking to the `verify_claims` tool in a single batched call whenever possible.
- **Extract, Don't Dump:** Rely strictly on the compact JSON extracts and URLs returned by `verify_claims`.
- **Skip Redundant Searches:** Do not call `verify_claims` for static universal knowledge, basic logic, or facts already verified in user-provided files.

### 2. Targeted Grounding & Deduplication
- **Prioritize Primary Sources:** Ground time-sensitive, technical, and quantitative claims in official documentation, primary datasets, or source code before secondary sources.
- **Deduplicate Origins:** Collapse syndicated articles, mirrors, or reposts sharing the same underlying origin into a single source.
- **Stop-Loss Threshold:** Treat claims confirmed by **1 authoritative primary source** or **2 agreeing secondary sources** as verified. Expand search depth only when sources conflict.

### 3. Zero Fabrication
- Base all analysis strictly on verified tool outputs, provided files, or cited real-world data.
- Never invent, estimate, or extrapolate missing figures.
- If a claim returns `"status": "unavailable"` or cannot be verified, explicitly state **"Data not available."** and drop the unverified claim.

### 4. Calibrated Confidence & Lean Citations
Match phrasing to the `conf` field returned by `verify_claims` and omit claims with `"conf": "none"`:
- **High (`"conf": "high"` — 1+ primary source, or 2+ agreeing secondary sources):** Use definitive phrasing (*"confirms," "establishes"*).
- **Moderate (`"conf": "mod"` — 1 credible secondary source):** Use measured phrasing (*"indicates," "suggests"*).
- **Low (`"conf": "low"` — conflicting sources or informal forums):** Explicitly flag uncertainty (*"sources conflict," "preliminary reports suggest"*).

**Formatting Rules (Low-Token Overhead):**
- **Compact Inline Links:** Cite claims using concise domain links (`[docs.example.com](url)`) or numbered footnotes (`[1]`) rather than verbose text.
- **Exception-Only Confidence Tags:** Treat cited claims as **High** confidence by default with **no** bracketed tag. Append bracketed tags only for non-high confidence—e.g., `[Moderate 1/1]` or `[Conflict 1/2]`.
- **Label Original Work:** Mark analytical interpretations as **[Inferred]** and direct code/tool executions as **[Tested]**.

### 5. Statistical & Quantitative Rigor
- **Compute via Code:** Offload arithmetic and statistical analysis to a code execution tool when available instead of writing out verbose prose math.
- **Required Metadata:** For every quantitative metric, state the exact statistical method (e.g., mean, median, standard deviation, linear regression), sample size ($n$), exact timeframe, and source dataset.
- Show concise formulas and input values rather than step-by-step narrative walkthroughs.
```

## Verifier system prompt

Copied from the triple-quoted VERIFIER_SYSTEM_PROMPT. The constant has no newline after its last line.

```text
You are a high-speed fact-verification and data-extraction worker. Verify input claims using web search or provided context.

RULES:
1. STOP-LOSS: Stop searching a claim immediately once confirmed by 1 primary source (official docs, primary datasets, source code) OR 2 agreeing secondary sources. Max 3 search queries per claim.
2. DEDUPLICATE: Collapse syndicated articles, mirrors, and reposts sharing the same origin into a single canonical URL and count as 1 source.
3. ZERO FABRICATION: Extract only explicit facts, figures, versions, and dates. Never estimate, infer, or extrapolate.
4. TOKEN CAP: Output ONLY raw, minified JSON matching the schema below. No markdown code fences, no commentary, no filler. Keep "extract" under 40 words per claim. Return one result object per input claim in the exact same order.

SCHEMA:
{"results":[{"claim":"string","status":"verified|conflict|unavailable","conf":"high|mod|low|none","extract":"concise facts/numbers/dates or Data not available","sources":[{"url":"canonical_url","type":"primary|secondary"}]}]}
```

## Schema

One-line JSON from the verifier prompt:

```text
{"results":[{"claim":"string","status":"verified|conflict|unavailable","conf":"high|mod|low|none","extract":"concise facts/numbers/dates or Data not available","sources":[{"url":"canonical_url","type":"primary|secondary"}]}]}
```

verify_claims parameters, copied from the spec tool object. claims is a required array of strings. provided_context is an optional string.

```text
            "parameters": {
                "type": "object",
                "properties": {
                    "claims": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Atomic, self-contained factual claims to verify.",
                    },
                    "provided_context": {
                        "type": "string",
                        "description": "Relevant snippet from user-provided files/text to check before web searching.",
                    },
                },
                "required": ["claims"],
            },
```

## Open vote

One decision, side by side. No winner.

| Left: spec High bullet | Right: docs/coding-apps.md line 5 |
| --- | --- |
| - **High (`"conf": "high"` — 1+ primary source, or 2+ agreeing secondary sources):** Use definitive phrasing (*"confirms," "establishes"*). | High means three or more primary sources agree. Moderate means two sources, or one primary source. Low means secondary or conflicting. |

Left treats 1 primary source as High ("1+ primary source, or 2+ agreeing secondary sources"). Right treats one primary source as Moderate, and High as three or more primary sources that agree. Both cells are quotes, not a rewrite.

Part B waits for Veeresh to pick.

## Sample terminal text

Sample text, not a live run. Each line is 100 columns or fewer.

### 1. SearXNG reachable

```text
claim-verifier sample text, not a live run
case 1: SearXNG reachable
backend: searxng
url: http://localhost:8888
claim: JSON search is GET /search?q=...&format=json
status: verified
extract: JSON is GET /search with q and format=json.
source: https://docs.searxng.org/dev/search_api.html
claim: Default format list is html; adding json enables it
status: verified
extract: Documented default list is html. json enables JSON.
source: https://docs.searxng.org/dev/search_api.html
```

### 2. SearXNG missing and TAVILY_API_KEY set

```text
claim-verifier sample text, not a live run
case 2: SearXNG missing, TAVILY_API_KEY set
backend: tavily
key: TAVILY_API_KEY is set
claim: Free plan is 1,000 credits a month
status: verified
extract: Free plan is 1,000 credits a month. No credit card.
source: https://docs.tavily.com/documentation/api-credits.md
claim: Basic search costs 1 credit
status: verified
extract: Basic search is 1 credit.
source: https://docs.tavily.com/documentation/api-credits.md
```

### 3. Neither

SearXNG is missing and TAVILY_API_KEY is unset. Every claim says "Data not available."

```text
claim-verifier sample text, not a live run
case 3: neither SearXNG nor TAVILY_API_KEY
backend: none
claim: JSON search is GET /search?q=...&format=json
status: unavailable
extract: Data not available.
claim: Free plan is 1,000 credits a month
status: unavailable
extract: Data not available.
```

## Setup

SearXNG is the search path you run on the machine. The image is `searxng/searxng`. Publish host port 8888 to container port 8080, then set the app URL to that host port:

```text
AGL_SEARXNG_URL=http://localhost:8888
```

Mount a settings file into the container. Formats live under `search:` in `settings.yml`. The documented default list is only `html`. Add `json` under `search.formats`. Adding `json` enables JSON search. Leave `html` in the list so the normal page still works.

JSON search is a GET. The query string carries `q` and `format=json`:

```text
GET /search?q=...&format=json
```

If format is unset, SearXNG returns 403. That is the usual miss when `json` was never added.

SearXNG search API: https://docs.searxng.org/dev/search_api.html

Settings fragment:

```text
search:
  formats:
    - html
    - json
```

Run line, as sample text only. This mockup did not start Docker and did not pull a model:

```text
docker run --name searxng -p 8888:8080 searxng/searxng
```

Add a volume mount on that same run so the container reads your settings file instead of the image default. Keep the host port at 8888 and the container port at 8080.

Tavily is the fallback, and only when SearXNG is missing and `TAVILY_API_KEY` is set. The free plan is 1,000 credits a month. No credit card. Basic search is 1 credit. The credits page has a card named "Get your free API key". Take the key from that card and store it in `TAVILY_API_KEY`. Keep the key out of git and out of this file.

Tavily credits: https://docs.tavily.com/documentation/api-credits.md

The samples above assume this order:

1. SearXNG reachable: use SearXNG.
2. SearXNG missing and `TAVILY_API_KEY` set: use Tavily.
3. Neither: do not invent a source. Every claim says "Data not available."

When you try it for real:

1. Write `settings.yml` and add `json` under `search.formats`.
2. Start `searxng/searxng` with host 8888 mapped to container 8080, and mount that settings file.
3. Set `AGL_SEARXNG_URL=http://localhost:8888`.
4. Request `GET /search?q=test&format=json` and expect JSON, not 403.
5. Or skip SearXNG, set `TAVILY_API_KEY` from the free-key card, and stay inside 1,000 credits a month.

## SDK tool check

google-antigravity 0.1.23 can register a custom tool. Pass a callable in `tools=` on `LocalOpenAIAgentConfig`. Confirmed with the installed copy in `C:\Users\veere\source\repos\local-antigravity\venv` (`importlib.metadata.version("google-antigravity")` is `0.1.23`).

`C:\Users\veere\source\repos\local-antigravity\venv\Lib\site-packages\google\antigravity\connections\local\local_openai_connection_config.py` lines 43-50. The `tools` parameter is line 50:

```text
  def __init__(
      self,
      *,
      model: str | types.ModelTarget | None = None,
      base_url: str | None = None,
      system_instructions: str | types.SystemInstructions | None = None,
      capabilities: types.CapabilitiesConfig | None = None,
      tools: list[Callable[..., Any]] | None = None,
```

`C:\Users\veere\source\repos\local-antigravity\venv\Lib\site-packages\google\antigravity\agent.py` lines 217-219. `ToolRunner` gets `config._get_all_custom_tools()`:

```text
      self._tool_runner = tool_runner.ToolRunner(
          tools=self._config._get_all_custom_tools()
      )
```

`C:\Users\veere\source\repos\local-antigravity\venv\Lib\site-packages\google\antigravity\connections\connection.py` lines 301-330. `_get_all_custom_tools` keeps callables. The name is `__name__` (or the class name when `__name__` is missing). Subagent tools are included in the same walk:

```text
  def _get_all_custom_tools(self) -> list[Callable[..., Any]]:
    """Returns all callable custom tools across the main agent and subagents."""
    tools: list[Callable[..., Any]] = []
    seen_names: dict[str, Callable[..., Any]] = {}
    for t in self.tools or []:
      if callable(t):
        name = getattr(t, "__name__", None) or type(t).__name__
        if name in seen_names:
          if seen_names[name] != t:
            raise ValueError(
                f"Duplicate custom tool name '{name}' detected across agent"
                " and subagent configurations."
            )
        else:
          seen_names[name] = t
          tools.append(t)
    for sub in self.subagents or []:
      for tool in sub.tools or []:
        if callable(tool):
          name = getattr(tool, "__name__", None) or type(tool).__name__
          if name in seen_names:
            if seen_names[name] != tool:
              raise ValueError(
                  f"Duplicate custom tool name '{name}' detected across agent"
                  f" and subagent '{sub.name}' configurations."
              )
          else:
            seen_names[name] = tool
            tools.append(tool)
    return tools
```

`C:\Users\veere\source\repos\local-antigravity\venv\Lib\site-packages\google\antigravity\connections\local\local_openai_connection_test.py` lines 251-271. `test_tools_forwarded_to_strategy` passes `tools=[custom_lookup]` and the harness proto includes `custom_lookup`:

```text
  def test_tools_forwarded_to_strategy(self):
    """Verify custom tools are forwarded to strategy and included in harness proto."""

    def custom_lookup(query: str) -> str:
      """Looks up a query."""
      return query

    config = local_openai_connection_config.LocalOpenAIAgentConfig(
        base_url="http://localhost:11434/v1",
        model="llama3.1",
        tools=[custom_lookup],
    )
    t_runner = tool_runner_mod.ToolRunner(tools=config._get_all_custom_tools())
    strategy = config.create_strategy(
        tool_runner=t_runner,
        hook_runner=mock.MagicMock(),
    )
    self.assertEqual(strategy._tools, [custom_lookup])
    h_cfg = strategy._build_harness_config()
    tool_names = [t.name for t in h_cfg.tools]
    self.assertIn("custom_lookup", tool_names)
```

Part B can register `verify_claims` the same way: a callable named `verify_claims` in `tools=` on `LocalOpenAIAgentConfig`. The SDK will pick up that name.

Today `C:\Users\veere\source\repos\local-antigravity\.worktrees\v1-verifier\agl\app\agent.py` does not pass `tools=`. Re-checked in this worktree. The Gemma rule is line 159, not an older line. It still sets `CapabilitiesConfig(enabled_tools=[])` when `gemma` is in the model name. That rule stays. This mockup does not edit the file.

```text
    # Disable tools only if using Gemma under Ollama (which does not support Ollama tool schema)
    capabilities = CapabilitiesConfig(enabled_tools=[]) if "gemma" in model.lower() else None

    agent_config = LocalOpenAIAgentConfig(
        model=model,
        base_url=base_url,
        workspaces=[workspace_dir],
        policies=[policy.allow_all()],
        capabilities=capabilities,
    )
```

