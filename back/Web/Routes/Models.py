"""The models installed in Ollama, and switching the active one (like /models and /model)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from Runtime.Models import list_models, looks_like_embedding_model, resolve_model
from Web.Sessions import WebSession, current

router = APIRouter()


class ModelChoice(BaseModel):
    name: str


def _installed(web: WebSession) -> list[str]:
    try:
        return list_models(web.session.ollama_url)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/models")
def models(web: WebSession = Depends(current)):
    installed = _installed(web)
    return {
        "current": web.session.model,
        "installed": resolve_model(web.session.model, installed) is not None,
        "models": [{"name": name, "embedding": looks_like_embedding_model(name)} for name in installed],
    }


@router.put("/model")
def switch_model(choice: ModelChoice, web: WebSession = Depends(current)):
    model = resolve_model(choice.name, _installed(web))
    if model is None:
        raise HTTPException(status_code=404, detail=f"The model {choice.name} is not installed.")
    web.session.model = model
    return {"current": model}
