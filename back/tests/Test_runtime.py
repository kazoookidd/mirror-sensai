"""
Tests for [A5] Personas and runtime model switching.

No real Ollama is needed: a tiny local HTTP server plays the part of
Ollama's GET /api/tags endpoint.

Usage (from the project root):
    python back/tests/Test_runtime.py
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

# back/tests/Test_runtime.py -> one level up is back/, same as Chatbot.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Runtime.Models import list_models, resolve_model, looks_like_embedding_model
from Runtime.Parameters import (
    describe_option,
    describe_temperature,
    generation_options,
    parse_num_predict,
    parse_seed,
    parse_temperature,
)
from Runtime.Personas import DEFAULT_PERSONA_ID, load_personas, resolve_persona
from Agents.Leave import prepare_leave_request
from Commands import Session, handle_command

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
                        "/confirm", "/cancel", "/leaves", "/temperature"):
            self.assertIn(command, output)


class TestTemperature(RuntimeTestCase):
    """Generation parameter: temperature."""

    def test_parse_accepts_numbers_and_a_decimal_comma(self):
        self.assertEqual(parse_temperature("0.7"), (0.7, None))
        self.assertEqual(parse_temperature("0,7"), (0.7, None))
        self.assertEqual(parse_temperature(" 0 "), (0.0, None))
        self.assertEqual(parse_temperature("2"), (2.0, None))

    def test_parse_default_words_and_unset_mean_the_model_default(self):
        for value in (None, "", "  ", "default", "AUTO", "reset"):
            self.assertEqual(parse_temperature(value), (None, None), value)

    def test_parse_rejects_invalid_values_without_clamping(self):
        for value in ("abc", "-0.1", "2.1", "nan", "inf", "1.2.3"):
            temperature, error = parse_temperature(value)
            self.assertIsNone(temperature, value)
            self.assertIn(value, error)

    def test_describe(self):
        self.assertEqual(describe_temperature(None), "model default")
        self.assertIn("deterministic", describe_temperature(0.0))
        self.assertEqual(describe_temperature(0.7), "0.7")

    def test_session_starts_on_the_model_default(self):
        self.assertIsNone(self.make_session().temperature)

    def test_command_sets_the_temperature(self):
        session = self.make_session()
        handled, output = self.run_command(session, "/temperature 0.3")
        self.assertTrue(handled)
        self.assertEqual(session.temperature, 0.3)
        self.assertIn("0.3", output)

    def test_command_without_argument_shows_the_current_value(self):
        session = self.make_session(temperature=1.2)
        _, output = self.run_command(session, "/temperature")
        self.assertIn("1.2", output)
        self.assertEqual(session.temperature, 1.2)

    def test_command_default_resets(self):
        session = self.make_session(temperature=1.2)
        self.run_command(session, "/temperature default")
        self.assertIsNone(session.temperature)

    def test_invalid_value_leaves_the_temperature_unchanged(self):
        session = self.make_session(temperature=0.5)
        for bad in ("hot", "5", "-1"):
            _, output = self.run_command(session, f"/temperature {bad}")
            self.assertIn("Error", output)
            self.assertIn("unchanged", output)
            self.assertEqual(session.temperature, 0.5)

    def test_temperature_does_not_touch_the_conversation_or_model(self):
        session = self.make_session()
        self.run_command(session, "/temperature 0.9")
        self.assertEqual((session.conversation_id, session.model), (1, "llama3:latest"))


class TestModelOptions(unittest.TestCase):
    """seed / num_predict: parsing and what is sent to Ollama."""

    PARSERS = {"seed": parse_seed, "num-predict": parse_num_predict}

    def test_whole_numbers_are_accepted(self):
        self.assertEqual(parse_seed("42"), (42, None))
        self.assertEqual(parse_seed(" 0 "), (0, None))
        self.assertEqual(parse_num_predict("300"), (300, None))

    def test_default_words_and_unset_mean_the_model_default(self):
        for name, parse in self.PARSERS.items():
            for value in (None, "", "  ", "default", "AUTO", "reset"):
                self.assertEqual(parse(value), (None, None), f"{name} {value!r}")

    def test_invalid_values_are_refused_and_never_clamped(self):
        bad = {
            "seed": ("abc", "-1", "2.5", "99999999999", "nan", "4,2"),
            "num-predict": ("abc", "0", "-5", "2.5", "99999999", "inf"),
        }
        for name, values in bad.items():
            for value in values:
                number, error = self.PARSERS[name](value)
                self.assertIsNone(number, f"{name} {value}")
                self.assertIn(value, error, f"{name} {value}")

    def test_bounds_are_inclusive(self):
        self.assertEqual(parse_num_predict("1"), (1, None))
        self.assertEqual(parse_seed(str(2**31 - 1)), (2**31 - 1, None))

    def test_only_the_options_that_are_set_are_sent_and_zero_counts_as_set(self):
        self.assertEqual(generation_options(), {})
        self.assertEqual(generation_options(seed=0), {"seed": 0})
        self.assertEqual(generation_options(42, 300), {"seed": 42, "num_predict": 300})

    def test_describe(self):
        self.assertEqual(describe_option(None), "model default")
        self.assertEqual(describe_option(0), "0")
        self.assertEqual(describe_option(300), "300")

    def test_a_session_starts_on_the_model_defaults(self):
        session = Session(user_id="a", conversation_id=1, model="m", persona_id="p",
                          personas={}, ollama_url="http://x", search_motor="none")
        self.assertEqual(session.model_options(), {})


class TestSettings(RuntimeTestCase):
    """/settings: change the assistant's settings while it runs."""

    def test_lists_every_setting_with_its_current_value(self):
        session = self.make_session(temperature=0.4, token_limit_action="continue",
                                    show_token_usage=False, seed=42)
        handled, output = self.run_command(session, "/settings")
        self.assertTrue(handled)
        for name in ("temperature", "token-limit", "token-usage", "seed", "num-predict",
                     "guardrails", "guardrails-output"):
            self.assertIn(name, output)
        for value in ("0.4", "continue", "off", "42", "model default"):
            self.assertIn(value, output)

    def test_set_is_an_alias(self):
        session = self.make_session()
        self.run_command(session, "/set temperature 0.2")
        self.assertEqual(session.temperature, 0.2)

    def test_changes_temperature_like_the_dedicated_command(self):
        session = self.make_session()
        self.run_command(session, "/settings temperature 0,7")
        self.assertEqual(session.temperature, 0.7)
        self.run_command(session, "/settings temperature default")
        self.assertIsNone(session.temperature)

    def test_changes_token_limit_action(self):
        session = self.make_session()
        self.assertEqual(session.token_limit_action, "block")
        self.run_command(session, "/settings token-limit continue")
        self.assertEqual(session.token_limit_action, "continue")
        self.run_command(session, "/settings token-limit block")
        self.assertEqual(session.token_limit_action, "block")

    def test_only_hr_accounts_change_the_guardrails(self):
        session = self.make_session()  # an employee account
        _, out = self.run_command(session, "/settings guardrails off")
        self.assertTrue(session.guardrails)
        self.assertIn("only HR accounts can change this setting", out)
        self.run_command(session, "/settings guardrails-output refuse")
        self.assertEqual(session.guardrails_output, "redact")

    def test_changes_guardrails(self):
        session = self.make_session(account_role="hr")
        self.assertTrue(session.guardrails)
        self.assertEqual(session.guardrails_output, "redact")
        self.run_command(session, "/settings guardrails off")
        self.assertFalse(session.guardrails)
        self.run_command(session, "/settings guardrails-output refuse")
        self.assertEqual(session.guardrails_output, "refuse")
        self.run_command(session, "/settings guardrails on")
        self.run_command(session, "/settings guardrails-output redact")
        self.assertTrue(session.guardrails)
        self.assertEqual(session.guardrails_output, "redact")

    def test_changes_token_usage_display(self):
        session = self.make_session()
        for text, expected in (("off", False), ("on", True), ("false", False), ("YES", True)):
            self.run_command(session, f"/settings token-usage {text}")
            self.assertIs(session.show_token_usage, expected, text)

    def test_names_are_case_and_underscore_insensitive_and_have_aliases(self):
        session = self.make_session()
        self.run_command(session, "/settings TOKEN_LIMIT continue")
        self.assertEqual(session.token_limit_action, "continue")
        self.run_command(session, "/settings show_token_usage off")
        self.assertFalse(session.show_token_usage)
        self.run_command(session, "/settings temp 1")
        self.assertEqual(session.temperature, 1.0)
        self.run_command(session, "/settings NUM_PREDICT 200")
        self.assertEqual(session.num_predict, 200)
        self.run_command(session, "/settings max-tokens 150")
        self.assertEqual(session.num_predict, 150)

    def test_name_alone_shows_the_value_and_what_it_accepts(self):
        session = self.make_session(token_limit_action="continue")
        _, output = self.run_command(session, "/settings token-limit")
        self.assertIn("continue", output)
        self.assertIn("block", output)  # accepted values are listed
        self.assertEqual(session.token_limit_action, "continue")

    def test_invalid_values_are_refused_and_nothing_changes(self):
        session = self.make_session(temperature=0.5, token_limit_action="continue",
                                    show_token_usage=True)
        for command in ("/settings temperature hot", "/settings temperature 9",
                        "/settings token-limit maybe", "/settings token-usage perhaps"):
            _, output = self.run_command(session, command)
            self.assertIn("Error", output, command)
            self.assertIn("unchanged", output, command)
        self.assertEqual(session.temperature, 0.5)
        self.assertEqual(session.token_limit_action, "continue")
        self.assertTrue(session.show_token_usage)

    def test_unknown_setting_lists_the_available_ones(self):
        session = self.make_session()
        handled, output = self.run_command(session, "/settings colour blue")
        self.assertTrue(handled)
        self.assertIn("unknown setting 'colour'", output)
        self.assertIn("temperature", output)
        self.assertIn("seed", output)
        self.assertIn("num-predict", output)

    def test_sets_the_seed_and_zero_is_a_real_value(self):
        session = self.make_session()
        _, output = self.run_command(session, "/settings seed 42")
        self.assertEqual(session.seed, 42)
        self.assertIn("seed set to 42", output)
        self.run_command(session, "/settings seed 0")
        self.assertEqual(session.seed, 0)
        self.assertEqual(session.model_options(), {"seed": 0})

    def test_sets_num_predict(self):
        session = self.make_session()
        _, output = self.run_command(session, "/settings num-predict 300")
        self.assertEqual(session.num_predict, 300)
        self.assertIn("num-predict set to 300", output)
        self.assertEqual(session.model_options(), {"num_predict": 300})

    def test_options_can_go_back_to_the_model_default(self):
        session = self.make_session(seed=1, num_predict=2)
        for name in ("seed", "num-predict"):
            self.run_command(session, f"/settings {name} default")
        self.assertEqual(session.model_options(), {})

    def test_invalid_seed_and_num_predict_are_refused_and_nothing_changes(self):
        session = self.make_session(temperature=0.5, seed=1, num_predict=200)
        for command in ("/settings seed -3", "/settings seed 1.5", "/settings seed lucky",
                        "/settings num-predict 0", "/settings num-predict 99999999",
                        "/settings num-predict big",
                        "/settings temperature hot", "/settings token-limit maybe"):
            _, output = self.run_command(session, command)
            self.assertIn("Error", output, command)
            self.assertIn("unchanged", output, command)
        self.assertEqual((session.temperature, session.seed, session.num_predict),
                         (0.5, 1, 200))

    def test_name_alone_shows_the_num_predict_value_and_its_range(self):
        session = self.make_session(num_predict=300)
        _, output = self.run_command(session, "/settings num-predict")
        self.assertIn("300", output)
        self.assertIn("1 to 32768", output)
        self.assertEqual(session.num_predict, 300)

    def test_changing_a_setting_keeps_the_rest_of_the_session(self):
        session = self.make_session()

    def test_changing_a_setting_keeps_the_rest_of_the_session(self):
        session = self.make_session()
        self.run_command(session, "/settings token-limit continue")
        self.run_command(session, "/settings seed 5")
        self.assertEqual((session.conversation_id, session.model, session.persona_id),
                         (1, "llama3:latest", DEFAULT_PERSONA_ID))

    def test_help_mentions_settings(self):
        _, output = self.run_command(self.make_session(), "/help")
        self.assertIn("/settings", output)


VALID_LEAVE = {
    "leave_type": "paid_leave",
    "start_date": "2026-11-03",
    "end_date": "2026-11-07",
    "reason": "vacances",
}

SAVE = "Agents.Leave.save_leave_request"


class TestConfirmCommand(RuntimeTestCase):
    """[A3] /confirm and /cancel, once the agent has prepared an action."""

    def pend(self, session, data=VALID_LEAVE):
        """Put a prepared leave request on the session, as the agent would."""
        session.pending_action = prepare_leave_request(session, **data)
        return session

    def test_confirm_saves_the_pending_request_for_the_session_user(self):
        session = self.pend(self.make_session())
        with mock.patch(SAVE, return_value=7) as save:
            handled, output = self.run_command(session, "/confirm")
        self.assertTrue(handled)
        save.assert_called_once_with("alice", VALID_LEAVE)
        self.assertIsNone(session.pending_action)
        self.assertIn("#7", output)

    def test_confirm_twice_saves_only_once(self):
        session = self.pend(self.make_session())
        with mock.patch(SAVE, return_value=7) as save:
            self.run_command(session, "/confirm")
            _, output = self.run_command(session, "/confirm")
        save.assert_called_once()
        self.assertIn("No action is waiting", output)

    def test_cancel_drops_the_pending_request_without_saving(self):
        session = self.pend(self.make_session())
        with mock.patch(SAVE) as save:
            _, output = self.run_command(session, "/cancel")
        save.assert_not_called()
        self.assertIsNone(session.pending_action)
        self.assertIn("Nothing was done", output)

    def test_confirm_and_cancel_with_nothing_pending(self):
        session = self.make_session()
        with mock.patch(SAVE) as save:
            _, confirmed = self.run_command(session, "/confirm")
            _, cancelled = self.run_command(session, "/cancel")
        save.assert_not_called()
        self.assertIn("No action is waiting", confirmed)
        self.assertIn("No action is waiting", cancelled)

    def test_a_new_pending_action_replaces_the_previous_one(self):
        other = dict(VALID_LEAVE, start_date="2026-12-01", end_date="2026-12-02")
        session = self.pend(self.make_session())
        self.pend(session, other)
        with mock.patch(SAVE, return_value=2) as save:
            self.run_command(session, "/confirm")
        save.assert_called_once_with("alice", other)

    def test_pending_actions_belong_to_their_own_session(self):
        alice = self.pend(self.make_session())
        bob = self.make_session(user_id="bob")
        with mock.patch(SAVE) as save:
            _, output = self.run_command(bob, "/confirm")
        save.assert_not_called()
        self.assertIn("No action is waiting", output)
        self.assertIsNotNone(alice.pending_action)

    def test_aliases_of_confirm_and_cancel(self):
        session = self.pend(self.make_session())
        with mock.patch(SAVE, return_value=1) as save:
            self.run_command(session, "/confirmer")
            save.assert_called_once()
            self.pend(session)
            _, output = self.run_command(session, "/annuler")
        self.assertIsNone(session.pending_action)
        self.assertIn("Nothing was done", output)

    def test_leave_is_no_longer_a_command(self):
        handled, output = self.run_command(self.make_session(), "/leave demain")
        self.assertTrue(handled)
        self.assertIn("Unknown command", output)

    def test_confirm_database_error_is_reported_and_keeps_the_action(self):
        session = self.pend(self.make_session())
        waiting = session.pending_action
        with mock.patch(SAVE, side_effect=sqlite3.IntegrityError("fk")):
            _, output = self.run_command(session, "/confirm")
        self.assertIn("failed", output)
        self.assertIs(session.pending_action, waiting)

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