"""Prepare a leave request; it is saved only on /confirm."""

from datetime import date

from Agents.Confirmation import PendingAction
from Memories.Leaves import save_leave_request

LEAVE_TYPES = (
    "paid_leave",
    "sick_leave",
    "marriage",
    "bereavement",
    "remote_work",
    "unpaid_leave",
    "other",
)


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
