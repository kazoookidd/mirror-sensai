"""A user's conversations: list, messages, rename, delete (Memories/Conversations.py).
[X2] Branches are not listed: they are reached from their root, and renaming or
deleting a conversation acts on all its branches (Memories/Branches.py)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from Memories.Branches import branch_ids, delete_family, family, rename_family, root_of, versions
from Memories.Conversations import get_conversation, list_conversations
from Memories.Memory import load_history
from Web.Sessions import WebSession, current

PREVIEW_CHARS = 140

router = APIRouter()


class Rename(BaseModel):
    title: str = Field(min_length=1, max_length=120)


def owned(conversation_id: int, web: WebSession) -> dict:
    """The conversation if it belongs to the logged-in user, 404 otherwise."""
    conversation = get_conversation(conversation_id)
    if conversation is None or conversation["user_id"] != web.session.user_id:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation


def _preview(history: list[dict]) -> str:
    """Start of the last answer, shown under the title in the history."""
    answers = [m["content"] for m in history if m["role"] == "assistant"]
    return " ".join(answers[-1].split())[:PREVIEW_CHARS] if answers else ""


@router.get("/conversations")
def conversations(web: WebSession = Depends(current)):
    items = []
    branches = branch_ids()
    for conversation in list_conversations(web.session.user_id):
        if conversation["id"] in branches:
            continue
        history = load_history(conversation["id"])
        if history:
            items.append({**conversation, "preview": _preview(history)})
    return {"conversations": items}


@router.get("/conversations/{conversation_id}/messages")
def messages(conversation_id: int, web: WebSession = Depends(current)):
    conversation = owned(conversation_id, web)
    root = root_of(conversation_id)
    return {
        "conversation": {**conversation, "title": get_conversation(root)["title"], "root_id": root},
        "messages": load_history(conversation_id),
        "versions": versions(conversation_id),
    }


@router.patch("/conversations/{conversation_id}")
def rename(conversation_id: int, body: Rename, web: WebSession = Depends(current)):
    owned(conversation_id, web)
    rename_family(conversation_id, body.title.strip())
    return {"ok": True}


@router.delete("/conversations/{conversation_id}")
def delete(conversation_id: int, web: WebSession = Depends(current)):
    owned(conversation_id, web)
    members = family(conversation_id)
    delete_family(conversation_id)
    if web.session.conversation_id in members:
        web.session.conversation_id = None
    return {"ok": True, "deleted": members}
