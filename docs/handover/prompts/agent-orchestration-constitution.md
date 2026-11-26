# Agent orchestration constitution (generic, copy into any project)

Paste the block below into a project's AGENTS.md, CLAUDE.md or into any agent prompt. It is written to cut token use without lowering quality.

```markdown
## Orchestration constitution

Cheap models do the heavy work, a mid-tier reviewer model accepts it, and the lead only plans and verifies.

### Tiers
| Tier | Who | Does | Never does |
|------|-----|------|------------|
| Lead | the main session | splits the task, writes briefs, runs the gate, integrates, reports | writes the bulk code or prose itself |
| Worker | the cheapest model that can clear the gate (cheaper models) | builds, writes, searches, tests | reviews its own work, merges, pushes |
| Reviewer | mid-tier model (one step up from the worker) | reads the evidence pack, then returns ACCEPT or REJECT with reasons | rewrites the work, reads the whole repo |

Escalate a worker to the next tier up only after it fails the same gate twice. Never start on a higher tier "to be safe".

### Size the effort to the task
- Tiny (one file, under 20 changed lines): 1 worker, then the deterministic gate, then 1 reviewer verdict.
- Normal: 2 to 4 workers in parallel on separate files or batches, then the gate, then 1 reviewer.
- Large or risky (security, data loss, public API): 3 to 5 workers plus 2 reviewer seats (spec compliance, quality).
- Don't use multiple agents when one call answers the question.

### Every worker brief has
Objective (one sentence), output format, the files it may write and the files it must not touch, `path:line` pointers instead of pasted files, the exact verify command, a token cap, and a stop rule (return partial results at the cap).

### Token rules
1. State the total cap and an estimate up front. Stop and ask the user at 80 percent.
2. Run the cheap deterministic gates first (tests, linters, check scripts). A reviewer sees the work only after they pass.
3. Workers return a summary of 150 words or fewer, plus file paths and the commit SHA. They don't paste full files or logs back.
4. The reviewer's evidence pack is only the diff, the gate output and the spec section. It never gets the repo or the chat history.
5. Run at most 2 review rounds. A second REJECT stops the run and goes to the user.
6. Never re-read a file the lead has already summarized. Pass the summary instead.
7. Report tokens and cost per tier with each result.
8. Subagents can't see their own counter. After each one returns, the lead reads its reported usage and adds it to a running total. Once the total hits 80 percent of the cap, the lead spawns nothing more and asks. A worker that overran gets a smaller brief next time, never a bigger cap.
9. The cap in the prompt is the cap. An agent never raises it on its own.

### Quality floor (not traded for tokens)
- The full test suite and the check scripts stay green. Never weaken an assertion.
- The reviewer ACCEPTs only against written pass/fail lines.
- The lead re-runs the gate itself before it says "done".
```

## Why this is the rule (sources)
- Anthropic's own research agent uses the orchestrator-worker pattern: "a lead agent coordinates the process while delegating to specialized subagents". [multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) [Confidence: High | Vote: 3/3, together with the next two]
- The pattern is described as "a central LLM dynamically breaks down tasks, delegates them to worker LLMs, and synthesizes their results". [building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- Each subagent "runs in its own context window" and "returns only the summary". [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)
- Model choice: "pair a lower-cost model with a frontier model so that most tokens are billed at the lower rate". [choosing a model](https://platform.claude.com/docs/en/about-claude/models/choosing-a-model), plus "route tasks to faster, lower-cost models" (quote trimmed to drop the model name) [subagents](https://code.claude.com/docs/en/sub-agents) and cheaper-model routing in [building effective agents](https://www.anthropic.com/engineering/building-effective-agents). [Confidence: High | Vote: 3/3]
- Cost: "multi-agent systems use about 15x more tokens than chats", so match the effort to the task value. [multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) [Confidence: Moderate | Vote: 1 primary]
- Effort scaling: "Simple fact-finding requires just 1 agent with 3-10 tool calls". [multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system). On complexity: add it "only when it demonstrably improves outcomes". [building effective agents](https://www.anthropic.com/engineering/building-effective-agents) [Confidence: Moderate | Vote: 2/2]
- Briefs: "Each subagent needs an objective, an output format, guidance on the tools and sources to use, and clear task boundaries". [multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) [Confidence: Moderate | Vote: 1 primary]
- Review loops need "stopping conditions (such as a maximum number of iterations)". [building effective agents](https://www.anthropic.com/engineering/building-effective-agents) [Confidence: Moderate | Vote: 1 primary]
- Not verified: the cookbook notebooks for orchestrator-workers and evaluator-optimizer. One hit a rate limit and the other returned no text.
- Inferred, not sourced: the escalate-after-two-failures rule, the 150-word return, the 20-line "tiny" bar and running gates before the reviewer. These are my design choices, built from the token overruns in this project.

Sources read on 2026-11-15. Model class names change, so say "cheaper models" and "mid-tier reviewer" rather than a model name.
