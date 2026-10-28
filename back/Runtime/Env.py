"""
Loads the project's .env file, once, before anything reads its settings.

Several modules read their settings when they are imported (Agents/ReAct.py,
Cache/SemanticCache.py, Memories/Compression.py...), so the entry points
(Chatbot.py, Server.py) call load_env() BEFORE importing them. No other module
loads the file: what a test or a script imports never depends on a local .env.

The file is found from this module, not from the current directory, and a
variable already set in the environment (docker compose, the shell) always
wins over the file.
"""

from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def load_env(path: Path = ENV_PATH) -> bool:
    """Load `path` into os.environ without overriding what is already set.
    Returns False when there is no such file (every setting has a default)."""
    return load_dotenv(path, override=False)
