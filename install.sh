#!/usr/bin/env bash
set -e

echo "=== Sensai - Installation ==="

# --- Check Python version ---
PYTHON_BIN="python3"
if ! command -v $PYTHON_BIN &> /dev/null; then
    echo "Error: python3 is not installed."
    exit 1
fi

PYTHON_VERSION=$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
REQUIRED_VERSION="3.10"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "Error: Python $REQUIRED_VERSION or higher is required (found $PYTHON_VERSION)."
    exit 1
fi
echo "Python $PYTHON_VERSION detected. OK."

# --- Create virtual environment ---
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment (.venv)..."
    $PYTHON_BIN -m venv .venv
else
    echo "Virtual environment already exists, skipping creation."
fi

# --- Install dependencies ---
echo "Installing dependencies from requirements.txt..."
source .venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
deactivate

# --- Set up .env ---
if [ ! -f ".env" ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "-> Edit .env to set your MODEL and other options."
else
    echo ".env already exists, leaving it untouched."
fi

echo ""
echo "=== Installation complete ==="
echo "Next steps:"
echo "  1. Make sure Ollama is running (ollama serve)"
echo "  2. Pull the model set in .env (e.g. ollama pull llama3)"
echo "  3. Run ./start.sh"