"""Login, logout and sign-up. [M1] The CLI creates HR accounts; signing up here creates employee
accounts only (Memories/Auth.py), and the role can never be chosen by the client."""

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from Chatbot import build_session
from Memories.Auth import (ROLE_EMPLOYEE, authenticate_user, check_new_account, create_user, user_exists,
                           user_id_for_email)
from Web.Sessions import COOKIE_NAME, REMEMBER_SECONDS

router = APIRouter()


class Credentials(BaseModel):
    email: str
    password: str
    remember: bool = False


class SignUp(BaseModel):
    user_id: str
    email: str
    password: str
    remember: bool = False


def _account(identifier: str) -> str | None:
    """The user_id behind what was typed: an email, or the CLI user id."""
    identifier = identifier.strip()
    if user_exists(identifier):
        return identifier
    return user_id_for_email(identifier)


def _open_session(request: Request, response: Response, user_id: str, remember: bool) -> dict:
    """Log the browser in as `user_id`: a backend Session found again through a cookie."""
    session = build_session(request.app.state.args, user_id, None)
    token = request.app.state.sessions.open(session)
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="strict",
                        max_age=REMEMBER_SECONDS if remember else None)
    return {"user_id": user_id, "model": session.model, "account_role": session.account_role}


@router.post("/login")
def login(credentials: Credentials, request: Request, response: Response):
    user_id = _account(credentials.email)
    if user_id is None or not authenticate_user(user_id, credentials.password):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return _open_session(request, response, user_id, credentials.remember)


@router.post("/signup")
def signup(account: SignUp, request: Request, response: Response):
    """[M1] A new employee account, then logged in at once."""
    user_id, email = account.user_id.strip(), account.email.strip()
    problem = check_new_account(user_id, email, account.password)
    if problem:
        raise HTTPException(status_code=409 if "already used" in problem else 422, detail=problem)
    try:
        create_user(user_id, email, account.password, role=ROLE_EMPLOYEE)
    except ValueError:  # taken meanwhile by another sign-up
        raise HTTPException(status_code=409, detail="This user id or email address is already used.")
    return _open_session(request, response, user_id, account.remember)


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
    return {"user_id": web.session.user_id, "model": web.session.model, "account_role": web.session.account_role}
