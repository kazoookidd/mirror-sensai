"""The personas of the session, and switching the active one (like /personas and /persona)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from Runtime.Personas import resolve_persona
from Web.Sessions import WebSession, current

router = APIRouter()


class PersonaChoice(BaseModel):
    id: str


@router.get("/personas")
def personas(web: WebSession = Depends(current)):
    return {
        "current": web.session.persona_id,
        "personas": [{"id": persona_id, "name": persona["name"], "description": persona["description"]}
                     for persona_id, persona in web.session.personas.items()],
    }


@router.put("/persona")
def switch_persona(choice: PersonaChoice, web: WebSession = Depends(current)):
    persona_id = resolve_persona(choice.id, web.session.personas)
    if persona_id is None:
        raise HTTPException(status_code=404, detail=f"Unknown persona: {choice.id}.")
    web.session.persona_id = persona_id
    return {"current": persona_id}
