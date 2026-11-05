#!/usr/bin/env bash
set -e

# Change directory to script location
cd "$(dirname "$0")"

# Find python3 or python
if command -v python3 &>/dev/null; then
    PYTHON_BIN="python3"
elif command -v python &>/dev/null; then
    PYTHON_BIN="python"
else
    echo "[ERROR] Python was not found in your system PATH."
    echo "Please install Python (3.11, 3.12, or 3.13):"
    echo "  macOS: brew install python@3.12"
    echo "  Linux: sudo apt update && sudo apt install -y python3 python3-venv"
    exit 1
fi

exec "$PYTHON_BIN" run.py "$@"
