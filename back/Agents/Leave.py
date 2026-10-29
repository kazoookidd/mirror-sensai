"""Prepare a leave request, or its cancellation; either is done only on /confirm ([A3])."""

from datetime import date

from Agents.Confirmation import PendingAction
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


def prepare_leave_request(session, leave_type: str, start_date: str, end_date: str,
                          reason: str = "") -> PendingAction:
    if leave_type not in LEAVE_TYPES:
        raise ValueError("leave_type must be one of: " + ", ".join(LEAVE_TYPES))
    start = _parse_day(start_date, "start_date")
    end = _parse_day(end_date, "end_date")
    if end < start:
        raise ValueError("end_date must not be before start_date")
    data = {
        "leave_type": leave_type,
        "start_date": start,
        "end_date": end,
        "reason": reason or "",
    }
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
