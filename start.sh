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
# ./start.sh --web [options]: web interface (X1) instead of the terminal
if [ "$1" = "--web" ]; then
    if [ ! -f "front/dist/index.html" ]; then
        echo "Error: web interface not built. Run ./install.sh, or: cd front && npm install && npm run build"
        exit 1
    fi
    shift
    exec python3 back/Server.py "$@"
fi
python3 back/Chatbot.py "$@"