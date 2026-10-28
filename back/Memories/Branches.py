"""
[X2] Branches of a conversation.

Editing a message, or regenerating an answer, continues the chat in a copy of
the conversation that keeps the messages before that point: the original stays
as it was. A branch is an ordinary conversation, so the history, the
compression (M2) and the CLI work on it unchanged; this module only records
where each branch comes from: its root, the conversation it was copied from
(source) and the index of the question it replaces (branch_at).
"""

import sqlite3

from .Conversations import create_conversation, delete_conversation, get_conversation, rename_conversation
from .Database import get_connection
from .Memory import load_history

BRANCH_TITLE = "{title} (branch {number})"

_CREATE_BRANCHES = """
    CREATE TABLE IF NOT EXISTS branches (
        conversation_id INTEGER PRIMARY KEY,
        root_id INTEGER NOT NULL,
        source_id INTEGER,
        branch_at INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id),
        FOREIGN KEY (root_id) REFERENCES conversations(id)
    )
"""
_NEW_COLUMNS = (("source_id", "INTEGER"), ("branch_at", "INTEGER NOT NULL DEFAULT 0"))
_COUNT_MESSAGES = "SELECT conversation_id, COUNT(*) AS n FROM messages WHERE conversation_id IN ({}) GROUP BY conversation_id"
_COPY_MESSAGES = """
    INSERT INTO messages (conversation_id, role, content, created_at)
    SELECT ?, role, content, created_at FROM messages
    WHERE conversation_id = ? ORDER BY id LIMIT ?
"""


def _connect():
    conn = get_connection()
    conn.execute(_CREATE_BRANCHES)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(branches)")}
    for name, kind in _NEW_COLUMNS:
        if name not in columns:
            try:
                conn.execute(f"ALTER TABLE branches ADD COLUMN {name} {kind}")
            except sqlite3.OperationalError:
                pass
    return conn


def root_of(conversation_id: int) -> int:
    """The conversation a branch was copied from, or the conversation itself."""
    conn = _connect()
    try:
        row = conn.execute("SELECT root_id FROM branches WHERE conversation_id = ?", (conversation_id,)).fetchone()
        return row["root_id"] if row else conversation_id
    finally:
        conn.close()


def family(conversation_id: int) -> list[int]:
    """The root, then its branches, oldest first."""
    root = root_of(conversation_id)
    conn = _connect()
    try:
        rows = conn.execute("SELECT conversation_id FROM branches WHERE root_id = ? ORDER BY conversation_id", (root,)).fetchall()
        return [root] + [row["conversation_id"] for row in rows]
    finally:
        conn.close()


def branch_ids() -> set[int]:
    """Every conversation that is a branch (the history lists only the roots)."""
    conn = _connect()
    try:
        return {row["conversation_id"] for row in conn.execute("SELECT conversation_id FROM branches")}
    finally:
        conn.close()


def create_branch(conversation_id: int, keep: int) -> int:
    """A new branch holding the first `keep` messages of the conversation. Returns its id."""
    root = root_of(conversation_id)
    source = get_conversation(root)
    title = BRANCH_TITLE.format(title=source["title"], number=len(family(root)) + 1)
    branch = create_conversation(source["user_id"], title)
    conn = _connect()
    try:
        conn.execute(_COPY_MESSAGES, (branch, conversation_id, keep))
        conn.execute("INSERT INTO branches (conversation_id, root_id, source_id, branch_at) VALUES (?, ?, ?, ?)", (branch, root, conversation_id, keep))
        conn.commit()
    finally:
        conn.close()
    return branch


def delete_branch(conversation_id: int) -> None:
    """Remove one branch (used when its first exchange failed)."""
    conn = _connect()
    try:
        conn.execute("DELETE FROM branches WHERE conversation_id = ?", (conversation_id,))
        conn.commit()
    finally:
        conn.close()
    delete_conversation(conversation_id)


def delete_family(conversation_id: int) -> None:
    """Delete the root and all its branches."""
    members = family(conversation_id)
    for member in members[1:]:
        delete_branch(member)
    delete_conversation(members[0])


def rename_family(conversation_id: int, title: str) -> None:
    """Rename the root; the branches follow as "<title> (branch n)"."""
    members = family(conversation_id)
    rename_conversation(members[0], title)
    for number, member in enumerate(members[1:], start=2):
        rename_conversation(member, BRANCH_TITLE.format(title=title, number=number))


def _lineage(conversation_id: int) -> dict[int, tuple[int | None, int]]:
    """Every member of the family: (the conversation it was copied from, the index it replaces)."""
    root = root_of(conversation_id)
    conn = _connect()
    try:
        rows = conn.execute("SELECT conversation_id, source_id, branch_at FROM branches WHERE root_id = ?", (root,))
        members = {root: (None, 0)}
        members.update({row["conversation_id"]: (row["source_id"] or root, row["branch_at"]) for row in rows})
        return members
    finally:
        conn.close()


def _lengths(members) -> dict[int, int]:
    conn = _connect()
    try:
        rows = conn.execute(_COUNT_MESSAGES.format(",".join("?" * len(members))), list(members))
        return {row["conversation_id"]: row["n"] for row in rows}
    finally:
        conn.close()


def versions(conversation_id: int) -> list[dict]:
    """For each question of the conversation that exists in several versions in its family:
    {"index", "current", "conversations"}. A version is identified by where its message comes
    from, never by its text: a regenerated answer equal to the first one is still a new version."""
    members = _lineage(conversation_id)
    lengths = _lengths(members)

    def origin(member: int, index: int) -> int:
        """The conversation in which the message at `index` of `member` was written."""
        while members[member][0] is not None and members[member][1] > index:
            member = members[member][0]
        return member

    result = []
    for index, message in enumerate(load_history(conversation_id)):
        if message["role"] != "user":
            continue
        options = sorted({origin(member, index) for member in members if lengths.get(member, 0) > index and (index == 0 or origin(member, index - 1) == origin(conversation_id, index - 1))})
        if len(options) < 2:
            continue
        mine = origin(conversation_id, index)
        result.append({"index": index, "current": options.index(mine) + 1, "conversations": [conversation_id if option == mine else option for option in options]})
    return result
