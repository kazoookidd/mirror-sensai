"""
Where a chat turn writes what the user sees.

The chat logic never calls print() directly: it reports events to an Output.
CliOutput reproduces the terminal display; another interface (the web UI)
plugs its own Output into Session.out and receives the same events.
"""

import signal

from contextlib import contextmanager
from Memories.TokenLimit import format_usage, small

TRACE_CHARS = 110  # one terminal line per step
TRACE_LABELS = {"observation": "result: ", "tool_error": "failed: "}


class CliOutput:
    """The terminal: every event is printed exactly as the CLI always did."""

    def __init__(self):
        self._stop = False

    @contextmanager
    def interruptible(self):
        """[X2] During a chat turn, Ctrl+C stops the answer instead of quitting."""
        self._stop = False
        previous = signal.signal(signal.SIGINT, lambda *_: setattr(self, "_stop", True))
        try:
            yield
        finally:
            signal.signal(signal.SIGINT, previous)

    def stopped(self) -> bool:
        return self._stop

    def stream_start(self, prefix: str) -> None:
        """Called once, just before the first streamed character of an answer."""
        print(prefix, end="")

    def stream_token(self, text: str) -> None:
        print(text, end="", flush=True)

    def stream_end(self) -> None:
        print()

    def answer(self, text: str) -> None:
        """A whole answer that was not streamed (cache hit, agent fallback)."""
        print(f"Assistant: {text}")

    def note(self, text: str) -> None:
        """Discreet line: tool used, cache hit, a feature turned off."""
        print(small(text))

    def trace(self, kind: str, text: str) -> None:
        """[A1] One step of the agent: thought, action, observation, tool_error or note.
        A thought is the text the model streamed before its tool call: already on screen."""
        if kind == "thought":
            return
        label = TRACE_LABELS.get(kind, "")
        line = " ".join(text.split())  # a search result spans many lines: one is enough here
        print(small(f"  · {label}{line[:TRACE_CHARS]}"))

    def retract(self) -> None:
        """[A1] What was streamed is not the answer (the agent calls the model again).
        The terminal cannot erase it: the dimmed trace line says why a new answer follows."""

    def warning(self, text: str) -> None:
        print(text)

    def error(self, text: str) -> None:
        print(text)

    def usage(self, prompt_tokens: int, completion_tokens: int, approximate: bool) -> None:
        print(small(format_usage(prompt_tokens, completion_tokens, approximate)))

    def context(self, context_tokens: int, budget: int) -> None:
        """Size of the context sent this turn. The terminal does not show it."""

    def confirmation(self, title: str, plan: str) -> None:
        """[A3] An action waits for /confirm or /cancel. The terminal already shows it in the answer."""
