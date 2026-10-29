"""
[M1] The user's profile: who they are and how they want to be answered.

One row per account. It is read at every turn and added to the system prompt
(Session.system_prompt), so the model knows the user without being told again:
"I am a consultant", "answer in French", "always quote the article". Switching
persona or model keeps it. It is edited with /profile in the CLI and on the
Profile page of the web interface, through the same checks (clean_profile).

The text added to the prompt (context_text) is the one the web interface
previews: front/src/features/profile/ContextPreview.jsx builds the same.
"""

import sqlite3
from dataclasses import dataclass

from .Database import get_connection


@dataclass(frozen=True)
class ProfileField:
    name: str            # column, and key of the API
    label: str           # key in the text given to the model
    max_chars: int
    choices: tuple = ()  # empty: free text
    aliases: tuple = ()  # other names accepted by /profile


FIELDS = (
    ProfileField("name", "name", 80, aliases=("nom", "full-name")),
    ProfileField("role", "job", 80, aliases=("job", "poste", "title")),
    ProfileField("department", "department", 80, aliases=("service",)),
    ProfileField("language", "language", 40, aliases=("langue",)),
    ProfileField("tone", "tone", 20, choices=("concise", "detailed"), aliases=("ton",)),
    ProfileField("instructions", "instructions", 1000, aliases=("consignes", "custom")),
)
FIELD_NAMES = tuple(field.name for field in FIELDS)

PROMPT_HEADER = (
    "--- User profile ---\n"
    "What the user told about themselves and how they want to be answered. "
    "Take it into account, unless it goes against the rules above."
)

_CREATE = f"""
    CREATE TABLE IF NOT EXISTS profiles (
        user_id TEXT PRIMARY KEY,
        {", ".join(f"{name} TEXT NOT NULL DEFAULT ''" for name in FIELD_NAMES)},
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
"""


def _connect(db_path: str = None) -> sqlite3.Connection:
    conn = get_connection(db_path)
    conn.execute(_CREATE)
    return conn


def empty_profile() -> dict:
    return {name: "" for name in FIELD_NAMES}


def find_field(name: str) -> ProfileField | None:
    """The field called `name` or one of its aliases (case and _ / - ignored)."""
    key = name.strip().lower().replace("_", "-")
    for field in FIELDS:
        if key == field.name or key in field.aliases:
            return field
    return None


def clean_value(field: ProfileField, value) -> tuple[str, str | None]:
    """(value as saved, error). Spaces are tidied; the instructions keep their lines."""
    if value is None:
        value = ""
    if not isinstance(value, str):
        return "", f"{field.name} must be text."
    if field.name == "instructions":
        value = "\n".join(" ".join(line.split()) for line in value.strip().splitlines()).strip()
    else:
        value = " ".join(value.split())
    if field.choices and value:
        value = value.lower()
        if value not in field.choices:
            return "", f"{field.name} must be one of: {', '.join(field.choices)} (or empty)."
    if len(value) > field.max_chars:
        return "", f"{field.name} is too long ({len(value)} characters, {field.max_chars} at most)."
    return value, None


def clean_profile(values: dict) -> tuple[dict, str | None]:
    """A whole profile as saved, or the first error. Missing fields are empty."""
    unknown = [key for key in values if key not in FIELD_NAMES]
    if unknown:
        return {}, f"Unknown profile field: {', '.join(unknown)}."
    profile = empty_profile()
    for field in FIELDS:
        value, error = clean_value(field, values.get(field.name, ""))
        if error:
            return {}, error
        profile[field.name] = value
    return profile, None


def get_profile(user_id: str, db_path: str = None) -> dict:
    """The saved profile, every field empty when there is none."""
    conn = _connect(db_path)
    try:
        row = conn.execute(f"SELECT {', '.join(FIELD_NAMES)} FROM profiles WHERE user_id = ?",
                           (user_id,)).fetchone()
        return dict(row) if row else empty_profile()
    finally:
        conn.close()


def save_profile(user_id: str, values: dict, db_path: str = None) -> dict:
    """Check and save a whole profile; returns it as saved. Raises ValueError on a bad value."""
    profile, error = clean_profile(values)
    if error:
        raise ValueError(error)
    columns = ", ".join(FIELD_NAMES)
    updates = ", ".join(f"{name} = excluded.{name}" for name in FIELD_NAMES)
    conn = _connect(db_path)
    try:
        conn.execute(
            f"INSERT INTO profiles (user_id, {columns}) VALUES (?, {', '.join('?' * len(FIELD_NAMES))}) "
            f"ON CONFLICT(user_id) DO UPDATE SET {updates}, updated_at = CURRENT_TIMESTAMP",
            (user_id, *(profile[name] for name in FIELD_NAMES)))
        conn.commit()
    finally:
        conn.close()
    return profile


def context_text(profile: dict | None) -> str:
    """What the model is given, empty when nothing is filled in."""
    profile = profile or {}
    lines = [f"{field.label}: {profile[field.name]}" for field in FIELDS
             if field.name != "instructions" and profile.get(field.name)]
    instructions = (profile.get("instructions") or "").strip()
    if not lines and not instructions:
        return ""
    parts = ["[profile]", *lines]
    if instructions:
        parts += ["", "[instructions]", instructions]
    return "\n".join(parts)


def with_profile(system_prompt: str, profile: dict | None) -> str:
    """The system prompt followed by the profile, or unchanged when the profile is empty."""
    text = context_text(profile)
    return f"{system_prompt}\n\n{PROMPT_HEADER}\n{text}" if text else system_prompt
