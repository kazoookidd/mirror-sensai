"""
[X3] Public links to a conversation.

A link shows a frozen copy of the conversation as it was when it was shared
(new messages never appear in it), without logging in. It expires after
SHARE_DAYS days and can be turned off before. Deleting the conversation
deletes its links (ON DELETE CASCADE).
"""

import json
import secrets

from Memories.Database import get_connection
from .Formats import EMPTY, document

SHARE_DAYS = 7
TOKEN_BYTES = 24

_CREATE_SHARES = """
    CREATE TABLE IF NOT EXISTS shares (
        token TEXT PRIMARY KEY,
        conversation_id INTEGER NOT NULL,
        snapshot TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        expires_at TEXT NOT NULL,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
    )
"""
_ACTIVE = "SELECT token, created_at, expires_at FROM shares WHERE conversation_id = ? AND expires_at > CURRENT_TIMESTAMP"


def _connect():
    conn = get_connection()
    conn.execute(_CREATE_SHARES)
    return conn


def active_share(conversation_id: int) -> dict | None:
    """The link of the conversation that still works, or None."""
    conn = _connect()
    try:
        row = conn.execute(_ACTIVE, (conversation_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def revoke_shares(conversation_id: int) -> int:
    """Turn off every link of the conversation. Returns how many there were."""
    conn = _connect()
    try:
        removed = conn.execute("DELETE FROM shares WHERE conversation_id = ?", (conversation_id,)).rowcount
        conn.commit()
        return removed
    finally:
        conn.close()


def create_share(conversation_id: int) -> dict:
    """A new link to the conversation as it is now; the previous link stops working.
    ValueError for an empty chat."""
    doc = document(conversation_id)
    if not doc["messages"]:
        raise ValueError(EMPTY)
    snapshot = {"title": doc["title"], "messages": [{"role": m["role"], "content": m["content"]} for m in doc["messages"]]}
    revoke_shares(conversation_id)
    conn = _connect()
    try:
        conn.execute(
            f"INSERT INTO shares (token, conversation_id, snapshot, expires_at) VALUES (?, ?, ?, datetime('now', '+{SHARE_DAYS} days'))",
            (secrets.token_urlsafe(TOKEN_BYTES), conversation_id, json.dumps(snapshot, ensure_ascii=False))
        )
        conn.commit()
    finally:
        conn.close()
    return active_share(conversation_id)


def find_share(token: str) -> dict | None:
    """What a public link shows: {"title", "messages", "created_at", "expires_at", "expired"}, None if unknown or turned off."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT snapshot, created_at, expires_at, expires_at <= CURRENT_TIMESTAMP AS expired FROM shares WHERE token = ?",
            (token,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {**json.loads(row["snapshot"]), "created_at": row["created_at"], "expires_at": row["expires_at"], "expired": bool(row["expired"])}
