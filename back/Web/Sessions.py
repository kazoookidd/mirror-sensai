"""
Logged-in browsers. Each one owns a backend Session (model, persona, settings,
active conversation), kept in memory and found again through a cookie.
"""

import secrets
import threading

from dataclasses import dataclass, field
from fastapi import HTTPException, Request
from Commands import Session

COOKIE_NAME = "sensai_session"
REMEMBER_SECONDS = 30 * 24 * 3600


@dataclass
class WebSession:
    session: Session
    # One answer at a time per user: chat_turn is not meant to run twice at once.
    busy: threading.Lock = field(default_factory=threading.Lock)


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, WebSession] = {}
        self._guard = threading.Lock()

    def open(self, session: Session) -> str:
        token = secrets.token_urlsafe(32)
        with self._guard:
            self._sessions[token] = WebSession(session)
        return token

    def get(self, token: str | None) -> WebSession | None:
        with self._guard:
            return self._sessions.get(token) if token else None

    def close(self, token: str | None) -> None:
        with self._guard:
            self._sessions.pop(token, None)


def current(request: Request) -> WebSession:
    """FastAPI dependency: the WebSession of the request, 401 if not logged in."""
    web = request.app.state.sessions.get(request.cookies.get(COOKIE_NAME))
    if web is None:
        raise HTTPException(status_code=401, detail="Session expired, please log in again.")
    return web
