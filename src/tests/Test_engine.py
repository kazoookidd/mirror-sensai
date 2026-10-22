"""
Tests for the chat integration of the agent (Engine + Router): the user never
asks for tools, simple messages stay at ONE model call, and a model without
tool support still works.

Usage (from the project root):
    python src/tests/Test_engine.py
"""

import io
import json
import os
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Agents import Engine
from Agents.Router import should_offer_tools
from Agents.Tooling import Tool, ToolRegistry
from Chatbot import chat_turn
from Commands import Session
from Memories import Compression, Database
from Memories.Auth import get_or_create_user
from Memories.Conversations import create_conversation
from Memories.Memory import load_history

SEARCH = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}


def call(name, args):
    return {"function": {"name": name, "arguments": args}}


class Fake(BaseHTTPRequestHandler):
    scripted: list = []   # per request: list of message dicts, or an int HTTP status
    received: list = []

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).received.append(payload)
        item = type(self).scripted.pop(0)
        if isinstance(item, int):
            body = json.dumps({"error": "this model does not support tools"}).encode()
            self.send_response(item); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            return
        self.send_response(200); self.send_header("Content-Type", "application/x-ndjson"); self.end_headers()
        for message in item:
            self.wfile.write((json.dumps({"message": {"role": "assistant", **message}, "done": False}) + "\n").encode())
        self.wfile.write((json.dumps({"message": {"role": "assistant", "content": ""}, "done": True,
                                      "prompt_eval_count": 20, "eval_count": 7}) + "\n").encode())

    def log_message(self, *a):
        pass


class TestRouter(unittest.TestCase):
    def test_small_talk_gets_no_tools(self):
        for text in ("Bonjour", "hello!", "Merci beaucoup", "ok", "Thanks.", "Bonjour Sensai", "au revoir", ""):
            self.assertFalse(should_offer_tools(text), text)

    def test_real_questions_get_tools(self):
        for text in ("Quelle est la dernière version de Python ?", "Merci, et pour le télétravail ?",
                     "hello, what is the minimum wage in France in 2026?"):
            self.assertTrue(should_offer_tools(text), text)


class TestEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Fake)
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close()

    def setUp(self):
        Fake.received, Fake.scripted = [], []
        Engine._NO_TOOLS.clear()
        self.tmp = tempfile.TemporaryDirectory()
        for patch in (mock.patch.object(Database, "DB_PATH", os.path.join(self.tmp.name, "t.db")),
                      mock.patch.object(Compression, "DEFAULT_BUDGET", 4000)):
            patch.start(); self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)
        Database.init_db()
        get_or_create_user("alice", "pw", email="a@example.com")
        self.searches = []
        self.conversation_id = create_conversation("alice", "t")

    def registry(self):
        def search_internet(query):
            self.searches.append(query)
            return "[1] Result\nhttp://r\nsnippet"
        return ToolRegistry([Tool("search_internet", "Search", SEARCH, search_internet, "Searching the web")])

    def session(self, **kw):
        values = dict(user_id="alice", conversation_id=self.conversation_id, model="m", persona_id="default",
                      personas={"default": {"id": "default", "name": "D", "description": "",
                                            "system_prompt": "You are a test assistant."}},
                      ollama_url=self.url, search_motor="tavily", tools=self.registry())
        values.update(kw)
        return Session(**values)

    def turn(self, session, text):
        buf = io.StringIO()
        with redirect_stdout(buf):
            done = chat_turn(session, text)
        return done, buf.getvalue()

    def test_a_question_that_needs_no_tool_is_one_streamed_call(self):
        Fake.scripted = [[{"content": "Paris "}, {"content": "is the capital."}]]
        done, out = self.turn(self.session(), "What is the capital of France?")
        self.assertTrue(done)
        self.assertEqual(len(Fake.received), 1)
        self.assertEqual([t["function"]["name"] for t in Fake.received[0]["tools"]], ["search_internet"])
        self.assertIn("Assistant: Paris is the capital.\n", out)
        self.assertIn("tokens: 20 in · 7 out", out)
        self.assertEqual(self.searches, [])

    def test_system_prompt_gets_the_tool_guidance_only_when_tools_are_offered(self):
        Fake.scripted = [[{"content": "a"}], [{"content": "b"}]]
        self.turn(self.session(), "What is the capital of France?")
        self.turn(self.session(), "merci")
        offered, plain = (r["messages"][0]["content"] for r in Fake.received)
        self.assertIn("You are a test assistant.", offered)
        self.assertIn("--- Tools ---", offered)
        self.assertNotIn("--- Tools ---", plain)

    def test_small_talk_sends_no_tools_at_all(self):
        Fake.scripted = [[{"content": "Bonjour !"}]]
        self.turn(self.session(), "Bonjour")
        self.assertNotIn("tools", Fake.received[0])

    def test_a_tool_call_runs_the_tool_streams_the_final_answer_once_and_stores_only_the_exchange(self):
        Fake.scripted = [
            [{"content": "", "tool_calls": [call("search_internet", {"query": "python version"})]}],
            [{"content": "Python "}, {"content": "3.14."}],
        ]
        done, out = self.turn(self.session(), "Quelle est la dernière version de Python ?")
        self.assertTrue(done)
        self.assertEqual(self.searches, ["python version"])
        self.assertEqual(len(Fake.received), 2)
        self.assertEqual(Fake.received[1]["messages"][-1]["role"], "tool")
        self.assertIn("Searching the web: python version", out)
        self.assertEqual(out.count("Python 3.14."), 1)  # not printed twice
        self.assertEqual([m["content"] for m in load_history(self.conversation_id)],
                         ["Quelle est la dernière version de Python ?", "Python 3.14."])

    def test_model_options_go_with_every_call_of_a_tool_turn(self):
        Fake.scripted = [
            [{"content": "", "tool_calls": [call("search_internet", {"query": "python version"})]}],
            [{"content": "Python 3.14."}],
        ]
        session = self.session(temperature=0.2, seed=42, num_predict=300)
        self.turn(session, "Quelle est la dernière version de Python ?")
        self.assertEqual(len(Fake.received), 2)
        for request in Fake.received:
            self.assertEqual(request["options"],
                             {"seed": 42, "num_predict": 300, "temperature": 0.2})

    def test_tool_activity_line_can_be_hidden(self):
        Fake.scripted = [[{"content": "", "tool_calls": [call("search_internet", {"query": "x"})]}],
                         [{"content": "done"}]]
        _, out = self.turn(self.session(show_tool_activity=False), "Quelle est la dernière version de Python ?")
        self.assertNotIn("Searching the web", out)
        self.assertIn("done", out)

    def test_no_registry_or_disabled_tools_means_a_plain_call(self):
        for kw in ({"tools": None}, {"tools_enabled": False}):
            Fake.received, Fake.scripted = [], [[{"content": "ok"}]]
            self.turn(self.session(**kw), "What is the capital of France?")
            self.assertNotIn("tools", Fake.received[0], kw)

    def test_a_model_without_tool_support_is_served_without_tools_and_remembered(self):
        Fake.scripted = [400, [{"content": "plain answer"}], [{"content": "second"}]]
        done, out = self.turn(self.session(), "What is the capital of France?")
        self.assertTrue(done)
        self.assertIn("cannot use tools", out)
        self.assertIn("plain answer", out)
        self.assertNotIn("Error", out)
        self.assertNotIn("tools", Fake.received[1])
        self.turn(self.session(), "Another real question please?")
        self.assertEqual(len(Fake.received), 3)           # no new failed attempt
        self.assertNotIn("tools", Fake.received[2])

    def test_ollama_errors_other_than_tool_support_are_reported_once_and_nothing_is_saved(self):
        done, out = self.turn(self.session(ollama_url="http://127.0.0.1:9"), "What is the capital of France?")
        self.assertFalse(done)
        self.assertEqual(out.count("cannot connect to Ollama"), 1)
        self.assertEqual(load_history(self.conversation_id), [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
