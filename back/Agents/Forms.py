"""
[X4] Questions and forms: the assistant asks, the user answers in a form instead of typing.

A form is a PendingAction with fields (Agents/Confirmation.py), so it lives where a plan to
confirm lives: in the session, tied to its conversation, shown as a card in the web UI,
dropped by /cancel, never cached. Two kinds:

  * a question (the ask_user tool): one short question, with choices or not. The answer the
    user picks or types is sent to the chat as their next message, and the model goes on.
  * an action form (file_leave_request with something missing or wrong): prefilled with what
    the model understood. Submitting it IS the confirmation: the request is filed at once,
    with exactly the values the user saw and validated, checked again here.
  * a form of the model (the ask_form tool, off unless AGENT_ASK_FORM=true): a few fields the
    model describes itself. It only collects answers, sent back to the chat as one message:
    a form the model writes can never act. Its description is checked strictly (model_form).

In the terminal, a question shows numbered choices (typing the number is enough) and an
action form is asked field by field (Commands.fill_form_in_terminal).
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from Agents.Confirmation import PendingAction

KIND_CHOICE = "choice"
KIND_DATE = "date"
KIND_TEXT = "text"
MAX_OPTIONS = 6
MAX_OPTION_CHARS = 80
MAX_TEXT_CHARS = 500
MAX_FIELDS = 5
MAX_LABEL_CHARS = 80
KIND_ALIASES = {"text": KIND_TEXT, "string": KIND_TEXT, "free": KIND_TEXT, "date": KIND_DATE,
                "choice": KIND_CHOICE, "select": KIND_CHOICE, "radio": KIND_CHOICE, "options": KIND_CHOICE}


class FormError(ValueError):
    """The values cannot be used: `errors` maps a field name to what is wrong with it."""

    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(f"{name}: {message}" for name, message in errors.items()))
        self.errors = errors


@dataclass
class FormField:
    name: str
    label: str
    kind: str = KIND_TEXT
    options: list = field(default_factory=list)  # [(value, label)] for a choice
    value: str = ""                              # prefilled
    required: bool = True
    error: str = ""                              # why the prefilled value was not kept

    def option_label(self, value: str) -> str:
        return next((label for key, label in self.options if key == value), value)

    def as_dict(self) -> dict:
        return {"name": self.name, "label": self.label, "kind": self.kind,
                "options": [{"value": key, "label": label} for key, label in self.options],
                "value": self.value, "required": self.required, "error": self.error}


def _not_ready() -> str:
    raise RuntimeError("this form is waiting for the user's answers")


@dataclass
class PendingForm(PendingAction):
    fields: list = field(default_factory=list)
    # Action form: does the work with the cleaned values, returns the result text.
    # None: a question, whose answer goes back to the chat as the user's message.
    on_submit: Callable[[dict], str] | None = None
    submit_label: str = "Send"

    @property
    def is_question(self) -> bool:
        """The answers go back to the chat (ask_user, ask_form), nothing is done here."""
        return self.on_submit is None

    @property
    def kind(self) -> str:
        """question: one field, answered in the chat. answers: several fields, sent back as one
        message. action: filled in, then the work is done (a leave request)."""
        if not self.is_question:
            return "action"
        return "question" if len(self.fields) == 1 else "answers"

    def render(self) -> str:
        """What the chat shows and keeps while the form waits."""
        lines = [f"=== {self.title} ===", self.plan]
        for item in self.fields:
            if item.kind == KIND_CHOICE:
                choices = "   ".join(f"{i}. {label}" for i, (_, label) in enumerate(item.options, start=1))
                lines.append(f"  {choices}" if self.kind == "question" else f"  {item.label}: {choices}")
            elif self.kind != "question":
                shown = item.value or "(to fill in)"
                lines.append(f"  {item.label}: {shown}{'' if item.required else ' (optional)'}")
        if self.kind == "question":
            lines.append("Answer with a number, or in your own words.")
        elif self.kind == "answers":
            lines.append("Fill in the form (/form in the terminal): the answers go back to the assistant.")
        else:
            lines.append("Nothing has been done yet. Complete the form, or /cancel to drop it.")
        return "\n".join(lines)

    def settled(self, outcome: str) -> str:
        return f"=== {self.title} ===\n{self.plan}\n{outcome}"

    def as_dict(self) -> dict:
        return {"kind": self.kind, "submit_label": self.submit_label,
                "fields": [item.as_dict() for item in self.fields]}

    def clean(self, values: dict) -> dict:
        """The values as strings, checked against the fields. Raises FormError."""
        cleaned, errors = {}, {}
        for item in self.fields:
            raw = values.get(item.name)
            value = " ".join(str(raw).split()) if raw is not None else ""
            if item.kind == KIND_CHOICE and value and self.kind == "question" and value.isdigit() \
                    and 1 <= int(value) <= len(item.options):
                value = item.options[int(value) - 1][0]  # "2" in the terminal
            if not value:
                if item.required:
                    errors[item.name] = "required"
                cleaned[item.name] = ""
                continue
            if item.kind == KIND_CHOICE and self.kind != "question" and value not in {key for key, _ in item.options}:
                errors[item.name] = "choose one of the options"
            elif item.kind == KIND_DATE:
                try:
                    value = date.fromisoformat(value).isoformat()
                except ValueError:
                    errors[item.name] = "a date YYYY-MM-DD"
            elif len(value) > MAX_TEXT_CHARS:
                errors[item.name] = f"{MAX_TEXT_CHARS} characters at most"
            cleaned[item.name] = value
        if errors:
            raise FormError(errors)
        return cleaned

    def submit(self, values: dict) -> str:
        """A question: the answer text. A form of the model: its answers as one message.
        An action form: the work is done, the result text."""
        cleaned = self.clean(values)
        if self.kind == "question":
            item = self.fields[0]
            return item.option_label(cleaned[item.name])
        if self.kind == "answers":
            return "\n".join(f"{item.label}: {item.option_label(cleaned[item.name]) or '(no answer)'}"
                             for item in self.fields)
        return self.on_submit(cleaned)


def question_form(question, options=None) -> PendingForm:
    """[X4] ask_user: one question from the model, with up to six short choices."""
    question = " ".join(str(question or "").split())
    if not question:
        raise ValueError("the question is empty")
    choices = []
    for option in options or []:
        option = " ".join(str(option).split())[:MAX_OPTION_CHARS]
        if option and option not in choices:
            choices.append(option)
    choices = choices[:MAX_OPTIONS]
    answer = FormField("answer", question, KIND_CHOICE if choices else KIND_TEXT, [(c, c) for c in choices])
    return PendingForm("Question", question, _not_ready, fields=[answer], submit_label="Send")


def _short(value, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def model_form(title, fields) -> PendingForm:
    """[X4] ask_form: a form the model describes itself. Checked strictly: 1 to 5 fields, each with
    a label and a known kind; a choice needs 2 to 6 options. Anything else is refused with a clear
    message, which goes back to the model like any bad tool call. It only collects answers."""
    title = _short(title, MAX_LABEL_CHARS)
    if not title:
        raise ValueError("give the form a short title")
    if not isinstance(fields, list) or not 1 <= len(fields) <= MAX_FIELDS:
        raise ValueError(f"fields must be a list of 1 to {MAX_FIELDS} fields")
    built, labels = [], set()
    for index, spec in enumerate(fields, start=1):
        if not isinstance(spec, dict):
            raise ValueError(f"field {index} must be an object with a label")
        label = _short(spec.get("label") or spec.get("name") or spec.get("question"), MAX_LABEL_CHARS)
        if not label or label.lower() in labels:
            raise ValueError(f"field {index} needs its own label")
        kind = KIND_ALIASES.get(str(spec.get("kind") or spec.get("type") or "text").strip().lower())
        if kind is None:
            raise ValueError(f"field {index} ({label}): kind must be text, date or choice")
        options = []
        for option in spec.get("options") or []:
            option = _short(option, MAX_OPTION_CHARS)
            if option and option not in options:
                options.append(option)
        if kind == KIND_CHOICE and not 2 <= len(options) <= MAX_OPTIONS:
            raise ValueError(f"field {index} ({label}): a choice needs 2 to {MAX_OPTIONS} options")
        labels.add(label.lower())
        built.append(FormField(f"field_{index}", label, kind, [(o, o) for o in options] if kind == KIND_CHOICE else [],
                               required=spec.get("required") is not False))
    return PendingForm(title, title, _not_ready, fields=built, submit_label="Send")
