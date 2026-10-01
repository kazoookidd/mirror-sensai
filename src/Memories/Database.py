import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "sensai.db"


def get_connection(db_path: str = None) -> sqlite3.Connection:
    """Open a SQLite connection with row access by column name."""
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str = None) -> None:
    """Create the users and messages tables if they don't exist yet.
    Safe to call on every startup."""
    conn = get_connection(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        # Current-state cache: at most one active summary per user.
        # Never a source of truth — always rebuildable from `messages`.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS summaries (
                user_id TEXT PRIMARY KEY,
                summary_text TEXT NOT NULL,
                covers_up_to_msg_id INTEGER NOT NULL,
                token_count INTEGER NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        # Append-only metrics log: one row per compression event.
        # Kept separate from `summaries` so state and history don't mix.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS compression_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                tokens_before INTEGER NOT NULL,
                tokens_after INTEGER NOT NULL,
                compression_ratio REAL NOT NULL,
                messages_compressed INTEGER NOT NULL,
                summary_token_count INTEGER NOT NULL,
                duration_seconds REAL NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        conn.commit()
    finally:
        conn.close()