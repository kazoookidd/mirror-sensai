import json
from datetime import date
from typing import Callable

import requests

from StructuredOutput.Schema import validate

DEFAULT_MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 120

LEAVE_TYPES = [
    "paid_leave",
    "sick_leave",
    "marriage",
    "bereavement",
    "remote_work",
    "unpaid_leave",
    "other",
]

LEAVE_REQUEST_SCHEMA = {
    "type": "object",
    "properties": {
        "leave_type": {"type": "string", "enum": LEAVE_TYPES},
        "start_date": {"type": "string", "format": "date"},
        "end_date": {"type": "string", "format": "date"},
        "reason": {"type": "string", "maxLength": 300},
    },
    "required": ["leave_type", "start_date", "end_date", "reason"],
    "additionalProperties": False,
}

LEAVE_INSTRUCTIONS = (
    "You extract a leave request from the user's message. "
    "Today's date is {today}: use it to resolve relative dates such as "
    "'next Monday'. Dates must be formatted YYYY-MM-DD. "
    "If the message gives a single day, start_date and end_date are the same. "
    "leave_type must be one of: " + ", ".join(LEAVE_TYPES) + ". "
    "reason is a short summary in the user's language (empty string if none)."
)


class StructuredOutputError(Exception):
    """The model could not produce a valid structured answer."""


def check_leave_dates(data: dict) -> list[str]:
    """Business rule the schema cannot express: the leave cannot end
    before it starts."""
    if data["end_date"] < data["start_date"]:
        return ["$.end_date: must not be before start_date"]
    return []


def _ask(base_url: str, model: str, messages: list, schema: dict) -> str:
    try:
        response = requests.post(
            f"{base_url}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "format": schema,
                "options": {"temperature": 0},
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]
    except requests.exceptions.ConnectionError:
        raise StructuredOutputError(
            "cannot connect to Ollama. Is it running? (ollama serve)") from None
    except requests.exceptions.Timeout:
        raise StructuredOutputError("Ollama took too long to answer.") from None
    except requests.exceptions.HTTPError as e:
        raise StructuredOutputError(f"model unavailable or bad request ({e})") from None
    except (KeyError, ValueError):
        raise StructuredOutputError("unexpected response format from Ollama.") from None


def extract_structured(
    text: str,
    schema: dict,
    instructions: str,
    base_url: str,
    model: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    extra_check: Callable[[dict], list[str]] | None = None,
) -> dict:
    """Return a dict extracted from `text` that is guaranteed to respect
    `schema` (and `extra_check`, if given). Raises StructuredOutputError
    when the model still fails after `max_attempts` attempts or when Ollama
    is unreachable (connection errors are not retried)."""
    if not text.strip():
        raise StructuredOutputError("empty input.")

    messages = [
        {"role": "system", "content": instructions},
        {"role": "user", "content": text},
    ]
    problems: list[str] = []

    for _ in range(max_attempts):
        raw = _ask(base_url, model, messages, schema)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            problems = [f"the reply is not valid JSON ({e.msg})"]
        else:
            problems = validate(data, schema)
            if not problems and extra_check:
                problems = extra_check(data)
            if not problems:
                return data

        # Show the model its own mistake so the next attempt can fix it.
        messages.append({"role": "assistant", "content": raw})
        messages.append({
            "role": "user",
            "content": "Your answer is invalid:\n- " + "\n- ".join(problems)
                       + "\nAnswer again with corrected JSON only.",
        })

    raise StructuredOutputError(
        f"no valid answer after {max_attempts} attempts: " + "; ".join(problems))


def extract_leave_request(
    text: str,
    base_url: str,
    model: str,
    today: date | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> dict:
    """Turn a free-text sentence ("I want next Monday to Wednesday off")
    into {"leave_type", "start_date", "end_date", "reason"}."""
    today = today or date.today()
    return extract_structured(
        text,
        LEAVE_REQUEST_SCHEMA,
        LEAVE_INSTRUCTIONS.format(today=today.isoformat()),
        base_url,
        model,
        max_attempts=max_attempts,
        extra_check=check_leave_dates,
    )
