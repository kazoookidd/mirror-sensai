"""
Tests for what leaves the machine (Tools/privacy.py and the web tools of
Agents/Setup.py), the agent's reasoning trace (A1) and the .env loading.
No network and no real Ollama.

Usage (from the project root):
    python back/tests/Test_privacy.py
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

from Agents.ReAct import ModelReply, ReActAgent, tool_guidance
from Agents.Setup import build_registry
from Agents.Tooling import Tool, ToolRegistry
from Commands import Session
from Runtime.Env import load_env
from Runtime.Output import CliOutput
from Tools.privacy import identifiers, redact
from Web.Output import SseOutput

SEARCH = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}


class TestRedact(unittest.TestCase):
    def test_personal_details_are_removed_and_named_by_kind_only(self):
        cases = {
            "congé mariage sophie.martin@acme.fr": "e-mail",
            "rappeler le 06 12 34 56 78 pour la mutuelle": "phone number",
            "mutuelle +33 6 12 34 56 78": "phone number",
            "remboursement 1 89 05 75 116 042 17": "social security number",
            "virement FR76 3000 6000 0112 3456 7890 189": "IBAN",
            "paiement 4111 1111 1111 1111": "card number",
        }
        for text, kind in cases.items():
            clean, found = redact(text)
            self.assertEqual(found, [kind], text)
            self.assertNotRegex(clean, r"\d{4}|@", text)

    def test_an_ordinary_query_is_left_as_it_is(self):
        for text in ("congé mariage durée code du travail 2026",
                     "jours fériés 2025 2026", "accord NAO 2026 augmentation 3 %",
                     "article L3142-4 code du travail"):
            self.assertEqual(redact(text), (text, []), text)

    def test_long_numbers_that_are_not_cards_are_kept(self):
        self.assertEqual(redact("dossier 1234 5678 9012 3456")[1], [])  # fails the Luhn check

    def test_the_users_own_identifiers_are_removed(self):
        known = identifiers("sophie.martin", "s.martin@acme.fr")
        clean, found = redact("congé de Sophie MARTIN pour mariage", known)
        self.assertEqual(clean, "congé de pour mariage")
        self.assertEqual(found, ["your user id"])
        self.assertEqual(redact("marchés martiniquais", known)[1], [])  # whole words only

    def test_short_ids_are_not_used(self):
        self.assertEqual(identifiers("rh"), ())


class TestWebTools(unittest.TestCase):
    def session(self):
        return Session(user_id="sophie.martin", conversation_id=1, model="m", persona_id="default",
                       personas={}, ollama_url="x", search_motor="tavily", email="s.martin@acme.fr")

    def test_the_query_is_cleaned_before_it_is_sent_and_the_model_is_told(self):
        registry = build_registry(self.session())
        with mock.patch("Tools.web_search.search_internet", return_value=[]) as engine:
            text, ok = registry.run("search_internet", {"query": "congé mariage sophie martin s.martin@acme.fr"})
        self.assertTrue(ok)
        self.assertEqual(engine.call_args.args, ("congé mariage", "tavily"))
        self.assertIn("Personal details were removed", text)
        self.assertIn("e-mail", text)

    def test_a_query_made_only_of_personal_details_is_not_sent(self):
        registry = build_registry(self.session())
        with mock.patch("Tools.web_search.search_internet") as engine:
            text, ok = registry.run("search_internet", {"query": "06 12 34 56 78"})
        engine.assert_not_called()
        self.assertIn("Not sent", text)

    def test_a_page_whose_address_holds_personal_details_is_not_opened(self):
        registry = build_registry(self.session())
        with mock.patch("Tools.read_websearch.requests.get") as get:
            text, ok = registry.run("read_webpage", {"url": "https://x.example/?mail=s.martin@acme.fr"})
        get.assert_not_called()
        self.assertFalse(ok)
        self.assertIn("personal details", text)

    def test_web_tools_can_be_turned_off(self):
        with mock.patch.dict(os.environ, {"AGENT_WEB_TOOLS": "false"}):
            registry = build_registry(self.session())
        self.assertEqual(registry.names(), ["file_leave_request"])

    def test_the_guidance_follows_the_tools_offered(self):
        everything = tool_guidance({"search_internet", "file_leave_request"})
        self.assertIn("Never put a personal detail", everything)
        leave_only = tool_guidance({"file_leave_request"})
        self.assertNotIn("search the internet", leave_only)
        self.assertIn("file_leave_request", leave_only)
        self.assertIn("what you look for and why", leave_only)


def scripted(*replies):
    replies = list(replies)
    return lambda messages, tools, temperature: replies.pop(0)


class TestTrace(unittest.TestCase):
    def registry(self):
        return ToolRegistry([Tool("search_internet", "Search", SEARCH,
                                  lambda query: "[1] Result\nhttp://r\nsnippet", "Searching the web")])

    def run_agent(self, out):
        from Agents.Engine import _activity_reporter
        llm = scripted(ModelReply("Je cherche la durée légale.", [{"function": {"name": "search_internet",
                                                                                 "arguments": {"query": "durée"}}}]),
                       ModelReply("Quatre jours."))
        return ReActAgent(llm, self.registry(), on_event=_activity_reporter(out)).run("Combien de jours ?")

    def test_the_web_gets_every_step_in_order(self):
        events = queue.Queue()
        self.run_agent(SseOutput(events))
        steps = []
        while not events.empty():
            name, data = events.get()
            if name == "trace":
                steps.append((data["kind"], data["text"]))
        self.assertEqual([kind for kind, _ in steps], ["thought", "action", "observation"])
        self.assertEqual(steps[0][1], "Je cherche la durée légale.")
        self.assertEqual(steps[1][1], "Searching the web: durée")
        self.assertIn("http://r", steps[2][1])

    def test_a_long_result_is_cut_for_the_web(self):
        events = queue.Queue()
        SseOutput(events).trace("observation", "x" * 5000)
        self.assertLess(len(events.get()[1]["text"]), 1600)

    def test_the_terminal_shows_one_line_per_step_and_not_the_thought_twice(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.run_agent(CliOutput())
        out = buf.getvalue()
        self.assertIn("· Searching the web: durée", out)
        self.assertIn("· result: [1] Result http://r snippet", out)
        self.assertNotIn("Je cherche", out)  # streamed by call_ollama, not printed again here


class TestEnv(unittest.TestCase):
    def test_the_file_never_overrides_the_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, ".env")
            with open(path, "w") as f:
                f.write("SENSAI_TEST_A=file\nSENSAI_TEST_B=file\n")
            with mock.patch.dict(os.environ, {"SENSAI_TEST_A": "shell"}):
                self.assertTrue(load_env(path))
                self.assertEqual((os.environ["SENSAI_TEST_A"], os.environ["SENSAI_TEST_B"]), ("shell", "file"))

    def test_a_missing_file_is_not_an_error(self):
        self.assertFalse(load_env("/nonexistent/.env"))


if __name__ == "__main__":
    unittest.main()
