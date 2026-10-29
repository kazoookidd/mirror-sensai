"""
Entry point of the web interface [X1].

Serves front/ and a small HTTP API on top of the same backend as the CLI:
the web UI calls chat_turn, the accounts, the conversations and the settings
exactly as the terminal does. Usage (from the project root):

    ./start.sh --web [--host 127.0.0.1] [--port 8000] [any CLI option]
"""

import os
import uvicorn

from Runtime.Env import load_env

# Before the project imports below: some of them read their settings when imported.
load_env()

from Chatbot import build_parser
from Memories.Database import init_db
from Web.App import create_app

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = "8000"


def build_web_parser():
    parser = build_parser("Sensai web interface")
    parser.add_argument(
        "--host",
        default=os.getenv("WEB_HOST", DEFAULT_HOST),
        help="Address the web server listens on (overrides .env WEB_HOST). "
             "Keep 127.0.0.1 so the HR data stays on this machine"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=os.getenv("WEB_PORT", DEFAULT_PORT),
        help="Port of the web server (overrides .env WEB_PORT)"
    )
    return parser


def main():
    init_db()
    args = build_web_parser().parse_args()
    print(f"Sensai web interface: http://{args.host}:{args.port} (Ctrl+C to stop)")
    uvicorn.run(create_app(args), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
