"""
Tests for the chat integration of the agent (Engine + Router): the user never
asks for tools, simple messages stay at ONE model call, and a model without
tool support still works.

Usage (from the project root):
    python back/tests/Test_engine.py
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
from Agents.Router import asks_for_date, asks_for_leave, asks_for_search, should_offer_tools
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


class TestDateQuestion(unittest.TestCase):
    def test_date_questions_are_detected_and_get_no_tools(self):
        for text in ("on est quel jour ?", "On est quel jour aujourd'hui", "quel jour sommes-nous ?",
                     "c'est quel jour ?", "quelle est la date ?", "la date d'aujourd'hui stp",
                     "What day is it?", "what's the date today"):
            self.assertTrue(asks_for_date(text), text)
            self.assertFalse(should_offer_tools(text), text)

    def test_questions_about_other_days_are_not(self):
        for text in ("Quels jours fériés en 2026 ?", "Combien de jours pour un mariage ?",
                     "quel jour tombe le 14 juillet 2027 ?", "date limite pour poser mes congés ?"):
            self.assertFalse(asks_for_date(text), text)

    def test_a_leave_action_is_never_served_nor_stored_by_the_cache(self):
        from Cache import Policy
        text = "Pose moi un jour de congé : je commence le 3 Novembre 2026 et je termine le 6 Novembre 2026"
        self.assertFalse(Policy.may_serve(text))
        self.assertFalse(Policy.may_store(text, "Une longue réponse qui explique la règle des congés.",
                                          used_tools=False, had_history=False))

    def test_the_context_window_fits_the_budget_the_tools_and_the_answer(self):
        with mock.patch.object(Compression, "DEFAULT_BUDGET", 4000):
            self.assertEqual(Compression.context_window(), 7168)       # 4000 + 1536 + 1024, rounded up
            self.assertEqual(Compression.context_window(300), 6144)
        with mock.patch.object(Compression, "DEFAULT_BUDGET", 8000):
            self.assertEqual(Compression.context_window(1024), 11264)

    def test_a_date_question_is_never_served_nor_stored_by_the_cache(self):
        from Cache import Policy
        for text in ("quelle est la date ?", "what's the date"):
            self.assertFalse(Policy.may_serve(text), text)


class TestLeaveRequest(unittest.TestCase):
    def test_leave_requests_are_detected(self):
        for text in ("Je pose du 3 au 7 novembre pour des vacances", "je prends lundi en congé", "je pose lundi", "Je voudrais poser 2 jours de RTT",
                     "j'aimerais prendre mes congés la semaine du 14", "Pose-moi vendredi en congé",
                     "I'm taking Monday off", "I want to book a day off on Friday"):
            self.assertTrue(asks_for_leave(text), text)

    def test_questions_about_leave_are_not(self):
        for text in ("Comment poser un congé ?", "Combien de jours de congé pour un mariage ?",
                     "Est-ce que je peux poser des congés pendant ma période d'essai ?",
                     "Je prends le train demain, quel temps fera-t-il ?", "Quels jours fériés en 2026 ?"):
            self.assertFalse(asks_for_leave(text), text)

    def test_a_leave_request_gets_no_hr_excerpts(self):
        import Chatbot
        context = [{"role": "system", "content": "s"}]
        with mock.patch.object(Chatbot, "rag_message") as rag:
            Chatbot.add_documents(context, "Je pose du 3 au 7 novembre 2026 pour des vacances.", "http://x")
            rag.assert_not_called()
            Chatbot.add_documents(context, "Combien de jours pour un mariage ?", "http://x")
            rag.assert_called_once()


class TestSearchRequest(unittest.TestCase):
    def test_explicit_search_requests_are_detected(self):
        for text in ("fait des recherches", "fait des recherches sur internet", "cherche sur le web le match de demain",
                     "Can you search for it?", "look it up", "fais une recherche"):
            self.assertTrue(asks_for_search(text), text)

    def test_ordinary_questions_are_not(self):
        for text in ("Comment mettre en place le télétravail ?", "où est le siège de la société X ?",
                     "Quels sont mes congés ?"):
            self.assertFalse(asks_for_search(text), text)


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
                      ollama_url=self.url, search_motor="tavily", tools=self.registry(),
                      semantic_cache=False)  # the cache has its own tests (Test_cache.py)
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

    def test_an_explicit_search_request_is_nudged_for_that_turn_only(self):
        Fake.scripted = [[{"content": "ok"}]]
        self.turn(self.session(), "fait des recherches sur internet")
        sent = Fake.received[0]["messages"][-1]["content"]
        self.assertTrue(sent.startswith("fait des recherches sur internet"))
        self.assertIn("call search_internet now", sent)
        self.assertEqual([m["content"] for m in load_history(self.conversation_id)][0], "fait des recherches sur internet")

    def test_a_reply_that_repeats_an_old_refusal_is_retried(self):
        from Memories.Memory import save_message
        old = "Je suis désolé, mais je ne peux pas faire de recherches en temps réel sur Internet."
        save_message(self.conversation_id, "user", "q1"); save_message(self.conversation_id, "assistant", old)
        Fake.scripted = [[{"content": old}], [{"content": "Voici les étapes du télétravail."}]]
        done, out = self.turn(self.session(), "Comment mettre en place le télétravail ?")
        self.assertTrue(done)
        self.assertEqual(len(Fake.received), 2)
        self.assertEqual([m["content"] for m in load_history(self.conversation_id)][-1], "Voici les étapes du télétravail.")

    def test_seed_and_num_predict_reach_every_call_of_the_loop(self):
        Fake.scripted = [[{"content": "", "tool_calls": [call("search_internet", {"query": "x"})]}],
                         [{"content": "done"}]]
        self.turn(self.session(seed=42, num_predict=50, temperature=0.3), "Quelle est la dernière version de Python ?")
        for request in Fake.received:
            self.assertEqual(request["options"], {"seed": 42, "num_predict": 50, "temperature": 0.3,
                                                  "num_ctx": Compression.context_window(50)})

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

    def test_a_tool_call_written_as_text_runs_the_tool_and_is_never_shown(self):
        # What llama3.2:1b really sends: a copy of the tool spec, in the content, with the values in "parameters".
        # It also forgets its last closing brace.
        written = json.dumps({"type": "function", "function": {"name": "search_internet", "description": "Search",
                                                              "parameters": {"query": "smic 2026"}}})[:-1]
        Fake.scripted = [[{"content": written[:20]}, {"content": written[20:]}], [{"content": "Le SMIC est de..."}]]
        done, out = self.turn(self.session(), "Quel est le montant du SMIC en 2026 ?")
        self.assertTrue(done)
        self.assertEqual(self.searches, ["smic 2026"])
        self.assertNotIn('"function"', out)
        self.assertIn("Assistant: Le SMIC est de...", out)
        self.assertEqual(load_history(self.conversation_id)[-1]["content"], "Le SMIC est de...")

    def test_a_date_question_gets_no_tools_but_the_date(self):
        from datetime import date
        Fake.scripted = [[{"content": "Nous sommes jeudi."}]]
        self.turn(self.session(), "on est quel jour ?")
        self.assertNotIn("tools", Fake.received[0])
        from datetime import timedelta
        system = Fake.received[0]["messages"][0]["content"]
        self.assertIn(f"Today is {date.today():%A} {date.today().isoformat()}", system)
        self.assertIn(f"tomorrow is {date.today() + timedelta(days=1):%A}", system)

    def test_json_left_over_next_to_a_real_tool_call_is_never_shown(self):
        # llama3.2:1b: Ollama extracts one call, the rest of the JSON stays in the content.
        leftover = '}\n{"type":"function","function":{"name":"read_webpage","description":"Read"}}'
        Fake.scripted = [[{"content": leftover, "tool_calls": [call("search_internet", {"query": "smic"})]}],
                         [{"content": "Le SMIC est de..."}]]
        done, out = self.turn(self.session(), "Quel est le montant du SMIC en 2026 ?")
        self.assertTrue(done)
        self.assertEqual(self.searches, ["smic"])
        self.assertNotIn('"function"', out)

    def test_a_streamed_reply_the_agent_drops_is_retracted_in_the_web(self):
        import queue
        from Memories.Memory import save_message
        from Web.Output import SseOutput
        old = "Je suis désolé, mais je ne peux pas faire de recherches en temps réel sur Internet."
        save_message(self.conversation_id, "user", "q1"); save_message(self.conversation_id, "assistant", old)
        Fake.scripted = [[{"content": old}], [{"content": "Voici les étapes."}]]
        events = queue.Queue()
        self.turn(self.session(out=SseOutput(events)), "Comment mettre en place le télétravail ?")
        names = []
        while not events.empty():
            names.append(events.get()[0])
        self.assertIn("retract", names)
        self.assertGreater(names.index("token", names.index("retract")), names.index("retract"))  # the new answer follows

    def test_an_answer_that_is_json_but_not_a_tool_call_is_still_shown(self):
        Fake.scripted = [[{"content": '{"jours"'}, {"content": ': 4}'}]]
        done, out = self.turn(self.session(), "Donne la réponse en JSON")
        self.assertTrue(done)
        self.assertIn('Assistant: {"jours": 4}', out)
        self.assertEqual(len(Fake.received), 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
