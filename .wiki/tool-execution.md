# Tool Execution & Safety Policies

## 1. Tool Call Schema
The Antigravity SDK routes tool calls via the OpenAI function-calling format to Ollama:
- `create_file`:
  - Required parameters: `Path` (string), `Content` (string), `Overwrite` (boolean).
  - Note: Case-sensitivity matters. `Path` and `Content` are capitalized in the local harness schema.

## 2. Safety Policies
- **`policy.allow_all()`**: Enabled in `agent_with_workspace.py` and `code_agent.py` so the local agent can create and modify files inside the workspace without freezing on interactive prompts.
- **Path Sanitization**: Relative paths resolve against `WORKSPACE_DIR` (default: `./workspace`). The harness blocks attempts to leave the workspace.

## 3. Model Compatibility Caveat
- `qwen2.5:14b` natively parses OpenAI function calls and executes tools.
- `gemma2:27b` in Ollama does NOT support tools schema (`registry.ollama.ai/library/gemma2:27b does not support tools`). For Gemma, tool execution must be disabled via `capabilities=CapabilitiesConfig(enabled_tools=[])`.

