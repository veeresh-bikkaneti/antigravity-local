"""Narrow tests for the platform config: each read takes an env mapping (never os.environ
directly, so the tests mutate nothing global), and the defaults derive from the one
Ollama host. Offline: pure functions of the mapping they are given."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from agl.platform import config  # noqa: E402


class LlmBaseUrl(unittest.TestCase):
    def test_reads_local_llm_base_url_from_the_env_mapping_it_is_given(self):
        self.assertEqual(config.llm_base_url({"LOCAL_LLM_BASE_URL": "http://127.0.0.1:1234/v1"}),
                         "http://127.0.0.1:1234/v1")

    def test_the_default_is_the_ollama_host_plus_v1(self):
        self.assertEqual(config.llm_base_url({}), config.OLLAMA_BASE_URL + "/v1")


class OllamaApiBase(unittest.TestCase):
    def test_reads_ollama_api_base_from_the_env_mapping_it_is_given(self):
        self.assertEqual(config.ollama_api_base({"OLLAMA_API_BASE": "http://127.0.0.1:11434"}),
                         "http://127.0.0.1:11434")

    def test_the_default_is_the_ollama_host(self):
        self.assertEqual(config.ollama_api_base({}), config.OLLAMA_BASE_URL)


if __name__ == "__main__":
    unittest.main()
