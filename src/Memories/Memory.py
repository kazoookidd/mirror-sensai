from Memories.Database import get_connection


def save_message(user_id: str, role: str, content: str) -> None:
    """Persist a single message to the conversation history."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content)
        )
        conn.commit()
    finally:
        conn.close()


def load_history(user_id: str) -> list[dict]:
    """Load the full message history for a user, ordered chronologically,
    already formatted as {"role": ..., "content": ...} dicts ready to be
    sent as context to Ollama."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE user_id = ? "
            "ORDER BY id ASC",
            (user_id,)
        ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]
    finally:
        conn.close()


def load_history_with_ids(user_id: str) -> list[dict]:
    """Same as load_history, but keeps the message id. Needed by the
    Context Builder (M2) to know which messages a cached summary already
    covers, so it never reprocesses the same old messages twice."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, role, content FROM messages WHERE user_id = ? "
            "ORDER BY id ASC",
            (user_id,)
        ).fetchall()
        return [
            {"id": row["id"], "role": row["role"], "content": row["content"]}
            for row in rows
        ]
    finally:
        conn.close()