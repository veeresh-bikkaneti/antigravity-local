import argparse
import asyncio
import os
import sys

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
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))  # next to this script, not the cwd
except ImportError:
    pass

try:
    from agl.app.agent_session import resolve_model  # Phase 6c: the one model/base-url path for the side scripts
except ImportError:  # a bare copy of this script (no agl/ next to it, as tests copy it) must still answer
    def resolve_model(cli_model, *, environ, default_base_url):
        return (cli_model or environ.get("LOCAL_LLM_MODEL") or None,
                environ.get("LOCAL_LLM_BASE_URL", default_base_url))

_parser = argparse.ArgumentParser(description="Streaming smoke test against the local LLM server.")
_parser.add_argument("model", nargs="?", default=None, help="Model name (default: $LOCAL_LLM_MODEL, saved by run.py).")
ARGS = _parser.parse_args()  # before the SDK import so --help works without it
model, _ = resolve_model(ARGS.model, environ=os.environ, default_base_url=None)
if not model:
    print("No model chosen yet. Run python run.py first, or pass --model.")
    sys.exit(2)

# Verify dependencies
try:
    from google.antigravity import Agent, LocalOpenAIAgentConfig
    from google.antigravity.types import CapabilitiesConfig
except ImportError:
    print("\n❌ [ERROR] Missing dependency: 'google-antigravity' is not installed.")
    print("👉 Run: pip install -r requirements.txt\n")
    sys.exit(1)

async def main():
    from agl.platform import config  # the one default lives in agl.platform.config
    model, base_url = resolve_model(ARGS.model, environ=os.environ, default_base_url=config.LLM_BASE_URL)

    # Gemma models in Ollama do not support tool calling schema; disable tools if running gemma
    capabilities = CapabilitiesConfig(enabled_tools=[]) if "gemma" in model.lower() else None
    
    config = LocalOpenAIAgentConfig(
        model=model,
        base_url=base_url,
        capabilities=capabilities,
    )
    
    print("==================================================")
    print(" Google Antigravity Local - Streaming Test")
    print("==================================================")
    print(f"Endpoint : {base_url}")
    print(f"Model    : {model}")
    print(f"Prompt   : 'What files are in the current directory?'\n")
    print("--- Response Stream ---")
    
    try:
        async with Agent(config) as agent:
            response = await agent.chat("What files are in the current directory?")
            async for chunk in response:
                print(chunk, end="", flush=True)
            print("\n--- End of Stream ---\n")
    except Exception as exc:
        print(f"\n❌ [ERROR] Connection or execution failure: {exc}")
        print("\n💡 Tip: Verify your local LLM server is active:")
        print(f"   - Is Ollama running? Run: ollama serve")
        print(f"   - Is the model downloaded? Run: ollama pull {model}")
        print(f"   - Is the endpoint correct? Current: {base_url}\n")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
