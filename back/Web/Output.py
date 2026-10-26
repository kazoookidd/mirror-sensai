"""
SseOutput: the Output of a chat turn for the web UI (see Runtime/Output.py).

Every event is put in a queue as (name, data); the /api/chat route reads the
queue and streams it to the browser as Server-Sent Events.
"""

import json
import queue

ERROR_KINDS = (
    ("cannot connect", "ollama"),
    ("not found", "model"),
    ("Token limit reached", "limit"),
)


def error_kind(text: str) -> str:
    """Which error banner the interface shows: ollama, model, limit or other."""
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

    def warning(self, text: str) -> None:
        self._emit("warning", text=text)

    def error(self, text: str) -> None:
        self._emit("error", text=text, kind=error_kind(text))

    def usage(self, prompt_tokens: int, completion_tokens: int, approximate: bool) -> None:
        self._emit("usage", prompt=prompt_tokens, completion=completion_tokens, approximate=approximate)

    def context(self, context_tokens: int, budget: int) -> None:
        self._emit("context", tokens=context_tokens, budget=budget)
