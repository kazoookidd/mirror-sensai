"""
What leaves the machine.

The model, the chats and the HR documents stay local. The only things sent
outside are what the web tools send: a search query (Brave, Tavily, Exa) and
the address of a page to read. The model writes them itself, so it can copy a
personal detail of the user into them ("congé mariage sophie.martin@acme.fr").
Every query and every address goes through this module first.

Caught: e-mail addresses, phone numbers, French social security numbers (NIR),
IBANs, card numbers, and the logged-in user's own id and e-mail. A name typed
in free text is NOT caught: the tool guidance asks the model to search for the
general rule, never for a person (Agents/ReAct.py).
"""

import re


def _luhn(number: str) -> bool:
    """The checksum of card numbers: keeps long numbers that are not cards (years, ids) out."""
    digits = [int(c) for c in number if c.isdigit()]
    total = 0
    for i, digit in enumerate(reversed(digits)):
        if i % 2:
            digit = digit * 2 - 9 if digit > 4 else digit * 2
        total += digit
    return total % 10 == 0


# (kind shown to the user, pattern, extra check). Order matters: the most specific first.
PATTERNS = (
    ("e-mail", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), None),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,3})?\b"), None),
    ("social security number", re.compile(
        r"\b[12][ .]?\d{2}[ .]?(?:0[1-9]|1[0-2]|[2-9]\d)[ .]?(?:\d{2}|2[AB])[ .]?\d{3}[ .]?\d{3}(?:[ .]?\d{2})?\b"), None),
    ("card number", re.compile(r"\b\d{4}(?:[ -]?\d{4}){2}[ -]?\d{1,7}\b"), _luhn),
    ("phone number", re.compile(r"(?:(?<![\w+])\+|\b00)\d{1,3}[ .-]?[1-9](?:[ .-]?\d{2}){4}\b"
                                r"|\b0[1-9](?:[ .-]?\d{2}){4}\b"), None),
)

MIN_IDENTIFIER_CHARS = 3  # a 2-letter user id ("rh") would remove ordinary words


def identifiers(user_id: str | None, email: str | None = None) -> tuple[str, ...]:
    """What identifies the logged-in user: their id, its parts (sophie.martin -> sophie, martin)
    and their e-mail."""
    values = {email} if email else set()
    if user_id:
        values.add(user_id)
        values.update(re.split(r"[._-]+", user_id))
    return tuple(v for v in values if v and len(v) >= MIN_IDENTIFIER_CHARS)


def redact(text: str, known: tuple[str, ...] = ()) -> tuple[str, list[str]]:
    """`text` without the personal details it contains, and the kinds of details removed
    (never their values: the list is shown to the user and to the model)."""
    found: list[str] = []

    for kind, pattern, valid in PATTERNS:
        def drop(match, kind=kind, valid=valid):
            if valid is not None and not valid(match.group()):
                return match.group()
            found.append(kind)
            return " "
        text = pattern.sub(drop, text)

    # The longest first, so the e-mail goes before the user id it may contain.
    for value in sorted(known, key=len, reverse=True):
        pattern = re.compile(rf"(?<!\w){re.escape(value)}(?!\w)", re.IGNORECASE)
        if pattern.search(text):
            found.append("your user id")
            text = pattern.sub(" ", text)

    return " ".join(text.split()), list(dict.fromkeys(found))
