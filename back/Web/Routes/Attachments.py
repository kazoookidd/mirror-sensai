"""Files joined to one conversation (rag/Attachments.py): read into that chat only, never into the shared base.
Same checks as an import into the base (name, format, size). A file joined before the first message
creates the conversation."""

import tempfile
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from Memories.Conversations import create_conversation, delete_conversation
from rag.Attachments import attach
from Web.Routes.Conversations import owned
from Web.Routes.Documents import read_upload, upload_name
from Web.Sessions import WebSession, current

router = APIRouter()


def _attach(conversation_id: int, name: str, content: bytes) -> dict:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / name
        path.write_bytes(content)
        return attach(conversation_id, path, name)


@router.post("/attachments")
async def join_file(request: Request, name: str, conversation_id: int | None = None, web: WebSession = Depends(current)):
    file_name = upload_name(name)
    content = await read_upload(request)
    if conversation_id is None:
        conversation = {"id": create_conversation(web.session.user_id, file_name), "title": file_name}
    else:
        conversation = owned(conversation_id, web)
    try:
        attachment = await run_in_threadpool(_attach, conversation["id"], file_name, content)
    except (ValueError, ConnectionError) as e:
        if conversation_id is None:
            delete_conversation(conversation["id"])
        raise HTTPException(status_code=422 if isinstance(e, ValueError) else 503, detail=str(e))
    return {"conversation": {"id": conversation["id"], "title": conversation["title"]}, "attachment": attachment}
