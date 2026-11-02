#!/usr/bin/env python3
"""
=============================================================================
 Google Antigravity Local - Developer Coding Agent CLI & Interactive Shell
=============================================================================
An autonomous, local pair-programmer powered by google-antigravity and Ollama.
Use it to write code, generate project scaffolds, refactor existing files,
and run unit tests completely on your local machine with 100% privacy.

Usage:
  # 1. Interactive Coding Mode (pairs with you in the specified workspace):
  python code_agent.py --workspace ./workspace

  # 2. One-Shot Task Mode (runs an autonomous task and exits):
  python code_agent.py --workspace ./workspace --task "Build a FastAPI REST API with SQLite"

  # 3. Specify Model (defaults to qwen2.5:14b or LOCAL_LLM_MODEL in .env):
  python code_agent.py --model qwen2.5:14b
=============================================================================
"""

import argparse
import asyncio
import os
import sys

# Load environment variables from .env if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Ensure UTF-8 console output on Windows to prevent charmap encoding errors
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from google.antigravity import Agent, LocalOpenAIAgentConfig
from google.antigravity.hooks import policy
from google.antigravity.types import CapabilitiesConfig


def list_workspace_files(workspace_dir: str):
    """List relative file paths in the workspace directory."""
    files = []
    for root, _, filenames in os.walk(workspace_dir):
        for f in filenames:
            rel = os.path.relpath(os.path.join(root, f), workspace_dir)
            files.append(rel)
    return sorted(files)


async def execute_task(agent: Agent, prompt: str, workspace_dir: str):
    """Execute a single coding prompt through the agent with streaming output."""
    full_prompt = (
        f"{prompt}\n\n"
        f"Workspace Directory: {os.path.abspath(workspace_dir)}\n"
        "Important Instructions:\n"
        "1. To create or modify files, call the `create_file` tool with parameters: "
        "`Path` (absolute path inside the workspace), `Content` (the complete file code), and `Overwrite=True`.\n"
        "2. Keep explanations concise and always execute the file creation tool directly."
    )
    response = await agent.chat(full_prompt)
    async for chunk in response:
        print(chunk, end="", flush=True)
    print("\n")


async def run_interactive_session(base_url: str, model: str, workspace_dir: str):
    """Run an interactive pair-programming session with the local agent."""
    os.makedirs(workspace_dir, exist_ok=True)

    capabilities = CapabilitiesConfig(enabled_tools=[]) if "gemma" in model.lower() else None
    config = LocalOpenAIAgentConfig(
        model=model,
        base_url=base_url,
        workspaces=[workspace_dir],
        policies=[policy.allow_all()],
        capabilities=capabilities,
    )

    print("\n" + "=" * 76)
    print(" 🚀 Google Antigravity - Local Developer Coding Shell")
    print("=" * 76)
    print(f" • Server Endpoint : {base_url}")
    print(f" • Active Model    : {model}")
    print(f" • Active Workspace: {os.path.abspath(workspace_dir)}")
    print(f" • Safety Policy   : policy.allow_all() (Autonomous Disk Access)")
    print("=" * 76)
    print(" Type your coding request below (e.g., 'Create a calculator CLI in Python').")
    print(" Commands: /files (list files), /help (show help), exit/quit (to exit)")
    print("=" * 76 + "\n")

    async with Agent(config) as agent:
        while True:
            try:
                user_input = input("CodeAgent [You] > ").strip()
                if not user_input:
                    continue

                if user_input.lower() in ["exit", "quit", "q"]:
                    print("\n👋 Happy coding! All files saved in workspace.\n")
                    break

                if user_input.lower() == "/files":
                    files = list_workspace_files(workspace_dir)
                    print(f"\n📂 Files currently in {workspace_dir} ({len(files)} total):")
                    if not files:
                        print("   (Workspace is currently empty)")
                    for f in files:
                        print(f"   - {f}")
                    print()
                    continue

                if user_input.lower() == "/help":
                    print("\n💡 Available Commands & Tips:")
                    print("   - Type any natural language task: 'Create app.py with Flask'")
                    print("   - '/files' : View all files created so far in workspace")
                    print("   - 'exit'   : Quit the coding session\n")
                    continue

                print("\nCodeAgent [Local LLM] > ", end="", flush=True)
                await execute_task(agent, user_input, workspace_dir)

            except (KeyboardInterrupt, EOFError):
                print("\n\n👋 Exiting session.\n")
                break
            except Exception as exc:
                print(f"\n❌ Error during task execution: {exc}\n")


async def run_one_shot(base_url: str, model: str, workspace_dir: str, task: str):
    """Run a single autonomous task from CLI arguments and exit."""
    os.makedirs(workspace_dir, exist_ok=True)

    capabilities = CapabilitiesConfig(enabled_tools=[]) if "gemma" in model.lower() else None
    config = LocalOpenAIAgentConfig(
        model=model,
        base_url=base_url,
        workspaces=[workspace_dir],
        policies=[policy.allow_all()],
        capabilities=capabilities,
    )

    print("\n" + "=" * 76)
    print(" 🎯 Google Antigravity - Autonomous Task Execution")
    print("=" * 76)
    print(f" • Endpoint : {base_url}")
    print(f" • Model    : {model}")
    print(f" • Workspace: {os.path.abspath(workspace_dir)}")
    print(f" • Task     : {task}")
    print("=" * 76 + "\n")

    async with Agent(config) as agent:
        await execute_task(agent, task, workspace_dir)

    files = list_workspace_files(workspace_dir)
    print("=" * 76)
    print(f"✅ Task completed. Workspace files ({len(files)}):")
    for f in files:
        print(f"   📁 {os.path.join(workspace_dir, f)}")
    print("=" * 76 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Google Antigravity Local Developer Coding Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--workspace", "-w",
        default=os.environ.get("WORKSPACE_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "workspace")),
        help="Target workspace directory where the agent reads and writes code.",
    )
    parser.add_argument(
        "--task", "-t",
        default=None,
        help="One-shot autonomous coding task. If omitted, starts interactive shell.",
    )
    parser.add_argument(
        "--model", "-m",
        default=os.environ.get("LOCAL_LLM_MODEL", "qwen2.5:14b"),
        help="Model name (e.g., qwen2.5:14b, llama3.1:8b, mistral-nemo).",
    )
    parser.add_argument(
        "--base-url", "-u",
        default=os.environ.get("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1"),
        help="OpenAI-compatible server endpoint (e.g., http://localhost:11434/v1).",
    )

    args = parser.parse_args()

    if args.task:
        asyncio.run(run_one_shot(args.base_url, args.model, args.workspace, args.task))
    else:
        asyncio.run(run_interactive_session(args.base_url, args.model, args.workspace))


if __name__ == "__main__":
    main()
