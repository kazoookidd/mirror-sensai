"""Is Ollama reachable? Shown on every screen, including the login page."""

from fastapi import APIRouter, Request
from Runtime.Models import list_models

router = APIRouter()


@router.get("/status")
def status(request: Request):
    url = request.app.state.args.ollama_url
    try:
        list_models(url)
    except RuntimeError as e:
        return {"ollama": False, "url": url, "detail": str(e)}
    return {"ollama": True, "url": url}
