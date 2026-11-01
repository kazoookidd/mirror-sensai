"""
Tests for questions and forms [X4] (Agents/Forms.py): the ask_user tool, the leave request
that becomes a form when something is missing, answering in the chat or in the terminal,
and POST /api/form. No real model; the database is a temporary file.

Usage (from the project root):
    python back/tests/Test_forms.py
"""

import io
import os
import queue
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import HTTPException

from Agents.Confirmation import PendingAction
from Agents.Forms import FormError, PendingForm, model_form, question_form
from Agents.Leave import prepare_leave_request
from Agents.ReAct import ModelReply, ReActAgent
from Agents.Setup import build_registry
from Commands import Session, answer_question, fill_form_in_terminal, handle_command
from Memories import Database
from Memories.Auth import ROLE_EMPLOYEE, create_user
from Memories.Conversations import create_conversation
from Memories.Leaves import list_leave_requests
from Memories.Memory import load_history, save_message
from Web.Output import SseOutput, pending_confirmation
from Web.Routes import Command as CommandRoute
from Web.Routes.Forms import FormValues, submit_form
from Web.Sessions import WebSession

COMPLETE = {"leave_type": "bereavement", "start_date": "2026-11-03", "end_date": "2026-11-06", "reason": "deuil"}


class FormTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch = mock.patch.object(Database, "DB_PATH", os.path.join(tmp.name, "t.db"))
        patch.start(); self.addCleanup(patch.stop)
        Database.init_db()
        create_user("sophie", "sophie@example.com", "pw", role=ROLE_EMPLOYEE)
        self.conversation = create_conversation("sophie", "t")
        self.session = Session(user_id="sophie", conversation_id=self.conversation, model="m", persona_id="default",
                               personas={}, ollama_url="x", search_motor="tavily", account_role=ROLE_EMPLOYEE)

    def wait_on(self, pending):
        """What the engine does when the agent suspends on a form."""
        pending.conversation_id = self.conversation
        self.session.pending_action = pending
        save_message(self.conversation, "user", "je veux poser un congé")
        save_message(self.conversation, "assistant", pending.render())
        return pending

    def command(self, text) -> str:
        buf = io.StringIO()
        with redirect_stdout(buf):
            handle_command(self.session, text)
        return buf.getvalue()


class TestQuestion(unittest.TestCase):
    def test_options_are_tidied_and_limited(self):
        form = question_form("  Quel type  de congé ? ", ["Congés payés", "congés payés ", "Congés payés", "RTT", "", *"abcdefg"])
        self.assertEqual(form.plan, "Quel type de congé ?")
        self.assertEqual([label for _, label in form.fields[0].options], ["Congés payés", "congés payés", "RTT", "a", "b", "c"])
        self.assertTrue(form.is_question)
        with self.assertRaises(ValueError):
            question_form("   ")

    def test_a_number_picks_a_choice_and_free_text_is_accepted(self):
        form = question_form("Quel type ?", ["Congés payés", "RTT"])
        self.assertEqual(form.submit({"answer": "2"}), "RTT")
        self.assertEqual(form.submit({"answer": "Un congé sans solde"}), "Un congé sans solde")
        with self.assertRaises(FormError):
            form.submit({"answer": "  "})

    def test_it_is_shown_with_numbered_choices(self):
        text = question_form("Quel type ?", ["Congés payés", "RTT"]).render()
        self.assertIn("1. Congés payés", text)
        self.assertIn("Answer with a number", text)


ADDRESS = [{"label": "Nouvelle adresse", "kind": "text"},
           {"label": "Date du déménagement", "kind": "date"},
           {"label": "Justificatif", "kind": "choice", "options": ["Facture", "Bail", "Facture"], "required": False}]


class TestModelForm(unittest.TestCase):
    def test_a_good_description_becomes_a_form_that_only_collects_answers(self):
        form = model_form("Changement d'adresse", ADDRESS)
        self.assertEqual(form.kind, "answers")
        self.assertTrue(form.is_question)  # nothing is done: the answers go back to the chat
        fields = form.as_dict()["fields"]
        self.assertEqual([f["kind"] for f in fields], ["text", "date", "choice"])
        self.assertEqual([o["value"] for o in fields[2]["options"]], ["Facture", "Bail"])
        self.assertFalse(fields[2]["required"])

    def test_the_answers_are_one_message(self):
        form = model_form("Changement d'adresse", ADDRESS)
        answers = form.submit({"field_1": "12 rue des Lilas", "field_2": "2026-12-01", "field_3": ""})
        self.assertEqual(answers, "Nouvelle adresse: 12 rue des Lilas\nDate du déménagement: 2026-12-01\n"
                                  "Justificatif: (no answer)")
        with self.assertRaises(FormError) as wrong:
            form.submit({"field_1": "", "field_2": "demain", "field_3": "Passeport"})
        self.assertEqual(set(wrong.exception.errors), {"field_1", "field_2", "field_3"})

    def test_aliases_of_small_models_are_accepted(self):
        form = model_form("RDV", [{"name": "Motif", "type": "select", "options": ["Paie", "Contrat"]}])
        self.assertEqual(form.fields[0].kind, "choice")

    def test_a_bad_description_is_refused_with_a_reason(self):
        cases = [("", ADDRESS, "title"), ("T", [], "1 to 5"), ("T", ADDRESS * 2, "1 to 5"), ("T", "texte", "1 to 5"),
                 ("T", ["Adresse"], "object"), ("T", [{"kind": "text"}], "label"),
                 ("T", [{"label": "A"}, {"label": "a"}], "own label"), ("T", [{"label": "A", "kind": "file"}], "kind"),
                 ("T", [{"label": "A", "kind": "choice", "options": ["seul"]}], "2 to 6"),
                 ("T", [{"label": "A", "kind": "choice"}], "2 to 6")]
        for title, fields, reason in cases:
            with self.assertRaises(ValueError, msg=fields) as refused:
                model_form(title, fields)
            self.assertIn(reason, str(refused.exception))


class TestLeaveForm(FormTest):
    def test_a_complete_request_is_still_a_plan_to_confirm(self):
        pending = prepare_leave_request(self.session, **COMPLETE)
        self.assertIsInstance(pending, PendingAction)
        self.assertNotIsInstance(pending, PendingForm)

    def test_missing_or_wrong_fields_give_a_prefilled_form(self):
        form = prepare_leave_request(self.session, "vacances", "2026-11-03", "", "deuil")
        self.assertIsInstance(form, PendingForm)
        fields = {f["name"]: f for f in form.as_dict()["fields"]}
        self.assertEqual(fields["leave_type"]["value"], "")
        self.assertIn("vacances", fields["leave_type"]["error"])
        self.assertEqual(fields["start_date"]["value"], "2026-11-03")
        self.assertEqual(fields["end_date"]["error"], "required")
        self.assertEqual(fields["reason"]["value"], "deuil")
        self.assertIn("bereavement", [o["value"] for o in fields["leave_type"]["options"]])
        self.assertEqual(form.as_dict()["kind"], "action")

    def test_submitting_files_the_request_with_the_values_checked_again(self):
        form = prepare_leave_request(self.session, start_date="2026-11-03")
        with self.assertRaises(FormError) as wrong:
            form.submit({**COMPLETE, "end_date": "2026-11-01"})
        self.assertIn("end_date", wrong.exception.errors)
        with self.assertRaises(FormError):
            form.submit({**COMPLETE, "leave_type": "holiday"})
        self.assertEqual(list_leave_requests("sophie"), [])
        result = form.submit(COMPLETE)
        self.assertIn("saved for sophie", result)
        saved = list_leave_requests("sophie")[0]
        self.assertEqual((saved["leave_type"], saved["start_date"], saved["reason"]), ("bereavement", "2026-11-03", "deuil"))


class TestAgent(FormTest):
    def run_agent(self, *calls):
        replies = [ModelReply("", [{"function": {"name": name, "arguments": args}}]) for name, args in calls]
        return ReActAgent(lambda messages, tools, temperature: replies.pop(0),
                          build_registry(self.session)).run("je veux poser un congé")

    def test_ask_user_suspends_the_agent_on_a_question(self):
        result = self.run_agent(("ask_user", {"question": "Quel type de congé ?", "options": ["Congés payés", "RTT"]}))
        self.assertEqual(result.status, "awaiting_confirmation")
        self.assertTrue(result.pending.is_question)
        self.assertEqual(build_registry(self.session).run("ask_user", {"question": "x"})[1], False)  # never run

    def test_a_leave_tool_call_without_dates_suspends_on_a_form(self):
        result = self.run_agent(("file_leave_request", {"leave_type": "paid_leave"}))
        self.assertEqual(result.status, "awaiting_confirmation")
        self.assertFalse(result.pending.is_question)
        self.assertEqual(list_leave_requests("sophie"), [])


class TestNoDate(FormTest):
    def test_a_leave_request_without_any_date_is_recognised(self):
        from Agents.Router import leave_type_in, wants_leave_without_dates
        for text, leave_type in (("je veux poser un congé", ""), ("Je voudrais poser un congé maladie", "sick_leave"),
                                 ("je veux poser un congé pour le décès de mon grand-père", "bereavement"),
                                 ("je veux poser 2 jours de RTT", "paid_leave")):
            self.assertTrue(wants_leave_without_dates(text), text)
            self.assertEqual(leave_type_in(text), leave_type, text)
        for text in ("Je pose du 3 au 7 novembre", "je pose lundi", "Annule mon congé", "Comment poser un congé ?"):
            self.assertFalse(wants_leave_without_dates(text), text)

    def test_it_opens_the_form_without_calling_the_model(self):
        from Agents.Engine import generate_reply
        self.session.tools = build_registry(self.session)
        self.session.ollama_url = "http://127.0.0.1:9"  # nothing listens: a model call would fail
        events = queue.Queue()
        self.session.out = SseOutput(events)
        reply = generate_reply(self.session, [{"role": "user", "content": "x"}], "Je voudrais poser un congé maladie")
        self.assertTrue(reply.used_tools)
        self.assertIsInstance(self.session.pending_action, PendingForm)
        fields = {f["name"]: f["value"] for f in self.session.pending_action.as_dict()["fields"]}
        self.assertEqual(fields["leave_type"], "sick_leave")
        names = [events.get()[0] for _ in range(events.qsize())]
        self.assertIn("confirmation", names)
        self.assertNotIn("error", names)


class TestAskFormSetting(FormTest):
    def test_ask_form_is_off_unless_turned_on(self):
        self.assertNotIn("ask_form", build_registry(self.session).names())
        with mock.patch.dict(os.environ, {"AGENT_ASK_FORM": "true"}):
            registry = build_registry(self.session)
        self.assertIn("ask_form", registry.names())
        self.assertTrue(registry.is_critical("ask_form"))  # it suspends the agent, it never runs
        pending, problem = registry.propose("ask_form", {"title": "Adresse", "fields": ADDRESS})
        self.assertEqual((problem, pending.kind), ("", "answers"))
        refused, problem = registry.propose("ask_form", {"title": "Adresse", "fields": []})
        self.assertIsNone(refused)
        self.assertIn("1 to 5", problem)  # back to the model, like any bad tool call


class TestAnswering(FormTest):
    def test_answering_settles_the_question_in_the_chat(self):
        self.wait_on(question_form("Quel type de congé ?", ["Congés payés", "RTT"]))
        self.assertEqual(answer_question(self.session, "2"), ("RTT", True))
        self.assertIsNone(self.session.pending_action)
        self.assertTrue(load_history(self.conversation)[-1]["content"].endswith("Answer: RTT"))

    def test_a_message_in_another_chat_is_not_an_answer(self):
        self.wait_on(question_form("Quel type ?", ["Congés payés", "RTT"]))
        self.session.conversation_id = create_conversation("sophie", "other")
        self.assertEqual(answer_question(self.session, "2"), ("2", False))
        self.assertIsNotNone(self.session.pending_action)

    def test_confirm_does_not_fill_a_form_and_cancel_drops_it(self):
        self.wait_on(prepare_leave_request(self.session, start_date="2026-11-03"))
        self.assertIn("A form is waiting", self.command("/confirm"))
        self.assertIn("Dropped", self.command("/cancel"))
        self.assertIsNone(self.session.pending_action)
        self.assertEqual(list_leave_requests("sophie"), [])

    def test_the_terminal_asks_field_by_field_and_files_the_request(self):
        self.wait_on(prepare_leave_request(self.session, leave_type="bereavement", start_date="2026-11-03"))
        typed = iter(["", "", "2026-11-01", "deuil", "2026-11-06"])  # end before start, then corrected
        with mock.patch("builtins.input", lambda prompt="": next(typed)), redirect_stdout(io.StringIO()) as out:
            fill_form_in_terminal(self.session)
        self.assertIn("To correct: end_date", out.getvalue())
        saved = list_leave_requests("sophie")[0]
        self.assertEqual((saved["leave_type"], saved["end_date"]), ("bereavement", "2026-11-06"))
        self.assertIsNone(self.session.pending_action)
        self.assertIn("saved for sophie", load_history(self.conversation)[-1]["content"])

    def test_a_form_of_the_model_answered_in_words_takes_the_message(self):
        self.wait_on(model_form("Adresse", ADDRESS))
        self.assertEqual(answer_question(self.session, "  12 rue des Lilas, le 1er décembre "),
                         ("12 rue des Lilas, le 1er décembre", True))
        self.assertIsNone(self.session.pending_action)

    def test_the_terminal_returns_the_answers_of_a_form_of_the_model(self):
        self.wait_on(model_form("Adresse", ADDRESS))
        typed = iter(["12 rue des Lilas", "2026-12-01", "2"])
        with mock.patch("builtins.input", lambda prompt="": next(typed)), redirect_stdout(io.StringIO()):
            answers = fill_form_in_terminal(self.session)
        self.assertIn("Justificatif: Bail", answers)
        self.assertIsNone(self.session.pending_action)
        self.assertIn("Answers:", load_history(self.conversation)[-1]["content"])

    def test_the_terminal_form_can_be_cancelled(self):
        self.wait_on(prepare_leave_request(self.session, leave_type="bereavement"))
        with mock.patch("builtins.input", lambda prompt="": "/cancel"), redirect_stdout(io.StringIO()):
            fill_form_in_terminal(self.session)
        self.assertIsNone(self.session.pending_action)
        self.assertEqual(list_leave_requests("sophie"), [])


class TestWeb(FormTest):
    def submit(self, values, conversation_id=None):
        return submit_form(FormValues(conversation_id=conversation_id or self.conversation, values=values),
                           WebSession(self.session))

    def test_the_card_carries_the_form_live_and_after_a_reload(self):
        form = self.wait_on(prepare_leave_request(self.session, start_date="2026-11-03"))
        events = queue.Queue()
        SseOutput(events).confirmation(form.title, form.plan, form.as_dict())
        name, data = events.get()
        self.assertEqual((name, data["form"]["kind"]), ("confirmation", "action"))
        self.assertEqual(pending_confirmation(self.session, self.conversation)["form"]["submit_label"], "File the request")

    def test_submitting_files_the_request_or_returns_the_errors(self):
        self.wait_on(prepare_leave_request(self.session, start_date="2026-11-03"))
        refused = self.submit({**COMPLETE, "leave_type": ""})
        self.assertEqual((refused["ok"], refused["errors"]), (False, {"leave_type": "required"}))
        self.assertIsNotNone(self.session.pending_action)  # still waiting
        done = self.submit(COMPLETE)
        self.assertTrue(done["ok"])
        self.assertEqual(len(list_leave_requests("sophie")), 1)
        self.assertIsNone(self.session.pending_action)
        self.assertIn("Leave request #", load_history(self.conversation)[-1]["content"])

    def test_only_the_form_of_this_chat_and_not_a_question(self):
        self.wait_on(prepare_leave_request(self.session, start_date="2026-11-03"))
        with self.assertRaises(HTTPException) as other:
            self.submit(COMPLETE, conversation_id=self.conversation + 1)
        self.assertEqual(other.exception.status_code, 404)
        self.session.pending_action = None
        self.wait_on(question_form("Quel type ?", ["RTT"]))
        with self.assertRaises(HTTPException) as question:
            self.submit({"answer": "RTT"})
        self.assertEqual(question.exception.status_code, 422)
        self.assertEqual(list_leave_requests("sophie"), [])

    def test_a_form_of_the_model_returns_its_answers(self):
        self.wait_on(model_form("Adresse", ADDRESS))
        done = self.submit({"field_1": "12 rue des Lilas", "field_2": "2026-12-01", "field_3": "Facture"})
        self.assertTrue(done["ok"])
        self.assertIn("Nouvelle adresse: 12 rue des Lilas", done["answer"])
        self.assertIsNone(self.session.pending_action)

    def test_the_terminal_form_command_is_refused_in_the_browser(self):
        self.assertIn("/form", CommandRoute.INTERACTIVE)


if __name__ == "__main__":
    unittest.main()
