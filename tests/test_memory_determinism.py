"""Regression: pure-python fallback embeddings must be identical across processes.

Flaw: _pure_python_embed used builtin hash(), which is salted per process
(PYTHONHASHSEED). Vectors stored at index time never match query vectors from a
later process, so the semantic tier of hybrid search is noise when Ollama has no
embedding model.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT = "hybrid memory retrieval fuses lexical and semantic ranking"

EMBED = f"""
import json, sys
sys.path.insert(0, {str(ROOT)!r})
import memory
print(json.dumps(memory.EmbeddingProvider._pure_python_embed(None, {TEXT!r})))
"""

STORE = f"""
import json, sys, sqlite3
sys.path.insert(0, {str(ROOT)!r})
import memory
db = memory.MemoryDatabase(memory.Path(sys.argv[1]))
emb = memory.EmbeddingProvider._pure_python_embed(None, {TEXT!r})
with db.get_connection() as c:
    c.execute("INSERT INTO documents (id,path,title,category,mtime,chunk_count) VALUES (1,'a.md','A','doc',0,1)")
    c.execute("INSERT INTO chunks (id,doc_id,chunk_index,start_line,end_line,content,embedding) VALUES (1,1,0,1,1,?,?)", ({TEXT!r}, json.dumps(emb)))
"""

SEARCH = f"""
import json, sys
sys.path.insert(0, {str(ROOT)!r})
import memory
e = memory.EmbeddingProvider(base_url="http://127.0.0.1:9")
s = memory.MemorySearcher(memory.MemoryDatabase(memory.Path(sys.argv[1])), e)
print(json.dumps(s.search("zzzz " + {TEXT!r}.replace("lexical", "")  , limit=1)))
"""


def run(code, seed, *args):
    env = {**os.environ, "PYTHONHASHSEED": str(seed), "OLLAMA_API_BASE": "http://127.0.0.1:9"}
    out = subprocess.run([sys.executable, "-c", code, *args], env=env,
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


class FallbackEmbeddingDeterminism(unittest.TestCase):
    def test_same_text_same_vector_across_processes(self):
        a, b = json.loads(run(EMBED, 1)), json.loads(run(EMBED, 2))
        self.assertEqual(a, b)

    def test_index_in_one_process_search_in_another(self):
        with tempfile.TemporaryDirectory() as d:
            db = str(Path(d) / "i.sqlite")
            run(STORE, 1, db)
            top = json.loads(run(SEARCH, 2, db))[0]
            # near-identical text must score high; salted hashes give ~0
            self.assertGreater(top["vector_sim"], 0.8)


if __name__ == "__main__":
    unittest.main()
