"""[X3] Downloading a conversation (Export/Formats.py) and its public link (Export/Shares.py).
GET /share/{token} is the only route that works without logging in: it never returns who shared."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from Export.Formats import export
from Export.Shares import active_share, create_share, find_share, revoke_shares
from Web.Routes.Conversations import owned
from Web.Sessions import WebSession, current

router = APIRouter()


@router.get("/conversations/{conversation_id}/export")
def download(conversation_id: int, format: str = "md", web: WebSession = Depends(current)):
    owned(conversation_id, web)
    try:
        name, media_type, content = export(conversation_id, format)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return Response(content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/conversations/{conversation_id}/share")
def share_state(conversation_id: int, web: WebSession = Depends(current)):
    owned(conversation_id, web)
    return {"share": active_share(conversation_id)}


@router.post("/conversations/{conversation_id}/share")
def share(conversation_id: int, web: WebSession = Depends(current)):
    owned(conversation_id, web)
    try:
        return {"share": create_share(conversation_id)}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/conversations/{conversation_id}/share")
def stop_sharing(conversation_id: int, web: WebSession = Depends(current)):
    owned(conversation_id, web)
    revoke_shares(conversation_id)
    return {"share": None}


@router.get("/share/{token}")
def shared(token: str):
    found = find_share(token)
    if found is None:
        raise HTTPException(status_code=404, detail="This link does not exist or was turned off.")
    if found.pop("expired"):
        raise HTTPException(status_code=410, detail="This link has expired.")
    return found
