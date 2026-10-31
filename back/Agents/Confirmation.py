"""
[A3] Human in the loop.

Before a critical or irreversible action, the agent suspends, presents its
plan to the user, and only proceeds after explicit confirmation.

A critical tool (tools.json: "critical": true) never acts. Its function only
PREPARES the action and returns a PendingAction: the plan to show, and the
function that really does the work. The agent stops there, the plan is shown
to the user, and `execute` runs only when the user types /confirm. /cancel
(or a new request) drops it. The user only confirms: the data that is run is
exactly the data that was shown, it is never sent back by the client.
"""

from dataclasses import dataclass
from typing import Callable


@dataclass
class PendingAction:
    title: str                    # short name of the action: "Leave request to confirm"
    plan: str                     # what will be done, as the user reads it
    execute: Callable[[], str]    # does the work; returns the result text for the user
    conversation_id: int | None = None  # where it was prepared: the web shows its card in that chat only

    def render(self) -> str:
        """What the user sees while the agent is suspended."""
        return (f"=== {self.title} ===\n{self.plan}\n"
                "Nothing has been done yet. Type /confirm to go ahead, or /cancel to drop it.")

    def settled(self, outcome: str) -> str:
        """What the conversation keeps once the user confirmed or cancelled."""
        return f"=== {self.title.removesuffix(' to confirm')} ===\n{self.plan}\n{outcome}"
