"""The one default base URL and the env reads for it. The Layer contract in docs/ARCHITECTURE.md
puts "env and config reads" here, so this is the one place the Ollama default host is written."""
import os

OLLAMA_BASE_URL = "http://localhost:11434"  # the default Ollama host, written once for the whole repo
LLM_BASE_URL = OLLAMA_BASE_URL + "/v1"      # the OpenAI-compatible default, derived, never typed out


def llm_base_url(env=os.environ):
    """LOCAL_LLM_BASE_URL, or the derived /v1 default."""
    return env.get("LOCAL_LLM_BASE_URL", LLM_BASE_URL)


def ollama_api_base(env=os.environ):
    """OLLAMA_API_BASE, or the default Ollama host."""
    return env.get("OLLAMA_API_BASE", OLLAMA_BASE_URL)
