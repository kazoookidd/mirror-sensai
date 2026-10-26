"""
Token limit and token usage display.

The limit is the context budget already used by the compression (M2):
CONTEXT_TOKEN_BUDGET. Compression normally keeps the context under it. The
limit only matters when compression cannot do it (a huge message, a failed
summary, recent messages that are alone bigger than the budget).

What happens then is a setting (TOKEN_LIMIT_ACTION):
    block     the message is refused and nothing is sent to the model
              (default). The conversation stays blocked as long as its
              context is over the limit: start a new one with /new.
    continue  the message is sent anyway, with a warning. The model may
              silently drop the oldest part of the context.

After every answer a small, dimmed line shows the tokens used by the
exchange and, from the compression threshold on (80% by default), how full
the context is.
"""

import os
import sys

from . import Compression
from .Compression import estimate_tokens

ACTION_BLOCK = "block"
ACTION_CONTINUE = "continue"
LIMIT_ACTIONS = (ACTION_BLOCK, ACTION_CONTINUE)
DEFAULT_ACTION = ACTION_BLOCK

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

def parse_limit_action(value: str | None) -> tuple[str, str | None]:
    """Turn the configured value into a valid action.
    Returns (action, warning). An invalid value falls back to the safe
    default (block) and comes with a warning to display."""
    if value is None or not value.strip():
        return DEFAULT_ACTION, None
    action = value.strip().lower()
    if action in LIMIT_ACTIONS:
        return action, None
    return DEFAULT_ACTION, (
        f"unknown token limit action '{value}' "
        f"(expected: {', '.join(LIMIT_ACTIONS)}), using '{DEFAULT_ACTION}'"
    )


def parse_bool(value: str | None, default: bool) -> bool:
    """Lenient boolean parsing for .env values (true/false, yes/no, 1/0, on/off)."""
    if value is None:
        return default
    value = value.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    return default


def get_budget() -> int:
    """The token limit: the same budget the compression works with.
    Read at call time so there is a single source of truth."""
    return Compression.DEFAULT_BUDGET


def get_threshold_ratio() -> float:
    """Fraction of the budget from which the usage percentage is shown
    (and from which the compression triggers)."""
    return Compression.DEFAULT_THRESHOLD_RATIO


# ---------------------------------------------------------------------
# Limit check
# ---------------------------------------------------------------------

def estimate_context_tokens(messages: list[dict]) -> int:
    """Estimated size of the context about to be sent (same ~4 chars per
    token approximation as the compression, so both agree)."""
    return sum(estimate_tokens(m.get("content", "")) for m in messages)


def is_over_limit(context_tokens: int, budget: int | None = None) -> bool:
    budget = get_budget() if budget is None else budget
    return context_tokens > budget


def blocked_message(context_tokens: int, budget: int | None = None) -> str:
    budget = get_budget() if budget is None else budget
    return (
        f"Token limit reached: the context is about {context_tokens} tokens, "
        f"over the limit of {budget}, even after compression.\n"
        f"The assistant is blocked for this conversation and nothing was sent. "
        f"Start a new conversation with /new (or switch with /conversations), "
        f"or set TOKEN_LIMIT_ACTION=continue to keep going past the limit."
    )


def warning_message(context_tokens: int, budget: int | None = None) -> str:
    budget = get_budget() if budget is None else budget
    return (
        f"Warning: the context is about {context_tokens} tokens, over the limit "
        f"of {budget}. Continuing anyway (TOKEN_LIMIT_ACTION=continue): the model "
        f"may ignore the oldest part of the conversation."
    )


# ---------------------------------------------------------------------
# Usage display
# ---------------------------------------------------------------------

def format_usage(prompt_tokens: int, completion_tokens: int,
                 approximate: bool = False, budget: int | None = None,
                 threshold_ratio: float | None = None) -> str:
    """One short line describing the tokens used by an exchange.

    prompt_tokens      tokens sent to the model (history + new message)
    completion_tokens  tokens of the answer
    approximate        True when the numbers are estimates, not Ollama's
                       own count (shown with a leading ~)

    The context percentage only appears once usage reaches the threshold,
    so most of the time the line stays minimal."""
    budget = get_budget() if budget is None else budget
    threshold_ratio = get_threshold_ratio() if threshold_ratio is None else threshold_ratio

    mark = "~" if approximate else ""
    parts = [f"{mark}{prompt_tokens} in", f"{mark}{completion_tokens} out"]

    total = prompt_tokens + completion_tokens
    if budget > 0 and total >= budget * threshold_ratio:
        percent = round(total / budget * 100)
        detail = f"{mark}{total}/{budget}"
        if total > budget:
            detail += ", limit exceeded"
        parts.append(f"context {percent}% ({detail})")

    return "tokens: " + " · ".join(parts)


def small(text: str) -> str:
    """Render a line discreetly: dimmed when writing to a real terminal.
    No escape codes when the output is piped, or when NO_COLOR is set."""
    if sys.stdout.isatty() and "NO_COLOR" not in os.environ:
        return f"\033[2m{text}\033[0m"
    return text