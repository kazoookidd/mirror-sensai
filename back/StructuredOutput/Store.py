from Memories.Database import get_connection

def init_store(db_path: str = None) -> None:
    """Create the leave_requests table if needed. Safe to call repeatedly."""
    conn = get_connection(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leave_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                leave_type TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        conn.commit()
    finally:
        conn.close()

def save_leave_request(user_id: str, data: dict, db_path: str = None) -> int:
    """Insert a validated leave request and return its id."""
    init_store(db_path)
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            "INSERT INTO leave_requests "
            "(user_id, leave_type, start_date, end_date, reason) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, data["leave_type"], data["start_date"],
             data["end_date"], data["reason"]),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def list_leave_requests(user_id: str, db_path: str = None) -> list[dict]:
    """Leave requests of a user, most recent first."""
    init_store(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT id, leave_type, start_date, end_date, reason, created_at "
            "FROM leave_requests WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
