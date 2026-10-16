"""
Runtime settings: the knobs of the assistant that can be changed while the
chat is running, with /settings.

Every setting lives on the Session and has the same three parts: how to
read what the user typed (a strict parser, nothing is silently corrected),
how to display the value, and a one-line hint. Adding a setting means
adding one entry to SETTINGS; /settings, /help and the error messages pick
it up from there.

This module does not import Commands.py (which imports it): it only reads
and writes attributes on the session object it is given.
"""

from dataclasses import dataclass
from typing import Any, Callable

from Memories.TokenLimit import DEFAULT_ACTION, LIMIT_ACTIONS
from Runtime.Parameters import (
    MAX_TEMPERATURE,
    MIN_TEMPERATURE,
    describe_temperature,
    parse_temperature,
)

Parser = Callable[[str], tuple[Any, str | None]]

_TRUE_WORDS = {"1", "true", "yes", "on"}
_FALSE_WORDS = {"0", "false", "no", "off"}


def parse_limit_action_strict(text: str) -> tuple[str | None, str | None]:

    action = text.strip().lower()
    if action in LIMIT_ACTIONS:
        return action, None
    if action in ("default", "reset"):
        return DEFAULT_ACTION, None
    return None, f"'{text}' is not a valid action (expected: {', '.join(LIMIT_ACTIONS)})."


def parse_switch(text: str) -> tuple[bool | None, str | None]:
    word = text.strip().lower()
    if word in _TRUE_WORDS:
        return True, None
    if word in _FALSE_WORDS:
        return False, None
    return None, f"'{text}' is not a valid value (expected: on or off)."


def describe_switch(value: bool) -> str:
    return "on" if value else "off"


@dataclass(frozen=True)
class Setting:
    name: str
    attribute: str
    summary: str
    accepted: str
    parse: Parser
    describe: Callable[[Any], str]
    aliases: tuple[str, ...] = ()


SETTINGS: tuple[Setting, ...] = (
    Setting(
        name="temperature",
        attribute="temperature",
        summary="how creative the answers are (low = precise, high = creative)",
        accepted=f"{MIN_TEMPERATURE:g} to {MAX_TEMPERATURE:g}, or 'default' for the model's own value",
        parse=parse_temperature,
        describe=describe_temperature,
        aliases=("temp",),
    ),
    Setting(
        name="token-limit",
        attribute="token_limit_action",
        summary="what to do when the context is over the token limit",
        accepted=" or ".join(LIMIT_ACTIONS),
        parse=parse_limit_action_strict,
        describe=str,
        aliases=("on-token-limit", "token-limit-action"),
    ),
    Setting(
        name="token-usage",
        attribute="show_token_usage",
        summary="show the token usage line under each answer",
        accepted="on or off",
        parse=parse_switch,
        describe=describe_switch,
        aliases=("show-token-usage",),
    ),
)


def normalize_name(name: str) -> str:
    """'Token_Limit' and 'token-limit' are the same setting."""
    return name.strip().lower().replace("_", "-")


def find_setting(name: str) -> Setting | None:
    wanted = normalize_name(name)
    for setting in SETTINGS:
        if wanted == setting.name or wanted in setting.aliases:
            return setting
    return None


def current_value(session, setting: Setting) -> str:
    return setting.describe(getattr(session, setting.attribute))


def apply_setting(session, setting: Setting, text: str) -> tuple[str | None, str | None]:
    """Parse `text` and store it on the session.
    Returns (new value as displayed, error). On error nothing is changed."""
    value, error = setting.parse(text)
    
    if error:
        return None, error
    setattr(session, setting.attribute, value)
    return setting.describe(value), None
