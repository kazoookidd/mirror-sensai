import hashlib
import re
import secrets
import sqlite3
from .Database import get_connection

# [M1] Account roles, set when the account is created and never changed by its owner:
# the CLI creates HR accounts, signing up on the web creates employee accounts.
ROLE_HR = "hr"
ROLE_EMPLOYEE = "employee"
ROLE_LABELS = {ROLE_HR: "HR", ROLE_EMPLOYEE: "Employee"}

# Web sign-up: the user id cannot contain "@", so it is never mistaken for an email at login.
USER_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,39}")
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
MIN_PASSWORD_CHARS = 8


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


def user_id_for_email(email: str) -> str | None:
    """Return the user_id of the account registered with this email, or None."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT user_id FROM users WHERE email = ?", (email,)
        ).fetchone()
        return row["user_id"] if row else None
    finally:
        conn.close()


def email_of(user_id: str) -> str | None:
    """Return the email of this account, or None."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT email FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["email"] if row else None
    finally:
        conn.close()


def role_of(user_id: str) -> str | None:
    """Return the role of this account (ROLE_HR or ROLE_EMPLOYEE), or None."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT role FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["role"] if row else None
    finally:
        conn.close()


def check_new_account(user_id: str, email: str, password: str) -> str | None:
    """The reason a web sign-up is refused, or None. Taken ids and emails are checked too."""
    if not USER_ID_PATTERN.fullmatch(user_id):
        return ("The user id must be 3 to 40 characters: letters, digits, '.', '_' or '-', "
                "starting with a letter or a digit.")
    if not EMAIL_PATTERN.fullmatch(email):
        return "Enter a valid email address."
    if len(password) < MIN_PASSWORD_CHARS:
        return f"The password must be at least {MIN_PASSWORD_CHARS} characters."
    if user_exists(user_id):
        return "This user id is already used."
    if user_id_for_email(email):
        return "This email address is already used."
    return None


def create_user(user_id: str, email: str, password: str, role: str = ROLE_HR) -> dict:
    """Create a new user account with a salted, hashed password.
    Raises ValueError if the user_id or email is already taken, or the role unknown."""
    if role not in ROLE_LABELS:
        raise ValueError(f"Unknown role: {role}.")
    conn = get_connection()
    try:
        salt = secrets.token_hex(16)
        password_hash = _hash_password(password, salt)
        try:
            conn.execute(
                "INSERT INTO users (user_id, email, password_hash, salt, role) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, email, password_hash, salt, role)
            )
            conn.commit()
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Could not create account: {e}")
        return {"user_id": user_id, "email": email, "role": role}
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
        # [M1] Accounts made in the terminal are HR accounts (employees sign up on the web).
        return create_user(user_id, email, password, role=ROLE_HR)