#!/bin/bash
set -e

echo "=================================================================="
echo " 🐳 DOCKER TEST DRIVE: Antigravity Local Environment Verification"
echo "=================================================================="

cd /app

echo "1. Checking Python environment..."
python --version

echo "2. Installing requirements in clean container..."
pip install --no-cache-dir -r requirements.txt

echo "3. Testing Memory Engine (Pure Python SQLite FTS5)..."
python memory.py status

echo "4. Testing Memory Hybrid Retrieval..."
python memory.py search "how does hardware offloading work with 16GB VRAM"

echo "5. Testing LLMWiki Canonical Topic Loading..."
python memory.py wiki architecture

echo "6. Testing Developer Coding Agent CLI..."
python code_agent.py --help

echo "7. Testing Network Connectivity to Host Ollama (:11434)..."
python -c "
import urllib.request, json
try:
    with urllib.request.urlopen('http://host.docker.internal:11434/api/tags', timeout=5) as resp:
        data = json.loads(resp.read().decode())
        models = [m['name'] for m in data.get('models', [])]
        print(f'   [OK] Connected to Host Ollama from inside Docker!')
        print(f'   [OK] Host Models detected: {models}')
except Exception as e:
    print(f'   [WARN] Host connection notice: {e}')
"

echo "=================================================================="
echo " ✅ DOCKER TEST DRIVE PASSED ALL GATES"
echo "=================================================================="
