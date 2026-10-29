"""[M1] The user's profile (Memories/Profile.py), with the same checks as /profile in the CLI.
The account role is shown with it but cannot be changed here: PUT refuses any unknown field."""

from fastapi import APIRouter, Depends, HTTPException
from Memories.Auth import ROLE_LABELS
from Memories.Profile import context_text, get_profile, save_profile
from Web.Sessions import WebSession, current

router = APIRouter()


def _view(web: WebSession, profile: dict) -> dict:
    """The profile, the text added to the system prompt (exactly as the model gets it) and the account role."""
    role = web.session.account_role
    return {"profile": profile, "context": context_text(profile),
            "account": {"role": role, "label": ROLE_LABELS.get(role, role)}}


@router.get("/profile")
def profile(web: WebSession = Depends(current)):
    return _view(web, get_profile(web.session.user_id))


@router.put("/profile")
def change_profile(values: dict[str, str | None], web: WebSession = Depends(current)):
    try:
        saved = save_profile(web.session.user_id, values)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    web.session.profile = saved  # the next answer uses it
    return _view(web, saved)
