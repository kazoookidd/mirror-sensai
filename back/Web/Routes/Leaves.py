"""[M1] The HR view of the leave requests: every employee's, and HR's decision on each.
For HR accounts only. The role is read from the server session, never from the browser:
an employee gets 403 even if they call the routes by hand."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from Memories.Auth import ROLE_HR
from Memories.Leaves import HR_DECISIONS, LEAVE_TYPES, STATUS_LABELS, decide_leave_request, list_all_leave_requests
from Web.Sessions import WebSession, current

router = APIRouter()


class Decision(BaseModel):
    status: str


def hr_only(web: WebSession = Depends(current)) -> WebSession:
    """FastAPI dependency: the session of an HR account, 403 for anyone else."""
    if web.session.account_role != ROLE_HR:
        raise HTTPException(status_code=403, detail="Only HR accounts can see the leave requests of every employee.")
    return web


def _view(request: dict) -> dict:
    return {**request,
            "type_label": LEAVE_TYPES.get(request["leave_type"], request["leave_type"]),
            "status_label": STATUS_LABELS.get(request["status"], request["status"])}


@router.get("/leave-requests")
def leave_requests(web: WebSession = Depends(hr_only)):
    return {
        "requests": [_view(request) for request in list_all_leave_requests()],
        "types": LEAVE_TYPES,
        "statuses": STATUS_LABELS,
        "decisions": list(HR_DECISIONS),
    }


@router.put("/leave-requests/{request_id}")
def decide(request_id: int, decision: Decision, web: WebSession = Depends(hr_only)):
    """Approve, refuse, or put back to pending. A request the employee cancelled stays cancelled."""
    try:
        return {"request": _view(decide_leave_request(request_id, decision.status, web.session.user_id))}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=f"{e}: it cannot be decided any more.")
