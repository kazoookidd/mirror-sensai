"""
Tests for the leave requests: their status, cancelling one ([A3], cancel_leave_request) and the
HR view ([M1], /leaves all). The database is a temporary file; no Ollama is needed.

Usage (from the project root):
    python back/tests/Test_leaves.py
"""

import io
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Agents.Confirmation import PendingAction
from Agents.Leave import prepare_cancellation
from Agents.Router import asks_for_leave
from Agents.Setup import build_registry
from Commands import Session, handle_command
from Memories import Database
from Memories.Auth import ROLE_EMPLOYEE, ROLE_HR, create_user
from Memories.Leaves import (LEAVE_TYPES, STATUS_APPROVED, STATUS_CANCELLED, STATUS_PENDING, STATUS_REFUSED,
                             cancel_leave_request, decide_leave_request, list_all_leave_requests,
                             list_leave_requests, save_leave_request)

NOVEMBER = {"leave_type": "paid_leave", "start_date": "2026-11-03", "end_date": "2026-11-07", "reason": "vacances"}


class LeaveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patch = mock.patch.object(Database, "DB_PATH", os.path.join(self.tmp.name, "t.db"))
        patch.start(); self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)
        Database.init_db()
        create_user("sophie", "sophie@example.com", "pw", role=ROLE_EMPLOYEE)
        create_user("paul", "paul@example.com", "pw", role=ROLE_EMPLOYEE)
        create_user("marc", "marc@example.com", "pw", role=ROLE_HR)

    def session(self, user_id="sophie", role=ROLE_EMPLOYEE):
        return Session(user_id=user_id, conversation_id=1, model="m", persona_id="default", personas={},
                       ollama_url="x", search_motor="tavily", account_role=role)

    def command(self, session, text) -> str:
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertTrue(handle_command(session, text))
        return buf.getvalue()


class TestStore(LeaveTest):
    def test_a_new_request_is_pending(self):
        save_leave_request("sophie", NOVEMBER)
        self.assertEqual(list_leave_requests("sophie")[0]["status"], STATUS_PENDING)

    def test_only_the_owner_cancels_and_only_once(self):
        request_id = save_leave_request("sophie", NOVEMBER)
        self.assertFalse(cancel_leave_request("paul", request_id))
        self.assertTrue(cancel_leave_request("sophie", request_id))
        self.assertFalse(cancel_leave_request("sophie", request_id))
        self.assertEqual(list_leave_requests("sophie")[0]["status"], STATUS_CANCELLED)

    def test_the_hr_list_has_every_employee_with_their_email(self):
        save_leave_request("sophie", NOVEMBER)
        save_leave_request("paul", {**NOVEMBER, "start_date": "2026-12-21", "end_date": "2026-12-24"})
        rows = list_all_leave_requests()
        self.assertEqual([(r["user_id"], r["email"]) for r in rows],
                         [("paul", "paul@example.com"), ("sophie", "sophie@example.com")])  # latest leave first

    def test_requests_made_before_statuses_existed_are_pending(self):
        path = os.path.join(self.tmp.name, "old.db")
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE leave_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, "
                     "leave_type TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL, "
                     "reason TEXT NOT NULL DEFAULT '', created_at TEXT)")
        conn.execute("INSERT INTO leave_requests (user_id, leave_type, start_date, end_date) "
                     "VALUES ('old', 'sick_leave', '2026-01-05', '2026-01-06')")
        conn.commit(); conn.close()
        self.assertEqual(list_leave_requests("old", db_path=path)[0]["status"], STATUS_PENDING)


class TestCancellation(LeaveTest):
    def test_the_plan_shows_the_request_found_and_confirm_cancels_it(self):
        request_id = save_leave_request("sophie", NOVEMBER)
        pending = prepare_cancellation(self.session(), "2026-11-03")
        self.assertIsInstance(pending, PendingAction)
        self.assertIn(f"#{request_id}", pending.plan)
        self.assertIn("2026-11-07", pending.plan)
        self.assertEqual(list_leave_requests("sophie")[0]["status"], STATUS_PENDING)  # nothing done yet
        self.assertIn("cancelled", pending.execute())
        self.assertEqual(list_leave_requests("sophie")[0]["status"], STATUS_CANCELLED)
        self.assertIn("not pending any more", pending.execute())

    def test_a_colleagues_request_is_never_found(self):
        save_leave_request("paul", NOVEMBER)
        with self.assertRaises(ValueError):
            prepare_cancellation(self.session("sophie"), "2026-11-03")
        self.assertEqual(list_leave_requests("paul")[0]["status"], STATUS_PENDING)

    def test_no_request_that_day_or_a_bad_date_goes_back_to_the_model(self):
        save_leave_request("sophie", NOVEMBER)
        for day in ("2026-11-04", "3 novembre"):
            with self.assertRaises(ValueError):
                prepare_cancellation(self.session(), day)

    def test_the_tool_is_critical_and_only_prepares(self):
        save_leave_request("sophie", NOVEMBER)
        registry = build_registry(self.session())
        self.assertTrue(registry.is_critical("cancel_leave_request"))
        text, ok = registry.run("cancel_leave_request", {"start_date": "2026-11-03"})
        self.assertFalse(ok)  # never run directly
        pending, problem = registry.propose("cancel_leave_request", {"start_date": "2026-11-03"})
        self.assertIsInstance(pending, PendingAction)
        self.assertEqual(list_leave_requests("sophie")[0]["status"], STATUS_PENDING)

    def test_cancelling_requests_are_detected_but_not_questions(self):
        for text in ("Annule mon congé du 3 novembre", "annuler ma demande de RTT de lundi",
                     "Cancel my leave on Monday", "supprime mes vacances de décembre"):
            self.assertTrue(asks_for_leave(text), text)
        for text in ("Comment annuler un congé ?", "Est-ce que je peux annuler mes vacances ?",
                     "annule ça", "Peut-on supprimer une absence déjà validée ?"):
            self.assertFalse(asks_for_leave(text), text)


class TestToolSpec(unittest.TestCase):
    def test_leave_types_are_a_closed_list_with_a_meaning_each(self):
        import json
        from Agents.Setup import DEFAULT_TOOLS_PATH
        tools = {t["function"]["name"]: t["function"] for t in json.load(open(DEFAULT_TOOLS_PATH, encoding="utf-8"))}
        leave_type = tools["file_leave_request"]["parameters"]["properties"]["leave_type"]
        self.assertEqual(leave_type["enum"], list(LEAVE_TYPES))
        for code in LEAVE_TYPES:
            self.assertIn(f"{code} = ", leave_type["description"])
        self.assertIn("bereavement = décès d'un proche, deuil", leave_type["description"])
        self.assertTrue(tools["cancel_leave_request"]["critical"])


class TestHrDecision(LeaveTest):
    def test_hr_approves_or_refuses_and_who_decided_is_kept(self):
        request_id = save_leave_request("sophie", NOVEMBER)
        saved = decide_leave_request(request_id, STATUS_APPROVED, "marc")
        self.assertEqual((saved["status"], saved["decided_by"]), (STATUS_APPROVED, "marc"))
        self.assertIsNotNone(saved["decided_at"])
        self.assertEqual(list_leave_requests("sophie")[0]["status"], STATUS_APPROVED)  # the employee sees it
        self.assertEqual(decide_leave_request(request_id, STATUS_REFUSED, "marc")["status"], STATUS_REFUSED)

    def test_back_to_pending_forgets_the_decision(self):
        request_id = save_leave_request("sophie", NOVEMBER)
        decide_leave_request(request_id, STATUS_APPROVED, "marc")
        saved = decide_leave_request(request_id, STATUS_PENDING, "marc")
        self.assertEqual((saved["status"], saved["decided_by"], saved["decided_at"]), (STATUS_PENDING, None, None))

    def test_a_cancelled_or_unknown_request_or_a_bad_status_is_refused(self):
        request_id = save_leave_request("sophie", NOVEMBER)
        with self.assertRaises(ValueError):
            decide_leave_request(request_id, "maybe", "marc")
        with self.assertRaises(LookupError):
            decide_leave_request(999, STATUS_APPROVED, "marc")
        cancel_leave_request("sophie", request_id)
        with self.assertRaises(PermissionError):
            decide_leave_request(request_id, STATUS_APPROVED, "marc")
        self.assertEqual(list_leave_requests("sophie")[0]["status"], STATUS_CANCELLED)

    def test_an_approved_request_cannot_be_cancelled_by_the_agent(self):
        request_id = save_leave_request("sophie", NOVEMBER)
        decide_leave_request(request_id, STATUS_APPROVED, "marc")
        with self.assertRaises(ValueError):
            prepare_cancellation(self.session(), "2026-11-03")  # only pending requests are found

    def test_the_cli_commands_are_for_hr_only(self):
        request_id = save_leave_request("sophie", NOVEMBER)
        self.assertIn("only HR accounts", self.command(self.session("sophie"), f"/leaves approve {request_id}"))
        self.assertEqual(list_leave_requests("sophie")[0]["status"], STATUS_PENDING)
        out = self.command(self.session("marc", ROLE_HR), f"/leaves approve #{request_id}")
        self.assertIn(f"#{request_id} of sophie is now approved", out)
        self.assertIn("Usage", self.command(self.session("marc", ROLE_HR), "/leaves refuse"))
        self.assertIn("Error", self.command(self.session("marc", ROLE_HR), "/leaves refuse 999"))


class TestHrCommand(LeaveTest):
    def test_hr_sees_every_employee_and_the_status(self):
        save_leave_request("sophie", NOVEMBER)
        cancel_leave_request("paul", save_leave_request("paul", NOVEMBER))
        out = self.command(self.session("marc", ROLE_HR), "/leaves all")
        self.assertIn("sophie  2026-11-03 -> 2026-11-07  paid_leave  [pending]", out)
        self.assertIn("paul", out)
        self.assertIn("[cancelled]", out)

    def test_an_employee_sees_only_their_own(self):
        save_leave_request("sophie", NOVEMBER)
        save_leave_request("paul", NOVEMBER)
        out = self.command(self.session("sophie"), "/leaves all")
        self.assertIn("only HR accounts", out)
        self.assertNotIn("paul", out)
        own = self.command(self.session("sophie"), "/leaves")
        self.assertIn("[pending]", own)
        self.assertNotIn("paul", own)


if __name__ == "__main__":
    unittest.main()
