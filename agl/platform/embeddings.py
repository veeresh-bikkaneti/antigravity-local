"""
agl/platform/embeddings.py - the Ollama embedding adapter: the installed-model probe and
the embed call with the pure-python fallback, moved out of memory.py in Phase 6a. The
base URL is always passed in; HTTP goes through the one helper in agl/platform/http.py.
"""
import json
import os

from agl.platform import config, http
from agl.core import memory as core_memory


class EmbeddingProvider:
    """Provides vector embeddings via local Ollama or pure-Python TF-IDF fallback."""

    def __init__(self, base_url: str = None):
        self.base_url = (base_url if base_url is not None else config.OLLAMA_BASE_URL).rstrip("/")
        self.ollama_model = self._detect_ollama_embedding_model()
        self.mode = f"ollama ({self.ollama_model})" if self.ollama_model else "pure_python_tfidf"
        self.fell_back = False  # set when an Ollama call failed and a fallback vector was returned

    def _detect_ollama_embedding_model(self) -> str | None:
        """Check if Ollama has a known embedding model installed."""
        if os.getenv("LOCAL_LLM_BACKEND") == "openai":
            return None  # run.py found a non-Ollama server: there is no /api/tags to ask, so use the built-in vectors quietly
        try:
            data = http.get_json(f"{self.base_url}/api/tags", timeout=1.5, headers={"User-Agent": "antigravity-memory"})
            models = [m.get("name", "") for m in data.get("models", [])]
            # Look for common embedding models
            candidates = ["nomic-embed-text", "all-minilm", "bge-m3", "bge-small", "snowflake-arctic-embed"]
            for cand in candidates:
                for m in models:
                    if cand in m:
                        return m
        except Exception:
            pass
        return None

    def embed_text(self, text: str) -> list[float]:
        """Generate embedding vector for text."""
        if self.ollama_model:
            try:
                payload = json.dumps({"model": self.ollama_model, "prompt": text[:2000]}).encode("utf-8")
                data = http.get_json(f"{self.base_url}/api/embeddings", timeout=5, headers={"Content-Type": "application/json"}, data=payload)
                emb = data.get("embedding")
                if emb and isinstance(emb, list):
                    return emb
            except Exception:
                pass
            self.fell_back = True

        # Fallback to pure Python feature vectorizer
        return self._pure_python_embed(text)

    def _pure_python_embed(self, text: str, dimensions: int = 128) -> list[float]:
        """Deterministic, lightweight 128-dim hashing vectorizer with L2 normalization."""
        return core_memory._pure_python_embed(text, dimensions)
