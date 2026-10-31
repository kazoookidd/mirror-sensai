"""
Interceptors on every chat turn, before the model and after the answer.

The system prompt already asks the model not to talk about another employee.
This module does not trust that: a small model, a jailbreak, or a cached
answer can still leak. The same rules run in the terminal and in the web UI,
because both go through chat_turn.

  * input: a question about another employee's salary or situation, or a
    prompt that tries to drop the assistant's rules, is refused before the
    cache, the documents and the model. Personal numbers (e-mail, phone,
    NIR, IBAN, card) are replaced by [kind] in what the model sees and in
    what is stored.
  * output: the same numbers are redacted in the answer (or the whole
    answer is refused, GUARDRAILS_OUTPUT=refuse). What was streamed is
    replaced. An answer that names another employee's personal data is
    never shown.

The web tools have their own filter (Tools/privacy.py): they clean what
leaves the machine. This module is the chat, both directions.

Turned off with GUARDRAILS=false or /settings guardrails off: the system
prompt is then the only guard.
"""

import re
from dataclasses import dataclass

from Tools.privacy import mask

ACTION_REDACT = "redact"
ACTION_REFUSE = "refuse"
OUTPUT_ACTIONS = (ACTION_REDACT, ACTION_REFUSE)
DEFAULT_OUTPUT = ACTION_REDACT

# Words that follow "salaire de" / "NIR de" in HR French without naming a person.
_NOT_A_PERSON = {
    "base", "brut", "net", "reference", "référence", "depart", "départ",
    "remplacement", "convention", "travail", "formation", "cadre", "cadres",
    "entreprise", "employeur", "salarie", "salarié", "salariee", "salariée",
    "salaries", "salariés", "employe", "employé", "employee", "employees",
    "employes", "employés", "personne", "personnes", "collaborateur",
    "collaborateurs", "agent", "agents", "annee", "année", "mois", "semaine",
    "la", "le", "les", "un", "une", "du", "des", "ce", "cet", "cette", "ces",
    "mon", "ma", "mes", "notre", "nos", "my", "our", "the", "a", "an",
}

_STRICT_PRIVATE = (
    r"salaire|r[ée]mun[ée]ration|paie|fiche de paie|pay.?slip|salary|"
    r"nir|num[ée]ro de s[ée]cu(?:rit[ée] sociale)?|"
    r"situation personnelle|dossier rh"
)
_LEAVE_PRIVATE = r"cong[ée]s?|rtt|absences?|arr[êe]t maladie"

_COLLEAGUE = re.compile(
    r"\b(?:coll[eè]gues?|coworkers?|co-workers?|"
    r"(?:un|une|d['']autres?|des autres|les autres|another|other)\s+"
    r"(?:salari[ée]s?|employ[ée]s?|coll[eè]gues?|personnes?|employees?)|"
    r"tout le monde|everyone)\b",
    re.IGNORECASE,
)
_PRIVATE_TOPIC = re.compile(rf"\b(?:{_STRICT_PRIVATE}|{_LEAVE_PRIVATE})\b", re.IGNORECASE)

_HOW_MUCH = re.compile(
    r"\bcombien\s+(?:gagne|per[cç]oit|touche)\s+(?!je\b|j'|tu\b|vous\b|on\b|nous\b)",
    re.IGNORECASE,
)
_HOW_MUCH_EN = re.compile(
    r"\bhow much (?:does|do)\s+(?!i\b|we\b|you\b)",
    re.IGNORECASE,
)
_POSSESSIVE_EN = re.compile(
    r"\b[A-Z][\w-]+'s\s+(?:salary|pay|pay\s+slip|absences?|leave)\b",
)

_STRICT_OF = re.compile(
    rf"\b(?:{_STRICT_PRIVATE})\s+(?:(?:de|du|of)\s+|d')([A-Za-zÀ-ÿ][\w'-]*)",
    re.IGNORECASE,
)
_LEAVE_OF_NAME = re.compile(
    rf"\b(?:{_LEAVE_PRIVATE})\s+(?:(?:de|du|of)\s+|d')([A-Za-zÀ-ÿ][\w'-]*)",
    re.IGNORECASE,
)

_JAILBREAK = re.compile(
    r"(?:ignore|oublie|forget|disregard)\s+(?:\w+\s+){0,4}"
    r"(?:instructions?|consignes?|r[èe]gles?|rules?|system prompt|prompt syst[eè]me)"
    r"|(?:r[ée]v[eè]le|montre|affiche|dump|show)\s+(?:\w+\s+){0,3}"
    r"(?:system prompt|prompt syst[eè]me|tes instructions|tes consignes|your instructions)"
    r"|you are now (?:dan|jailbroken|unrestricted)"
    r"|tu es maintenant (?:dan|sans r[èe]gles)"
    r"|developer mode|jailbreak|do anything now"
    r"|sans aucune restriction|without any restrictions",
    re.IGNORECASE,
)
_DAN = re.compile(r"(?<![A-Za-z])DAN(?![A-Za-z])")

_PLACEHOLDER = re.compile(
    r"\[(?:e-mail|IBAN|social security number|card number|phone number)\]"
)

REFUSED_MARKER = "Refused:"


@dataclass
class Screen:
    """The result of one interceptor. `text` is what continues (input) or
    what may be shown (output). On a block, `message` is what the user sees."""
    text: str
    blocked: bool = False
    message: str = ""
    note: str = ""
    changed: bool = False


def parse_output_action(value: str | None) -> tuple[str, str | None]:
    """Turn GUARDRAILS_OUTPUT into redact or refuse.
    An invalid value falls back to redact (the answer is still shown, cleaned)."""
    if value is None or not value.strip():
        return DEFAULT_OUTPUT, None
    action = value.strip().lower()
    if action in OUTPUT_ACTIONS:
        return action, None
    return DEFAULT_OUTPUT, (
        f"unknown guardrails output action '{value}' "
        f"(expected: {' or '.join(OUTPUT_ACTIONS)}), using '{DEFAULT_OUTPUT}'"
    )


def enabled(session) -> bool:
    return bool(getattr(session, "guardrails", True))


def inspect_input(text: str) -> Screen:
    """Refuse or clean a user message. Call before the cache and the model."""
    if is_jailbreak(text):
        return Screen(text, blocked=True, message=(
            f"{REFUSED_MARKER} this message tries to drop the assistant's rules. "
            f"Sensai keeps them: it is the internal HR assistant, and it will not ignore them."
        ))
    if asks_about_another_employee(text):
        return Screen(text, blocked=True, message=(
            f"{REFUSED_MARKER} this question asks about another employee "
            f"(salary, absences, personal situation). Sensai does not give that information. "
            f"Ask about the rules, or about your own situation."
        ))
    cleaned, found = mask(text)
    if not found:
        return Screen(text)
    if not _PLACEHOLDER.sub("", cleaned).strip():
        return Screen(text, blocked=True, message=(
            f"{REFUSED_MARKER} your message only contained personal details "
            f"({_join(found)}). It was not sent."
        ))
    return Screen(cleaned, changed=True,
                  note=f"Personal details were removed from your message before it was sent: {_join(found)}.")


def inspect_output(text: str, action: str = DEFAULT_OUTPUT) -> Screen:
    """Refuse or clean a model answer. Call after generate_reply, before it is saved."""
    if asks_about_another_employee(text):
        return Screen(text, blocked=True, changed=True, message=(
            f"{REFUSED_MARKER} the answer was about another employee's personal situation. "
            f"It was not shown. Ask the HR department."
        ))
    cleaned, found = mask(text)
    if not found:
        return Screen(text)
    kinds = _join(found)
    if action == ACTION_REFUSE:
        return Screen(text, blocked=True, changed=True, message=(
            f"{REFUSED_MARKER} the answer contained personal details ({kinds}). "
            f"It was not shown. Rephrase without them, or ask the HR department."
        ))
    return Screen(cleaned, changed=True,
                  note=f"Personal details were removed from the answer: {kinds}.")


def asks_about_another_employee(text: str) -> bool:
    """Salary, NIR or absences of a named person or a colleague, not 'mon salaire'
    and not the company rules ('salaire de base', 'congés de maternité')."""
    if _HOW_MUCH.search(text) or _HOW_MUCH_EN.search(text) or _POSSESSIVE_EN.search(text):
        return True
    if _PRIVATE_TOPIC.search(text) and _COLLEAGUE.search(text):
        return True
    if any(_is_person(name, require_capital=False) for name in _STRICT_OF.findall(text)):
        return True
    if any(_is_person(name, require_capital=True) for name in _LEAVE_OF_NAME.findall(text)):
        return True
    return False


def is_jailbreak(text: str) -> bool:
    return _JAILBREAK.search(text) is not None or _DAN.search(text) is not None


def _is_person(name: str, require_capital: bool) -> bool:
    if require_capital and not name[:1].isupper():
        return False
    if not any(c.isalpha() for c in name):
        return False
    return name.casefold() not in _NOT_A_PERSON


def _join(kinds: list[str]) -> str:
    return ", ".join(kinds)
