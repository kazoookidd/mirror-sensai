"""
Where a chat turn writes what the user sees.

The chat logic never calls print() directly: it reports events to an Output.
CliOutput reproduces the terminal display; another interface (the web UI)
plugs its own Output into Session.out and receives the same events.
"""

from Memories.TokenLimit import format_usage, small


class CliOutput:
    """The terminal: every event is printed exactly as the CLI always did."""

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

    def warning(self, text: str) -> None:
        print(text)

    def error(self, text: str) -> None:
        print(text)

    def usage(self, prompt_tokens: int, completion_tokens: int, approximate: bool) -> None:
        print(small(format_usage(prompt_tokens, completion_tokens, approximate)))

    def context(self, context_tokens: int, budget: int) -> None:
        """Size of the context sent this turn. The terminal does not show it."""
