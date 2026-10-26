from .Database import get_connection
from .Conversations import touch_conversation


def save_message(conversation_id: int, role: str, content: str) -> None:
    """Persist a single message to a conversation's history, and bump the
    conversation's updated_at so it sorts first in the conversation list."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
            (conversation_id, role, content)
        )
        conn.commit()
    finally:
        conn.close()
    touch_conversation(conversation_id)


def load_history(conversation_id: int) -> list[dict]:
    """Load the full message history for a conversation, ordered
    chronologically, already formatted as {"role": ..., "content": ...}
    dicts ready to be sent as context to Ollama."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? "
            "ORDER BY id ASC",
            (conversation_id,)
        ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]
    finally:
        conn.close()


def load_history_with_ids(conversation_id: int) -> list[dict]:
    """Same as load_history, but keeps the message id. Needed by the
    Context Builder (M2) to know which messages a cached summary already
    covers, so it never reprocesses the same old messages twice."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, role, content FROM messages WHERE conversation_id = ? "
            "ORDER BY id ASC",
            (conversation_id,)
        ).fetchall()
        return [
            {"id": row["id"], "role": row["role"], "content": row["content"]}
            for row in rows
        ]
    finally:
        conn.close()