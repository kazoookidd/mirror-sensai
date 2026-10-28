"""
POST /api/chat: one exchange, streamed as Server-Sent Events.

The route runs the CLI's own chat_turn in a thread, with an SseOutput instead
of the terminal, and forwards its events to the browser as they arrive.
[X2] `branch_from` continues the chat in a new branch that keeps the messages
before that index (edit a question, regenerate an answer); POST /api/chat/stop
stops the answer being generated.
"""

import logging
import queue
import threading

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from Chatbot import chat_turn
from Memories.Branches import create_branch, delete_branch, root_of
from Memories.Conversations import create_conversation, get_conversation, touch_conversation
from Memories.Memory import load_history
from Web.Output import SseOutput, sse
from Web.Routes.Conversations import owned
from Web.Sessions import WebSession, current

TITLE_CHARS = 60
logger = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    conversation_id: int | None = None
    branch_from: int | None = None


def _title(message: str) -> str:
    """A new conversation is named after its first question."""
    title = " ".join(message.split())
    return title if len(title) <= TITLE_CHARS else title[:TITLE_CHARS - 3].rstrip() + "..."


def _branch(web: WebSession, conversation_id: int | None, index: int) -> dict:
    """A new branch of the conversation that keeps the messages before `index`, a question."""
    if conversation_id is None:
        raise HTTPException(status_code=422, detail="A branch needs a conversation.")
    owned(conversation_id, web)
    history = load_history(conversation_id)
    if not 0 <= index < len(history) or history[index]["role"] != "user":
        raise HTTPException(status_code=422, detail="This message cannot be edited.")
    branch = create_branch(conversation_id, index)
    return {"id": branch, "title": get_conversation(root_of(branch))["title"], "branch": True}


def _select_conversation(web: WebSession, body: ChatRequest, message: str) -> dict:
    """Make the requested conversation (or a new branch of it) active, or create one for a first message."""
    if body.branch_from is not None:
        conversation = _branch(web, body.conversation_id, body.branch_from)
    elif body.conversation_id is None:
        title = _title(message)
        conversation = {"id": create_conversation(web.session.user_id, title), "title": title}
    else:
        conversation = owned(body.conversation_id, web)
    web.session.conversation_id = conversation["id"]
    return conversation


def _settle(web: WebSession, conversation: dict, done: bool) -> None:
    """After a turn: a branch with nothing new is removed (the original is enough), otherwise
    the root moves to the top of the history."""
    if conversation.get("branch") and not done:
        delete_branch(conversation["id"])
        web.session.conversation_id = None
    elif done:
        touch_conversation(root_of(conversation["id"]))


def _run(web: WebSession, conversation: dict, message: str, events: queue.Queue) -> None:
    done = False
    cache = web.session.semantic_cache
    try:
        web.session.semantic_cache = cache and not conversation.get("branch")
        done = chat_turn(web.session, message)
    except Exception:
        logger.exception("chat turn failed")
        events.put(("error", {"text": "Internal server error.", "kind": "other"}))
    finally:
        web.session.semantic_cache = cache
        try:
            _settle(web, conversation, done)
        except Exception:
            logger.exception("could not settle the conversation")
        if web.session.out.stopped():
            events.put(("stopped", {}))
        events.put(("done", {"ok": done}))
        events.put(None)
        web.busy.release()


def _stream(conversation: dict, events: queue.Queue):
    yield sse("conversation", conversation)
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
        conversation = _select_conversation(web, body, message)
    except HTTPException:
        web.busy.release()
        raise
    events = queue.Queue()
    web.session.out = SseOutput(events)
    threading.Thread(target=_run, args=(web, conversation, message, events), daemon=True).start()
    return StreamingResponse(_stream(conversation, events), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


@router.post("/chat/stop")
def stop(web: WebSession = Depends(current)):
    """Stop the answer being generated; what arrived so far is kept."""
    stopping = web.busy.locked() and hasattr(web.session.out, "stop")
    if stopping:
        web.session.out.stop.set()
    return {"stopping": stopping}
