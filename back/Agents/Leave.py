"""Prepare a leave request, or its cancellation; either is done only on /confirm ([A3]).
A request with something missing or wrong becomes a form the user completes ([X4])."""

from datetime import date

from Agents.Confirmation import PendingAction
from Agents.Forms import KIND_CHOICE, KIND_DATE, FormError, FormField, PendingForm, _not_ready
from Memories.Leaves import LEAVE_TYPES, cancel_leave_request, pending_requests_starting, save_leave_request


def describe_leave_request(data: dict) -> str:
    lines = [f"  type:   {data['leave_type']}",
             f"  from:   {data['start_date']}",
             f"  to:     {data['end_date']}"]
    if data["reason"]:
        lines.append(f"  reason: {data['reason']}")
    return "\n".join(lines)


def _parse_day(value: str, field: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a date YYYY-MM-DD") from None


def leave_problems(leave_type: str, start_date: str, end_date: str) -> tuple[dict, dict]:
    """(the valid values, what is wrong with the others), by field."""
    valid, problems = {}, {}
    if leave_type in LEAVE_TYPES:
        valid["leave_type"] = leave_type
    else:
        problems["leave_type"] = "choose the type of leave" if not leave_type else f"'{leave_type}' is not a type of leave"
    for name, value in (("start_date", start_date), ("end_date", end_date)):
        try:
            valid[name] = _parse_day(value, name)
        except ValueError:
            problems[name] = "required" if not value else f"'{value}' is not a date YYYY-MM-DD"
    if "start_date" in valid and "end_date" in valid and valid["end_date"] < valid["start_date"]:
        problems["end_date"] = "must not be before the first day"
        del valid["end_date"]
    return valid, problems


def leave_form(session, leave_type: str = "", start_date: str = "", end_date: str = "", reason: str = "") -> PendingForm:
    """[X4] The leave request as a form, prefilled with what the model understood. Submitting
    it is the confirmation (A3): the request is filed with exactly the values the user validated."""
    valid, problems = leave_problems(leave_type or "", start_date or "", end_date or "")
    user_id = session.user_id

    def submit(values: dict) -> str:
        cleaned, wrong = leave_problems(values["leave_type"], values["start_date"], values["end_date"])
        if wrong:
            raise FormError(wrong)
        data = {**cleaned, "reason": values.get("reason", "")}
        request_id = save_leave_request(user_id, data)
        return (f"Leave request #{request_id} saved for {user_id}:\n{describe_leave_request(data)}\n"
                f"See all yours with /leaves.")

    fields = [
        FormField("leave_type", "Type", KIND_CHOICE, list(LEAVE_TYPES.items()), valid.get("leave_type", ""),
                  error=problems.get("leave_type", "")),
        FormField("start_date", "First day", KIND_DATE, value=valid.get("start_date", ""), error=problems.get("start_date", "")),
        FormField("end_date", "Last day", KIND_DATE, value=valid.get("end_date", ""), error=problems.get("end_date", "")),
        FormField("reason", "Reason", value=" ".join((reason or "").split()), required=False),
    ]
    return PendingForm("Leave request to complete", f"Complete your leave request, {user_id}:", _not_ready,
                       fields=fields, on_submit=submit, submit_label="File the request")


def prepare_leave_request(session, leave_type: str = "", start_date: str = "", end_date: str = "",
                          reason: str = "") -> PendingAction:
    """Everything understood: a plan to confirm. Something missing or wrong: a form [X4]."""
    valid, problems = leave_problems(leave_type or "", start_date or "", end_date or "")
    if problems:
        return leave_form(session, leave_type, start_date, end_date, reason)
    data = {**valid, "reason": reason or ""}
    user_id = session.user_id

    def execute() -> str:
        request_id = save_leave_request(user_id, data)
        return (f"Leave request #{request_id} saved for {user_id}. "
                f"See all yours with /leaves.")

    plan = f"I will file this leave request for {user_id}:\n{describe_leave_request(data)}"
    return PendingAction("Leave request to confirm", plan, execute)


def prepare_cancellation(session, start_date: str) -> PendingAction:
    """The model only gives the first day of the leave: the request is looked for among the
    pending requests of the session's user, never of anyone else."""
    start = _parse_day(start_date, "start_date")
    user_id = session.user_id
    matches = pending_requests_starting(user_id, start)
    if not matches:
        raise ValueError(f"{user_id} has no pending leave request starting on {start}. "
                         "Ask the user which leave to cancel (its first day).")
    request = matches[0]  # the most recent one, if the same day was filed twice

    def execute() -> str:
        if not cancel_leave_request(user_id, request["id"]):
            return f"Leave request #{request['id']} was not pending any more: nothing changed."
        return f"Leave request #{request['id']} cancelled. See all yours with /leaves."

    plan = (f"I will cancel this leave request of {user_id}:\n"
            f"  request: #{request['id']}\n{describe_leave_request(request)}")
    return PendingAction("Leave cancellation to confirm", plan, execute)
