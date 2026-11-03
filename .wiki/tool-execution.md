# Tool Execution & Safety Policies

## 1. Tool Call Schema
The Antigravity SDK routes tool calls via the OpenAI function-calling format to Ollama:
- `create_file`:
  - Required parameters: `Path` (string), `Content` (string), `Overwrite` (boolean).
  - Note: Case-sensitivity matters. `Path` and `Content` are capitalized in the local harness schema.

## 2. Safety Policies
- **`policy.allow_all()`**: Enabled in `agent_with_workspace.py` and `code_agent.py` to allow the local autonomous agent to create and modify files inside the designated workspace without interactive prompt freezes.
- **Path Sanitization**: Relative paths are resolved strictly against `WORKSPACE_DIR` (default: `./workspace`). Attempts to break out of workspace are blocked by the harness boundary.

## 3. Model Compatibility Caveat
- `qwen2.5:14b` natively parses OpenAI function calls and executes tools cleanly.
- `gemma2:27b` in Ollama does NOT support tools schema (`registry.ollama.ai/library/gemma2:27b does not support tools`). For Gemma, tool execution must be disabled via `capabilities=CapabilitiesConfig(enabled_tools=[])`.
