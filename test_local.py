import asyncio
import os
import sys

# Load environment variables from .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from google.antigravity import Agent, LocalOpenAIAgentConfig
from google.antigravity.types import CapabilitiesConfig

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

async def main():
    base_url = os.environ.get("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
    model = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LOCAL_LLM_MODEL", "gemma2:27b")
    
    # Gemma models in Ollama do not support tool calling schema; disable tools if running gemma
    capabilities = CapabilitiesConfig(enabled_tools=[]) if "gemma" in model.lower() else None
    
    config = LocalOpenAIAgentConfig(
        model=model,
        base_url=base_url,
        capabilities=capabilities,
    )
    
    print(f"Connecting local Antigravity Agent to: {base_url}")
    print(f"Active Model: {model}")
    async with Agent(config) as agent:
        prompt = "What files are in the current directory?"
        print(f"Prompt: '{prompt}'\n")
        print("--- Response Stream ---")
        response = await agent.chat(prompt)
        async for chunk in response:
            print(chunk, end="", flush=True)
        print("\n--- End of Stream ---")

if __name__ == "__main__":
    asyncio.run(main())
