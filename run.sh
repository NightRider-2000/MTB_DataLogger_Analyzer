#!/bin/bash
# MTB DataLogger Analyzer launcher
# Uses Python 3.12 venv to avoid macOS libexpat compatibility issues with Python 3.14

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
PYTHON="/opt/homebrew/bin/python3.12"

# Create venv if it doesn't exist
if [ ! -d "$VENV" ]; then
    echo "Creating virtual environment with Python 3.12..."
    if ! command -v "$PYTHON" &>/dev/null; then
        echo "Python 3.12 not found. Installing via Homebrew..."
        brew install python@3.12
    fi
    "$PYTHON" -m venv "$VENV"
    echo "Installing dependencies..."
    "$VENV/bin/pip" install --quiet matplotlib pyserial
    echo "Done."
fi

exec "$VENV/bin/python" "$SCRIPT_DIR/MTB_DataLog_Analyze.py" "$@"
