import argparse
import asyncio
import os
import sys

import task_report

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Load environment variables from .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_parser = argparse.ArgumentParser(description="Local agent demo: creates index.html in the workspace.")
_parser.add_argument("model", nargs="?", default=None, help="Model name (default: $LOCAL_LLM_MODEL or qwen2.5:14b).")
ARGS = _parser.parse_args()  # before the SDK import so --help works without it

# Verify dependencies
try:
    from google.antigravity import Agent, LocalOpenAIAgentConfig
    from google.antigravity.hooks import policy
except ImportError:
    print("\n❌ [ERROR] Missing dependency: 'google-antigravity' is not installed.")
    print("👉 Run: pip install -r requirements.txt\n")
    sys.exit(1)

async def main():
    base_url = os.environ.get("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
    model = ARGS.model or os.environ.get("LOCAL_LLM_MODEL", "qwen2.5:14b")
    workspace_dir = os.environ.get(
        "WORKSPACE_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "workspace"),
    )
    os.makedirs(workspace_dir, exist_ok=True)
    
    config = LocalOpenAIAgentConfig(
        model=model,
        base_url=base_url,
        workspaces=[workspace_dir],
        policies=[policy.allow_all()],
    )
    
    print("==================================================")
    print(" Google Antigravity - Local Autonomous Agent")
    print("==================================================")
    print(f"Server Endpoint : {base_url}")
    print(f"Inference Model : {model}")
    print(f"Agent Workspace : {workspace_dir}")
    print("Security Policy : policy.allow_all() (Autonomous Mode)")
    print("Task            : Create index.html with a modern dark-mode toggle.\n")
    
    target_file = os.path.join(workspace_dir, "index.html")
    prompt = (
        f"Create an index.html file with a modern dark-mode toggle at path {target_file}. "
        "Call the write_to_file tool with TargetFile, CodeContent, and Overwrite=true."
    )
    
    before = task_report.snapshot(workspace_dir)
    try:
        async with Agent(config) as agent:
            response = await agent.chat(prompt)
            async for chunk in response:
                print(chunk, end="", flush=True)
            created, changed = task_report.summarize(before, task_report.snapshot(workspace_dir))
            if "index.html" in created + changed:
                print("\n\n✅ Agent task completed successfully.")
                print(f"📁 Output file generated: {target_file}")
            else:
                print("\n\n⚠️ The agent finished, but it did not create or change index.html.")
                print("Small local models sometimes answer without writing anything. Run the same command again.")
    except Exception as exc:
        print(f"\n❌ [ERROR] Agent execution failure: {exc}")
        print("\n💡 Troubleshooting Tips:")
        print(f"   - Tool calling models supported: nanbeige (4.1/2-16B), qwen2.5 (14b/32b), llama3.1:8b (not gemma2)")
        print(f"   - Is Ollama active? Run: ollama serve")
        print(f"   - Pull the model: Run: ollama pull {model}\n")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
