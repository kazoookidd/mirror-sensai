"""
POST /api/chat: one exchange, streamed as Server-Sent Events.

The route runs the CLI's own chat_turn in a thread, with an SseOutput instead
of the terminal, and forwards its events to the browser as they arrive.
"""

import logging
import queue
import threading

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from Chatbot import chat_turn
from Memories.Conversations import create_conversation
from Web.Output import SseOutput, sse
from Web.Routes.Conversations import owned
from Web.Sessions import WebSession, current

TITLE_CHARS = 60
logger = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    conversation_id: int | None = None


def _title(message: str) -> str:
    """A new conversation is named after its first question."""
    title = " ".join(message.split())
    return title if len(title) <= TITLE_CHARS else title[:TITLE_CHARS - 3].rstrip() + "..."


def _select_conversation(web: WebSession, conversation_id: int | None, message: str) -> dict:
    """Make the requested conversation active, or create one for a first message."""
    if conversation_id is None:
        title = _title(message)
        conversation_id = create_conversation(web.session.user_id, title)
        conversation = {"id": conversation_id, "title": title}
    else:
        conversation = owned(conversation_id, web)
    web.session.conversation_id = conversation_id
    return conversation


def _run(web: WebSession, message: str, events: queue.Queue) -> None:
    done = False
    try:
        done = chat_turn(web.session, message)
    except Exception:  # never leave the browser waiting: report it, keep the server up
        logger.exception("chat turn failed")
        events.put(("error", {"text": "Internal server error.", "kind": "other"}))
    finally:
        events.put(("done", {"ok": done}))
        events.put(None)
        web.busy.release()


def _stream(conversation: dict, events: queue.Queue):
    yield sse("conversation", {"id": conversation["id"], "title": conversation["title"]})
    while (event := events.get()) is not None:
        yield sse(*event)


@router.post("/chat")
def chat(body: ChatRequest, web: WebSession = Depends(current)):
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="The message is empty.")
    if not web.busy.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="An answer is already being generated.")
    try:
        conversation = _select_conversation(web, body.conversation_id, message)
    except HTTPException:
        web.busy.release()
        raise
    events = queue.Queue()
    web.session.out = SseOutput(events)
    threading.Thread(target=_run, args=(web, message, events), daemon=True).start()
    return StreamingResponse(_stream(conversation, events), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})
