# Architecture & Runtime Decoupling

## 1. System Philosophy
This repository runs Google Antigravity autonomous coding agents on local, air-gapped workstations without external cloud dependencies, billing accounts, or mandatory Google Cloud API keys.

## 2. Core Invariants
- **Decoupled LLM Backend**: `google-antigravity` communicates with Ollama via `LocalOpenAIConnectionStrategy` at `http://localhost:11434/v1/chat/completions`.
- **Harness Communication**: Agents interact with workspace files via a local background binary harness communicating over WebSockets using Protocol Buffers (`localharness_pb2`).
- **Open-Source Compatibility**: Compatible with custom builds of Google's Research AI Harness via `ANTIGRAVITY_HARNESS_PATH`.
- **Air-Gapped Operation**: No telemetry, model weights, or source code leave the local machine.

## 3. Session Topology
- **Antigravity IDE UI Session**: The upper chat panel in the Antigravity IDE is hosted by Google Cloud (Gemini Flash/Pro).
- **Local Agent Terminal Session**: The integrated terminal runs the local agent scripts (`run.py`, `code_agent.py`, `agent_with_workspace.py`), executing locally against Ollama.
- **Shared Memory Bridge**: Both environments share and read the same file-backed state (`CONTEXT_MEMORY.md`, `.wiki/`, `graphify-out/graph.json`, and `.memory/index.sqlite`).
