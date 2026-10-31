"""
[R2] The HR document passages an answer was written from, kept with the answer: they are shown
under it after a reload too. They go when the message goes (ON DELETE CASCADE).
"""

import json
from .Database import get_connection

_CREATE = """
    CREATE TABLE IF NOT EXISTS message_sources (
        message_id INTEGER PRIMARY KEY,
        sources TEXT NOT NULL,
        FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
    )
"""
_BY_MESSAGE = """
    SELECT m.id, s.sources FROM messages m LEFT JOIN message_sources s ON s.message_id = m.id
    WHERE m.conversation_id = ? ORDER BY m.id
"""


def _connect():
    conn = get_connection()
    conn.execute(_CREATE)
    return conn


def save_sources(message_id: int, sources: list[dict]) -> None:
    if not sources:
        return
    conn = _connect()
    try:
        with conn:
            conn.execute("INSERT OR REPLACE INTO message_sources (message_id, sources) VALUES (?, ?)", (message_id, json.dumps(sources, ensure_ascii=False)))
    finally:
        conn.close()


def sources_by_position(conversation_id: int) -> list[list[dict] | None]:
    """The sources of each message of the conversation, in the order of its history (None: no source)."""
    conn = _connect()
    try:
        return [json.loads(row["sources"]) if row["sources"] else None for row in conn.execute(_BY_MESSAGE, (conversation_id,))]
    finally:
        conn.close()


def copy_sources(from_conversation: int, to_conversation: int) -> None:
    """[X2] A branch copies the first messages of its source: their sources go with them, in order."""
    conn = _connect()
    try:
        old = conn.execute(_BY_MESSAGE, (from_conversation,)).fetchall()
        new = conn.execute("SELECT id FROM messages WHERE conversation_id = ? ORDER BY id", (to_conversation,)).fetchall()
        with conn:
            conn.executemany("INSERT OR REPLACE INTO message_sources (message_id, sources) VALUES (?, ?)", [(copy["id"], original["sources"]) for original, copy in zip(old, new) if original["sources"]])
    finally:
        conn.close()
