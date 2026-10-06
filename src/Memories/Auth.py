import hashlib
import secrets
import sqlite3
from .Database import get_connection


def _hash_password(password: str, salt: str) -> str:
    """Derive a password hash using PBKDF2-HMAC-SHA256 (100k iterations)."""
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000
    ).hex()


def user_exists(user_id: str) -> bool:
    """Return True if a user with this user_id already has an account."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def create_user(user_id: str, email: str, password: str) -> dict:
    """Create a new user account with a salted, hashed password.
    Raises ValueError if the user_id or email is already taken."""
    conn = get_connection()
    try:
        salt = secrets.token_hex(16)
        password_hash = _hash_password(password, salt)
        try:
            conn.execute(
                "INSERT INTO users (user_id, email, password_hash, salt) "
                "VALUES (?, ?, ?, ?)",
                (user_id, email, password_hash, salt)
            )
            conn.commit()
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Could not create account: {e}")
        return {"user_id": user_id, "email": email}
    finally:
        conn.close()


def authenticate_user(user_id: str, password: str) -> bool:
    """Return True if the given password matches the stored hash
    for this user_id. Returns False if the user doesn't exist."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT password_hash, salt FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        if row is None:
            return False
        expected_hash = _hash_password(password, row["salt"])
        return secrets.compare_digest(expected_hash, row["password_hash"])
    finally:
        conn.close()


def get_or_create_user(user_id: str, password: str, email: str = None) -> dict:
    """
    Login/signup entry point used at CLI startup:
    - If user_id already exists: authenticate with the given password.
      Raises ValueError on wrong password.
    - If user_id does not exist: create a new account. An email is
      required in that case.
    Returns a dict with at least {"user_id": ...} on success.
    """
    if user_exists(user_id):
        if not authenticate_user(user_id, password):
            raise ValueError("Incorrect password.")
        return {"user_id": user_id}
    else:
        if not email:
            raise ValueError("Email is required to create a new account.")
        return create_user(user_id, email, password)