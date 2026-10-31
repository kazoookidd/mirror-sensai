"""
SseOutput: the Output of a chat turn for the web UI (see Runtime/Output.py).

Every event is put in a queue as (name, data); the /api/chat route reads the
queue and streams it to the browser as Server-Sent Events.
"""

import json
import queue
import threading

TRACE_CHARS = 1500  # a tool result can be 4000 characters: the start is enough to check it

ERROR_KINDS = (
    ("cannot connect", "ollama"),
    ("not found", "model"),
    ("Token limit reached", "limit"),
    ("Refused:", "guardrail"),
)


def error_kind(text: str) -> str:
    """Which error banner the interface shows: ollama, model, limit, guardrail or other."""
    for marker, kind in ERROR_KINDS:
        if marker in text:
            return kind
    return "other"


def sse(name: str, data: dict) -> str:
    """One Server-Sent Event."""
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class SseOutput:
    def __init__(self, events: queue.Queue):
        self.events = events
        self.stop = threading.Event()

    def stopped(self) -> bool:
        return self.stop.is_set()

    def _emit(self, name: str, **data) -> None:
        self.events.put((name, data))

    def stream_start(self, prefix: str) -> None:
        self._emit("start")

    def stream_token(self, text: str) -> None:
        self._emit("token", text=text)

    def stream_end(self) -> None:
        pass

    def answer(self, text: str) -> None:
        self._emit("answer", text=text)

    def note(self, text: str) -> None:
        self._emit("note", text=text.strip().lstrip("· ").strip())

    def retract(self) -> None:
        """[A1] What was streamed is not the answer (the agent calls the model again): the interface empties it."""
        self._emit("retract")

    def trace(self, kind: str, text: str) -> None:
        """[A1] One step of the agent, shown in the "Reasoning" panel of the answer."""
        text = text.strip()
        if len(text) > TRACE_CHARS:
            text = text[:TRACE_CHARS].rstrip() + " [...]"
        self._emit("trace", kind=kind, text=text)

    def warning(self, text: str) -> None:
        self._emit("warning", text=text)

    def error(self, text: str) -> None:
        self._emit("error", text=text, kind=error_kind(text))

    def usage(self, prompt_tokens: int, completion_tokens: int, approximate: bool) -> None:
        self._emit("usage", prompt=prompt_tokens, completion=completion_tokens, approximate=approximate)

    def context(self, context_tokens: int, budget: int) -> None:
        self._emit("context", tokens=context_tokens, budget=budget)

    def confirmation(self, title: str, plan: str) -> None:
        self._emit("confirmation", title=title, plan=plan)

    def sources(self, sources: list[dict]) -> None:
        self._emit("sources", sources=sources)


def pending_confirmation(session, conversation_id: int | None) -> dict | None:
    """[A3] The action waiting for /confirm or /cancel, as the card of `conversation_id` shows it:
    None in any other chat, or its card would sit on an answer it has nothing to do with."""
    pending = session.pending_action
    if pending is None or pending.conversation_id != conversation_id:
        return None
    return {"title": pending.title, "plan": pending.plan}
