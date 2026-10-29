"""Answer settings, through the same parsers as /settings in the CLI (Runtime/Settings.py)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from Memories.TokenLimit import get_budget
from Runtime.Settings import apply_setting, find_setting
from Web.Sessions import WebSession, current

router = APIRouter()


class SettingValue(BaseModel):
    value: str


@router.get("/settings")
def settings(web: WebSession = Depends(current)):
    session = web.session
    return {
        "temperature": session.temperature,
        "num_predict": session.num_predict,
        "ollama_url": session.ollama_url,
        "context_budget": get_budget(),
        "hr_documents": session.hr_documents,
    }


@router.put("/settings/{name}")
def change_setting(name: str, body: SettingValue, web: WebSession = Depends(current)):
    setting = find_setting(name)
    if setting is None:
        raise HTTPException(status_code=404, detail=f"Unknown setting: {name}.")
    value, error = apply_setting(web.session, setting, body.value)
    if error:
        raise HTTPException(status_code=422, detail=error)
    return {"name": setting.name, "value": value}
