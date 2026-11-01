"""
[X4] POST /api/form: the values of the form the assistant is waiting for.

Only the form of this session and of this conversation is accepted, and the values are
checked again here (Agents/Forms.py): the browser never decides what is valid. A question
is answered in the chat instead (its answer is the user's next message). A form of the model
(ask_form) returns its answers, which the interface sends as the user's next message.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from Agents.Forms import FormError, PendingForm
from Commands import settle_pending_action
from Web.Sessions import WebSession, current

router = APIRouter()


class FormValues(BaseModel):
    conversation_id: int | None = None
    values: dict[str, str | None] = {}


@router.post("/form")
def submit_form(body: FormValues, web: WebSession = Depends(current)):
    pending = web.session.pending_action
    conversation_id = body.conversation_id if body.conversation_id is not None else web.session.conversation_id
    if not isinstance(pending, PendingForm) or pending.conversation_id != conversation_id:
        raise HTTPException(status_code=404, detail="No form is waiting in this chat.")
    if pending.kind == "question":
        raise HTTPException(status_code=422, detail="Answer this question in the chat.")
    if not web.busy.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="An answer is already being generated.")
    try:
        result = pending.submit(body.values)
    except FormError as e:
        return {"ok": False, "errors": e.errors}
    except Exception as e:  # still waiting: the user can submit again
        raise HTTPException(status_code=500, detail=f"The request failed ({e}). The form is still waiting.")
    finally:
        web.busy.release()
    web.session.pending_action = None
    if pending.kind == "answers":
        outcome = f"Answers:\n{result}"
        settle_pending_action(pending, outcome)
        return {"ok": True, "answer": result, "settled": pending.settled(outcome)}
    settle_pending_action(pending, result)
    return {"ok": True, "result": result, "settled": pending.settled(result)}
