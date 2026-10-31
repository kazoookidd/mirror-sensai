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

from Agents.Guardrails import DEFAULT_OUTPUT, OUTPUT_ACTIONS
from Memories.TokenLimit import DEFAULT_ACTION, LIMIT_ACTIONS
from Runtime.Parameters import (
    MAX_NUM_PREDICT,
    MAX_SEED,
    MAX_TEMPERATURE,
    MIN_NUM_PREDICT,
    MIN_SEED,
    MIN_TEMPERATURE,
    describe_option,
    describe_temperature,
    parse_num_predict,
    parse_seed,
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


def parse_output_action_strict(text: str) -> tuple[str | None, str | None]:
    action = text.strip().lower()
    if action in OUTPUT_ACTIONS:
        return action, None
    if action in ("default", "reset"):
        return DEFAULT_OUTPUT, None
    return None, f"'{text}' is not a valid action (expected: {' or '.join(OUTPUT_ACTIONS)})."


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
    Setting(
        name="cache",
        attribute="semantic_cache",
        summary="answer a question that means the same as an earlier one from the cache (no model call)",
        accepted="on or off",
        parse=parse_switch,
        describe=describe_switch,
        aliases=("semantic-cache",),
    ),
    Setting(
        name="documents",
        attribute="hr_documents",
        summary="search the HR documents for each question (off = the model's own knowledge only)",
        accepted="on or off",
        parse=parse_switch,
        describe=describe_switch,
        aliases=("hr-documents", "rag"),
    ),
    Setting(
        name="guardrails",
        attribute="guardrails",
        summary="block out-of-scope or unsafe questions, and screen answers for personal details",
        accepted="on or off",
        parse=parse_switch,
        describe=describe_switch,
    ),
    Setting(
        name="guardrails-output",
        attribute="guardrails_output",
        summary="what to do when an answer contains personal details",
        accepted=" or ".join(OUTPUT_ACTIONS),
        parse=parse_output_action_strict,
        describe=str,
        aliases=("guardrail-output",),
    ),
    Setting(
        name="seed",
        attribute="seed",
        summary="same seed + same question + same settings = same answer",
        accepted=f"a whole number, {MIN_SEED} to {MAX_SEED}, or 'default' (not fixed)",
        parse=parse_seed,
        describe=describe_option,
    ),
    Setting(
        name="num-predict",
        attribute="num_predict",
        summary="maximum length of an answer, in tokens (too low cuts it short)",
        accepted=f"{MIN_NUM_PREDICT} to {MAX_NUM_PREDICT}, or 'default' for the model's own value",
        parse=parse_num_predict,
        describe=describe_option,
        aliases=("max-tokens", "max-length"),
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
