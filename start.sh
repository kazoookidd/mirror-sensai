#!/usr/bin/env bash
set -e

if [ ! -d ".venv" ]; then
    echo "Error: virtual environment not found. Run ./install.sh first."
    exit 1
fi

if [ ! -f ".env" ]; then
    echo "Error: .env not found. Run ./install.sh first, or copy .env.example to .env."
    exit 1
fi

source .venv/bin/activate
python3 chatbot.py "$@"