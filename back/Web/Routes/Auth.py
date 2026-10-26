"""Login and logout. Accounts are the CLI's ones (Memories/Auth.py): no sign-up from the web."""

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from Chatbot import build_session
from Memories.Auth import authenticate_user, user_exists, user_id_for_email
from Web.Sessions import COOKIE_NAME, REMEMBER_SECONDS

router = APIRouter()


class Credentials(BaseModel):
    email: str
    password: str
    remember: bool = False


def _account(identifier: str) -> str | None:
    """The user_id behind what was typed: an email, or the CLI user id."""
    identifier = identifier.strip()
    if user_exists(identifier):
        return identifier
    return user_id_for_email(identifier)


@router.post("/login")
def login(credentials: Credentials, request: Request, response: Response):
    user_id = _account(credentials.email)
    if user_id is None or not authenticate_user(user_id, credentials.password):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    session = build_session(request.app.state.args, user_id, None)
    token = request.app.state.sessions.open(session)
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="strict",
                        max_age=REMEMBER_SECONDS if credentials.remember else None)
    return {"user_id": user_id, "model": session.model}


@router.post("/logout")
def logout(request: Request, response: Response):
    request.app.state.sessions.close(request.cookies.get(COOKIE_NAME))
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    """The logged-in user, or null: the interface asks before showing the login page."""
    web = request.app.state.sessions.get(request.cookies.get(COOKIE_NAME))
    if web is None:
        return {"user_id": None}
    return {"user_id": web.session.user_id, "model": web.session.model}
