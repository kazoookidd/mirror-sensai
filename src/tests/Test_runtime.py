"""
Tests for [A5] Personas and runtime model switching.

No real Ollama is needed: a tiny local HTTP server plays the part of
Ollama's GET /api/tags endpoint.

Usage (from the project root):
    python src/tests/Test_runtime.py
"""

import io
import json
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

# src/tests/Test_runtime.py -> one level up is src/, same as Chatbot.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Runtime.Models import list_models, resolve_model, looks_like_embedding_model
from Runtime.Personas import DEFAULT_PERSONA_ID, load_personas, resolve_persona
from Commands import Session, handle_command
from StructuredOutput.Extractor import StructuredOutputError

INSTALLED = ["nomic-embed-text:latest", "mistral:7b", "llama3:latest"]


class FakeOllamaHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/tags":
            body = json.dumps({"models": [{"name": n} for n in INSTALLED]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass  # keep the test output clean


class RuntimeTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeOllamaHandler)
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def make_session(self, **overrides) -> Session:
        personas, _ = load_personas("does-not-exist", "default prompt")
        personas["hr"] = {"id": "hr", "name": "RH Senior", "description": "", "system_prompt": "hr prompt"}
        values = dict(
            user_id="alice", conversation_id=1, model="llama3:latest",
            persona_id=DEFAULT_PERSONA_ID, personas=personas, ollama_url=self.url,
            search_motor="tavily",
        )
        values.update(overrides)
        return Session(**values)

    def run_command(self, session: Session, text: str) -> tuple[bool, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            handled = handle_command(session, text)
        return handled, buffer.getvalue()


class TestModels(RuntimeTestCase):
    def test_list_models_is_sorted(self):
        self.assertEqual(list_models(self.url), sorted(INSTALLED))

    def test_list_models_connection_error(self):
        with self.assertRaises(RuntimeError) as ctx:
            list_models("http://127.0.0.1:1")  # nothing listens there
        self.assertIn("cannot connect", str(ctx.exception))

    def test_list_models_http_error(self):
        with self.assertRaises(RuntimeError):
            list_models(self.url + "/nope")  # fake server answers 404 here

    def test_resolve_by_exact_name_number_and_implicit_latest(self):
        installed = sorted(INSTALLED)  # [llama3:latest, mistral:7b, nomic-embed-text:latest]
        self.assertEqual(resolve_model("mistral:7b", installed), "mistral:7b")
        self.assertEqual(resolve_model("llama3", installed), "llama3:latest")
        self.assertEqual(resolve_model("2", installed), "mistral:7b")

    def test_resolve_unknown_or_out_of_range(self):
        installed = sorted(INSTALLED)
        self.assertIsNone(resolve_model("gpt-9", installed))
        self.assertIsNone(resolve_model("0", installed))
        self.assertIsNone(resolve_model("4", installed))
        self.assertIsNone(resolve_model("  ", installed))
        self.assertIsNone(resolve_model("mistral", installed))  # only mistral:7b exists

    def test_embedding_heuristic(self):
        self.assertTrue(looks_like_embedding_model("nomic-embed-text:latest"))
        self.assertFalse(looks_like_embedding_model("llama3:latest"))


class TestPersonas(unittest.TestCase):
    def write(self, directory: str, filename: str, content) -> None:
        text = content if isinstance(content, str) else json.dumps(content)
        Path(directory, filename).write_text(text, encoding="utf-8")

    def test_loads_valid_personas_and_injects_default_first(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(d, "hr_senior.json", {"name": "RH Senior", "system_prompt": "p1", "description": "desc"})
            self.write(d, "hr_onboarding.json", {"name": "Buddy", "system_prompt": "p2"})
            personas, warnings = load_personas(d, "base prompt")

        self.assertEqual(warnings, [])
        self.assertEqual(list(personas), [DEFAULT_PERSONA_ID, "hr_onboarding", "hr_senior"])
        self.assertEqual(personas[DEFAULT_PERSONA_ID]["system_prompt"], "base prompt")
        self.assertEqual(personas["hr_senior"]["description"], "desc")
        self.assertEqual(personas["hr_onboarding"]["description"], "")

    def test_invalid_files_are_skipped_with_a_warning(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(d, "broken.json", "{ not json")
            self.write(d, "no_prompt.json", {"name": "X"})
            self.write(d, "no_name.json", {"system_prompt": "p"})
            self.write(d, "not_object.json", [1, 2])
            self.write(d, "ok.json", {"name": "OK", "system_prompt": "p"})
            personas, warnings = load_personas(d, "base")

        self.assertEqual(list(personas), [DEFAULT_PERSONA_ID, "ok"])
        self.assertEqual(len(warnings), 4)

    def test_missing_directory_gives_default_only_and_a_warning(self):
        personas, warnings = load_personas("definitely-not-here", "base")
        self.assertEqual(list(personas), [DEFAULT_PERSONA_ID])
        self.assertEqual(len(warnings), 1)

    def test_default_json_overrides_the_builtin_default(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(d, "default.json", {"name": "Custom default", "system_prompt": "custom"})
            personas, _ = load_personas(d, "base")
        self.assertEqual(personas[DEFAULT_PERSONA_ID]["system_prompt"], "custom")
        self.assertEqual(list(personas), [DEFAULT_PERSONA_ID])

    def test_resolve_by_id_name_and_number(self):
        personas = {
            "default": {"name": "Sensai (default)"},
            "hr_senior": {"name": "RH Senior"},
        }
        self.assertEqual(resolve_persona("hr_senior", personas), "hr_senior")
        self.assertEqual(resolve_persona("rh senior", personas), "hr_senior")
        self.assertEqual(resolve_persona("2", personas), "hr_senior")
        self.assertIsNone(resolve_persona("3", personas))
        self.assertIsNone(resolve_persona("nobody", personas))
        self.assertIsNone(resolve_persona("", personas))


class TestCommands(RuntimeTestCase):
    def test_non_commands_are_not_handled(self):
        handled, output = self.run_command(self.make_session(), "hello there")
        self.assertFalse(handled)
        self.assertEqual(output, "")

    def test_persona_switch_changes_active_prompt_and_keeps_conversation(self):
        session = self.make_session()
        handled, output = self.run_command(session, "/persona hr")
        self.assertTrue(handled)
        self.assertEqual(session.persona_id, "hr")
        self.assertEqual(session.persona["system_prompt"], "hr prompt")
        self.assertEqual(session.conversation_id, 1)
        self.assertIn("history is kept", output)

    def test_unknown_persona_leaves_state_unchanged(self):
        session = self.make_session()
        _, output = self.run_command(session, "/persona ghost")
        self.assertEqual(session.persona_id, DEFAULT_PERSONA_ID)
        self.assertIn("unknown persona", output)

    def test_personas_lists_and_marks_active(self):
        _, output = self.run_command(self.make_session(persona_id="hr"), "/personas")
        self.assertIn("* 2. hr", output)
        self.assertIn("  1. default", output)

    def test_model_switch_by_name_and_by_number(self):
        session = self.make_session()
        self.run_command(session, "/model mistral:7b")
        self.assertEqual(session.model, "mistral:7b")

        # sorted list: 1=llama3:latest, 2=mistral:7b, 3=nomic-embed-text:latest
        self.run_command(session, "/model 1")
        self.assertEqual(session.model, "llama3:latest")

    def test_model_switch_accepts_name_without_tag(self):
        session = self.make_session(model="mistral:7b")
        self.run_command(session, "/model llama3")
        self.assertEqual(session.model, "llama3:latest")

    def test_unknown_model_leaves_state_unchanged(self):
        session = self.make_session()
        _, output = self.run_command(session, "/model gpt-9")
        self.assertEqual(session.model, "llama3:latest")
        self.assertIn("not installed", output)

    def test_model_switch_with_ollama_down_keeps_current_model(self):
        session = self.make_session(ollama_url="http://127.0.0.1:1")
        _, output = self.run_command(session, "/model mistral:7b")
        self.assertEqual(session.model, "llama3:latest")
        self.assertIn("cannot connect", output)
        self.assertIn("model unchanged", output)

    def test_models_lists_installed_and_marks_active(self):
        _, output = self.run_command(self.make_session(), "/models")
        self.assertIn("* 1. llama3:latest", output)
        self.assertIn("mistral:7b", output)
        self.assertIn("embedding model", output)

    def test_models_marks_active_model_configured_without_tag(self):
        # MODEL=llama3 in .env while Ollama lists it as llama3:latest
        _, output = self.run_command(self.make_session(model="llama3"), "/models")
        self.assertIn("* 1. llama3:latest", output)
        self.assertNotIn("not in this list", output)

    def test_models_warns_when_active_model_is_not_installed(self):
        _, output = self.run_command(self.make_session(model="ghost"), "/models")
        self.assertIn("not in this list", output)

    def test_unknown_command_is_swallowed_with_a_hint(self):
        handled, output = self.run_command(self.make_session(), "/wat")
        self.assertTrue(handled)
        self.assertIn("/help", output)

    def test_help_lists_every_runtime_command(self):
        _, output = self.run_command(self.make_session(), "/help")
        for command in ("/personas", "/persona", "/models", "/model", "/new", "/conversations",
                        "/leave", "/leaves"):
            self.assertIn(command, output)


VALID_LEAVE = {
    "leave_type": "paid_leave",
    "start_date": "2026-11-03",
    "end_date": "2026-11-07",
    "reason": "vacances",
}


class TestLeaveCommand(RuntimeTestCase):

    def test_leave_extracts_and_saves_for_the_session_user(self):
        with mock.patch("Commands.extract_leave_request", return_value=VALID_LEAVE) as extract, \
             mock.patch("Commands.save_leave_request", return_value=7) as save:
            handled, output = self.run_command(self.make_session(), "/leave Je pose du 3 au 7 novembre")
        self.assertTrue(handled)
        extract.assert_called_once_with("Je pose du 3 au 7 novembre", self.url, "llama3:latest")
        save.assert_called_once_with("alice", VALID_LEAVE)
        self.assertIn("2026-11-03", output)
        self.assertIn("#7", output)

    def test_conge_is_an_alias(self):
        with mock.patch("Commands.extract_leave_request", return_value=VALID_LEAVE), \
             mock.patch("Commands.save_leave_request", return_value=1) as save:
            self.run_command(self.make_session(), "/conge demain")
        save.assert_called_once()

    def test_leave_without_text_shows_usage_and_does_not_call_the_model(self):
        with mock.patch("Commands.extract_leave_request") as extract:
            handled, output = self.run_command(self.make_session(), "/leave")
        self.assertTrue(handled)
        self.assertIn("Usage", output)
        extract.assert_not_called()

    def test_leave_failure_prints_error_and_saves_nothing(self):
        error = StructuredOutputError("cannot connect to Ollama.")
        with mock.patch("Commands.extract_leave_request", side_effect=error), \
             mock.patch("Commands.save_leave_request") as save:
            handled, output = self.run_command(self.make_session(), "/leave demain")
        self.assertTrue(handled)
        self.assertIn("cannot connect to Ollama", output)
        self.assertIn("Nothing was saved", output)
        save.assert_not_called()

    def test_leave_database_error_is_reported(self):
        with mock.patch("Commands.extract_leave_request", return_value=VALID_LEAVE), \
             mock.patch("Commands.save_leave_request", side_effect=sqlite3.IntegrityError("fk")):
            _, output = self.run_command(self.make_session(), "/leave demain")
        self.assertIn("could not save", output)

    def test_leaves_lists_the_requests_of_the_user(self):
        rows = [{"id": 3, "leave_type": "paid_leave", "start_date": "2026-11-03",
                 "end_date": "2026-11-07", "reason": "vacances", "created_at": ""}]
        with mock.patch("Commands.list_leave_requests", return_value=rows) as listing:
            _, output = self.run_command(self.make_session(), "/leaves")
        listing.assert_called_once_with("alice")
        self.assertIn("#3", output)
        self.assertIn("vacances", output)

    def test_leaves_when_empty(self):
        with mock.patch("Commands.list_leave_requests", return_value=[]):
            _, output = self.run_command(self.make_session(), "/leaves")
        self.assertIn("none yet", output)

if __name__ == "__main__":
    unittest.main(verbosity=2)