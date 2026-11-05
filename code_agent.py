#!/usr/bin/env python3
"""
=============================================================================
 Google Antigravity Local - Developer Coding Agent CLI & Interactive Shell
=============================================================================
An autonomous, local pair-programmer powered by google-antigravity and Ollama.
Equipped with the 3-Tier Memory Fabric:
  - Graphify (AST Knowledge Graph)
  - LLMWiki (Karpathy-style canonical topic pages)
  - SQLite Hybrid Memory Engine (BM25 + Semantic Cosine Fusion)

Usage:
  # 1. Interactive Coding Shell (pairs with you in the workspace):
  python code_agent.py --workspace ./workspace

  # 2. Interactive Shell with Memory Retrieval augmented:
  python code_agent.py --with-memory

  # 3. One-Shot Autonomous Task:
  python code_agent.py --task "Build a FastAPI REST API with SQLite" --with-memory

  # 4. Specify Model:
  python code_agent.py --model qwen2.5:14b
=============================================================================
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import task_report

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

Agent = LocalOpenAIAgentConfig = policy = CapabilitiesConfig = None


def _load_sdk():
    """Import the SDK lazily so --help works without it."""
    global Agent, LocalOpenAIAgentConfig, policy, CapabilitiesConfig
    try:
        from google.antigravity import Agent, LocalOpenAIAgentConfig
        from google.antigravity.hooks import policy
        from google.antigravity.types import CapabilitiesConfig
    except ImportError:
        print("\n❌ [ERROR] Missing dependency: 'google-antigravity' is not installed.")
        print("👉 Run: pip install -r requirements.txt\n")
        sys.exit(1)

# Memory engine import
try:
    from memory import MemoryDatabase, EmbeddingProvider, MemorySearcher, WIKI_DIR
    HAS_MEMORY = True
except ImportError:
    HAS_MEMORY = False


def list_workspace_files(workspace_dir: str):
    """List relative file paths in the workspace directory."""
    files = []
    for root, _, filenames in os.walk(workspace_dir):
        for f in filenames:
            rel = os.path.relpath(os.path.join(root, f), workspace_dir)
            files.append(rel)
    return sorted(files)


def get_memory_context(query: str, limit: int = 2) -> str:
    """Retrieve top-K memory chunks formatted for prompt context injection."""
    if not HAS_MEMORY:
        return ""
    try:
        db = MemoryDatabase()
        embedder = EmbeddingProvider()
        searcher = MemorySearcher(db, embedder)
        results = searcher.search(query, limit=limit)
        if not results:
            return ""

        chunks_text = []
        for res in results:
            content = res['content'].strip()
            if len(content) > 1200:
                content = content[:1200] + "\n... [truncated for token conservation]"
            chunks_text.append(
                f"[{res['category'].upper()}: {res['title']} ({res['path']}#L{res['start_line']}-L{res['end_line']})]\n"
                f"{content}"
            )
        return "\n\n<relevant_project_memory>\n" + "\n---\n".join(chunks_text) + "\n</relevant_project_memory>\n\n"
    except Exception:
        return ""


async def execute_task(agent, prompt: str, workspace_dir: str, with_memory: bool = False):
    """Execute a single coding prompt through the agent with streaming output."""
    memory_section = get_memory_context(prompt, limit=2) if with_memory else ""

    full_prompt = (
        f"{memory_section}"
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


async def run_interactive_session(base_url: str, model: str, workspace_dir: str, with_memory: bool = False):
    """Run an interactive pair-programming session with the local agent."""
    _load_sdk()
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
    print(f" • Memory Fabric   : {'ACTIVE (Auto-Retrieval Enabled)' if with_memory else 'AVAILABLE (/memory, /wiki)'}")
    print("=" * 76)
    print(" Type your coding request below (e.g., 'Create a calculator CLI in Python').")
    print(" Commands: /memory <query>, /wiki [topic], /files, /clear, /help, exit/quit")
    print("=" * 76 + "\n")

    while True:
        async with Agent(config) as agent:
            if await _chat_loop(agent, workspace_dir, with_memory):
                print("\n🧹 Conversation cleared. Fresh session started.\n")
                continue
            return


async def _chat_loop(agent, workspace_dir: str, with_memory: bool) -> bool:
    """Run the REPL; return True if /clear was requested (caller restarts the session)."""
    while True:
        try:
            user_input = input("CodeAgent [You] > ").strip()
            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "q"]:
                print("\n👋 Happy coding! All files saved in workspace.\n")
                return False

            if user_input.lower() == "/clear":
                return True

            if user_input.lower() == "/files":
                files = list_workspace_files(workspace_dir)
                print(f"\n📂 Files currently in {workspace_dir} ({len(files)} total):")
                if not files:
                    print("   (Workspace is currently empty)")
                for f in files:
                    print(f"   - {f}")
                print()
                continue

            if user_input.lower().startswith("/memory"):
                query = user_input[7:].strip()
                if not query:
                    print("\nUsage: /memory <search query>\n")
                    continue
                if not HAS_MEMORY:
                    print("\nMemory engine not available.\n")
                    continue
                db = MemoryDatabase()
                embedder = EmbeddingProvider()
                searcher = MemorySearcher(db, embedder)
                results = searcher.search(query, limit=3)
                print("\n" + "-" * 60)
                print(f"🔍 Memory Search: '{query}'")
                print("-" * 60)
                if not results:
                    print("No relevant memory found.")
                for i, r in enumerate(results, start=1):
                    print(f"[{i}] [{r['category'].upper()}] {r['title']} ({r['path']}#L{r['start_line']}-L{r['end_line']})")
                    for l in r["content"].strip().splitlines()[:4]:
                        print(f"    | {l}")
                print("-" * 60 + "\n")
                continue

            if user_input.lower().startswith("/wiki"):
                parts = user_input.split(maxsplit=1)
                topic = parts[1].strip() if len(parts) > 1 else None
                if not topic:
                    print("\n📚 Available Wiki Topics (.wiki/):")
                    if WIKI_DIR.is_dir():
                        for p in sorted(WIKI_DIR.glob("*.md")):
                            print(f"   - {p.stem}")
                    print("Usage: /wiki <topic>\n")
                    continue
                target = WIKI_DIR / f"{topic}.md"
                if not target.exists():
                    matches = [p for p in WIKI_DIR.glob("*.md") if topic.lower() in p.stem.lower()]
                    target = matches[0] if matches else None
                if target and target.exists():
                    print("\n" + "=" * 60)
                    print(f"📖 Wiki: {target.stem.upper()}")
                    print("=" * 60)
                    print(target.read_text(encoding="utf-8"))
                    print("=" * 60 + "\n")
                else:
                    print(f"\nTopic '{topic}' not found in .wiki/\n")
                continue

            if user_input.lower() == "/help":
                print("\n💡 Available Commands & Tips:")
                print("   - Type any natural language task: 'Create app.py with Flask'")
                print("   - '/memory <query>' : Search project memory (BM25 + Vector)")
                print("   - '/wiki [topic]'   : Read canonical domain knowledge pages")
                print("   - '/files'          : View all files created so far in workspace")
                print("   - '/clear'          : Reset the conversation (fresh agent session)")
                print("   - 'exit'            : Quit the coding session\n")
                continue

            print("\nCodeAgent [Local LLM] > ", end="", flush=True)
            await execute_task(agent, user_input, workspace_dir, with_memory=with_memory)

        except (KeyboardInterrupt, EOFError):
            print("\n\n👋 Exiting session.\n")
            return False
        except Exception as exc:
            print(f"\n❌ Error during task execution: {exc}\n")


async def run_one_shot(base_url: str, model: str, workspace_dir: str, task: str, with_memory: bool = False):
    """Run a single autonomous task from CLI arguments and exit."""
    _load_sdk()
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
    print(f" • Memory   : {'ENABLED' if with_memory else 'OFF'}")
    print("=" * 76 + "\n")

    before = task_report.snapshot(workspace_dir)
    async with Agent(config) as agent:
        await execute_task(agent, task, workspace_dir, with_memory=with_memory)

    created, changed = task_report.summarize(before, task_report.snapshot(workspace_dir))
    print("\n".join(task_report.render(workspace_dir, list_workspace_files(workspace_dir), created, changed)) + "\n")


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
    parser.add_argument(
        "--with-memory",
        action="store_true",
        help="Augment tasks with relevant project memory from SQLite hybrid store.",
    )

    args = parser.parse_args()

    if args.task:
        asyncio.run(run_one_shot(args.base_url, args.model, args.workspace, args.task, with_memory=args.with_memory))
    else:
        asyncio.run(run_interactive_session(args.base_url, args.model, args.workspace, with_memory=args.with_memory))


if __name__ == "__main__":
    main()
