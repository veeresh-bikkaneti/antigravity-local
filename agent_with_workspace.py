import asyncio
import os
import sys

# Load environment variables from .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from google.antigravity import Agent, LocalOpenAIAgentConfig
from google.antigravity.hooks import policy

async def main():
    base_url = os.environ.get("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
    model = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LOCAL_LLM_MODEL", "qwen2.5:14b")
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
    print(" Local Google Antigravity Autonomous Agent")
    print("==================================================")
    print(f"Server Endpoint : {base_url}")
    print(f"Inference Model : {model}")
    print(f"Agent Workspace : {workspace_dir}")
    print("Security Policy : policy.allow_all() (Autonomous Mode)")
    print("Task            : Create index.html with a dark-mode toggle.\n")
    
    target_file = os.path.join(workspace_dir, "index.html")
    prompt = (
        f"Create an index.html file with a modern dark-mode toggle at path {target_file}. "
        "Call write_file or create_file with Path, Content, and Overwrite=True."
    )
    
    async with Agent(config) as agent:
        response = await agent.chat(prompt)
        async for chunk in response:
            print(chunk, end="", flush=True)
        print("\n\nAgent task completed.")

if __name__ == "__main__":
    asyncio.run(main())
