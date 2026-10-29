"""
POST /api/command: runs a slash command for the web session with the CLI's own
handle_command (Commands.py) and returns what the terminal would have printed.

/new and /conversations ask questions in the terminal (input()), and /export
writes a file on the server: the interface handles them itself. /ingest only
indexes the default folder (data/docs): a path typed in the browser must not
choose what the server reads.
"""

import io
import threading
from contextlib import redirect_stdout
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from Commands import handle_command
from Web.Output import pending_confirmation
from Web.Sessions import WebSession, current

INTERACTIVE = ("/new", "/conversations", "/export")

router = APIRouter()
# sys.stdout belongs to the whole process: one command captured at a time.
_capture = threading.Lock()


class CommandRequest(BaseModel):
    text: str
    conversation_id: int | None = None


@router.post("/command")
def command(body: CommandRequest, web: WebSession = Depends(current)):
    text = body.text.strip()
    name, _, argument = text.partition(" ")
    name = name.lower()
    if not name.startswith("/"):
        raise HTTPException(status_code=422, detail="A command starts with /.")
    if name in INTERACTIVE:
        raise HTTPException(status_code=422, detail=f"{name} is handled by the interface.")
    if name == "/ingest" and argument.strip():
        raise HTTPException(status_code=422, detail="Only the default folder (data/docs) can be indexed from the interface.")
    if not web.busy.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="An answer is already being generated.")
    output = io.StringIO()
    try:
        with _capture, redirect_stdout(output):
            handle_command(web.session, text)
    finally:
        web.busy.release()
    return {
        "command": name,
        "output": output.getvalue().strip(),
        "model": web.session.model,
        "persona": web.session.persona["name"],
        "pending": pending_confirmation(web.session, body.conversation_id or web.session.conversation_id),
    }
