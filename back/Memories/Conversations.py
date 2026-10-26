from .Database import get_connection

DEFAULT_TITLE = "New conversation"


def create_conversation(user_id: str, title: str = None) -> int:
    """Create a new, empty conversation for a user. Returns its id."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO conversations (user_id, title) VALUES (?, ?)",
            (user_id, title or DEFAULT_TITLE)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_conversations(user_id: str) -> list[dict]:
    """List a user's conversations, most recently active first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations "
            "WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_conversation(conversation_id: int) -> dict | None:
    """Fetch a single conversation by id, or None if it doesn't exist."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, user_id, title, created_at, updated_at "
            "FROM conversations WHERE id = ?",
            (conversation_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def rename_conversation(conversation_id: int, new_title: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE conversations SET title = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (new_title, conversation_id)
        )
        conn.commit()
    finally:
        conn.close()


def touch_conversation(conversation_id: int) -> None:
    """Bump updated_at. Called whenever a message is saved, so the
    conversation list can be sorted by recency without a join on messages."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (conversation_id,)
        )
        conn.commit()
    finally:
        conn.close()


def delete_conversation(conversation_id: int) -> None:
    """Delete a conversation and everything tied to it (messages, summary,
    compression logs). Irreversible - the caller is responsible for any
    confirmation step before calling this."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        conn.execute("DELETE FROM summaries WHERE conversation_id = ?", (conversation_id,))
        conn.execute("DELETE FROM compression_logs WHERE conversation_id = ?", (conversation_id,))
        conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        conn.commit()
    finally:
        conn.close()