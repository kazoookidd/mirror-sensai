"""Leave requests saved after the user confirmed them ([A3]).

A request is never deleted: cancelling it changes its status, so the HR view keeps the
whole story. Every function that touches one request takes the user_id of the session:
a request is only found among the requests of that user.
"""

from Memories.Database import get_connection

# Leave types, with the wording shown to people (the HR view, the plans to confirm).
LEAVE_TYPES = {
    "paid_leave": "Paid leave",
    "sick_leave": "Sick leave",
    "marriage": "Marriage or civil union (Pacs)",
    "bereavement": "Bereavement",
    "remote_work": "Remote work",
    "unpaid_leave": "Unpaid leave",
    "other": "Other",
}

STATUS_PENDING = "pending"      # filed by the employee, not decided by HR yet
STATUS_APPROVED = "approved"    # approved by HR
STATUS_REFUSED = "refused"      # refused by HR
STATUS_CANCELLED = "cancelled"  # cancelled by the employee: final, HR cannot reopen it
STATUS_LABELS = {STATUS_PENDING: "Pending", STATUS_APPROVED: "Approved", STATUS_REFUSED: "Refused",
                 STATUS_CANCELLED: "Cancelled"}
# What HR can set. Back to pending undoes a decision taken by mistake.
HR_DECISIONS = (STATUS_PENDING, STATUS_APPROVED, STATUS_REFUSED)

_COLUMNS = "id, user_id, leave_type, start_date, end_date, reason, status, created_at, decided_by, decided_at"


def init_store(db_path: str = None) -> None:
    """Create the leave_requests table if needed. Safe to call repeatedly.
    A table made before statuses existed gets the column: its requests are pending."""
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
                status TEXT NOT NULL DEFAULT 'pending',
                decided_by TEXT,
                decided_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(leave_requests)")}
        for name, kind in (("status", "TEXT NOT NULL DEFAULT 'pending'"), ("decided_by", "TEXT"), ("decided_at", "TEXT")):
            if name not in columns:
                conn.execute(f"ALTER TABLE leave_requests ADD COLUMN {name} {kind}")
        conn.commit()
    finally:
        conn.close()


def save_leave_request(user_id: str, data: dict, db_path: str = None) -> int:
    """Insert a leave request and return its id."""
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
            f"SELECT {_COLUMNS} FROM leave_requests WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def pending_requests_starting(user_id: str, start_date: str, db_path: str = None) -> list[dict]:
    """The pending requests of this user that start on `start_date`, most recent first."""
    init_store(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM leave_requests "
            "WHERE user_id = ? AND start_date = ? AND status = ? ORDER BY id DESC",
            (user_id, start_date, STATUS_PENDING),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def cancel_leave_request(user_id: str, request_id: int, db_path: str = None) -> bool:
    """Cancel one pending request of this user. False if it is not theirs, or not pending any more."""
    init_store(db_path)
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            "UPDATE leave_requests SET status = ? WHERE id = ? AND user_id = ? AND status = ?",
            (STATUS_CANCELLED, request_id, user_id, STATUS_PENDING),
        )
        conn.commit()
        return cursor.rowcount == 1
    finally:
        conn.close()


def decide_leave_request(request_id: int, status: str, hr_user_id: str, db_path: str = None) -> dict:
    """[M1] HR approves or refuses a request (or puts it back to pending). Returns the request as saved.
    Raises ValueError for an unknown status, LookupError for an unknown request, and
    PermissionError for a cancelled one (the employee's cancellation is final).
    The caller checks that `hr_user_id` is an HR account."""
    if status not in HR_DECISIONS:
        raise ValueError(f"status must be one of: {', '.join(HR_DECISIONS)}")
    init_store(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT status FROM leave_requests WHERE id = ?", (request_id,)).fetchone()
        if row is None:
            raise LookupError(f"no leave request #{request_id}")
        if row["status"] == STATUS_CANCELLED:
            raise PermissionError(f"leave request #{request_id} was cancelled by the employee")
        decided = status != STATUS_PENDING
        conn.execute(
            "UPDATE leave_requests SET status = ?, decided_by = ?, "
            "decided_at = CASE WHEN ? THEN CURRENT_TIMESTAMP END WHERE id = ?",
            (status, hr_user_id if decided else None, decided, request_id))
        conn.commit()
        return dict(conn.execute(
            "SELECT r.id, r.user_id, u.email, r.leave_type, r.start_date, r.end_date, r.reason, r.status, "
            "r.created_at, r.decided_by, r.decided_at FROM leave_requests r "
            "LEFT JOIN users u ON u.user_id = r.user_id WHERE r.id = ?", (request_id,)).fetchone())
    finally:
        conn.close()


def list_all_leave_requests(db_path: str = None) -> list[dict]:
    """[M1] Every request with its employee's email, for the HR view: next leaves first."""
    init_store(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT r.id, r.user_id, u.email, r.leave_type, r.start_date, r.end_date, r.reason, "
            "r.status, r.created_at, r.decided_by, r.decided_at FROM leave_requests r "
            "LEFT JOIN users u ON u.user_id = r.user_id ORDER BY r.start_date DESC, r.id DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
