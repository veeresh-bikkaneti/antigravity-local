#!/usr/bin/env bash
set -e

echo "==================================================="
echo " Google Antigravity Local Setup (macOS / Linux)"
echo "==================================================="

# Check Python installation
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] python3 is not installed or not in PATH."
    echo "Please install Python 3.11, 3.12, or 3.13."
    exit 1
fi

# Create virtual environment if not present
if [ ! -d "venv" ]; then
    echo "[1/3] Creating virtual environment in ./venv..."
    python3 -m venv venv
else
    echo "[1/3] Existing virtual environment found in ./venv."
fi

# Activate virtual environment
source venv/bin/activate

# Upgrade pip and install requirements
echo "[2/3] Installing dependencies from requirements.txt..."
pip install --upgrade pip --quiet
pip install -r requirements.txt

# Setup environment variables file
if [ ! -f ".env" ]; then
    echo "[3/3] Copying .env.example to .env..."
    cp .env.example .env
else
    echo "[3/3] Existing .env file found."
fi

echo ""
echo "==================================================="
echo " Setup Complete!"
echo "==================================================="
echo "To get started:"
echo "  1. Activate venv:  source venv/bin/activate"
echo "  2. Start Ollama:   ollama run qwen2.5:14b"
echo "  3. Run test:       python test_local.py"
echo "  4. Run agent:      python agent_with_workspace.py"
echo "==================================================="
