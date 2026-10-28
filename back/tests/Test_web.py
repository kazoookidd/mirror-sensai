"""
Tests for the web interface API [X1] (back/Web/): login, chat streamed as
Server-Sent Events, conversations, settings and models.

No real Ollama: a fake server answers /api/tags and /api/chat. The web server
runs in a thread on a free port, the database is a temporary file.

Usage (from the project root):
    python back/tests/Test_web.py
"""

import io
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

import requests
import uvicorn

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Cache import Chat as CacheChat
from Memories import Database
from Memories.Auth import create_user
from Memories.Conversations import create_conversation
from Memories.Memory import load_history, save_message
from rag.Store import document_statuses
from Server import build_web_parser
from Web.App import FRONT_DIR, create_app

MODELS = ["m:latest", "other:7b"]
CHAT_MODELS = ["m"]  # other:7b is listed but refused by /api/chat, like a model deleted meanwhile


class FakeOllama(BaseHTTPRequestHandler):
    scripted: list = []

    def _json(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._json(200, {"models": [{"name": name} for name in MODELS]})

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path != "/api/chat":
            self._json(404, {"error": "not found"})
            return
        if payload["model"] not in CHAT_MODELS:
            self._json(404, {"error": f"model '{payload['model']}' not found"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        for text in type(self).scripted.pop(0):
            self.wfile.write((json.dumps({"message": {"content": text}, "done": False}) + "\n").encode())
        self.wfile.write((json.dumps({"message": {"content": ""}, "done": True,
                                      "prompt_eval_count": 20, "eval_count": 7}) + "\n").encode())

    def log_message(self, *args):
        pass


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def events(response) -> list[tuple[str, dict]]:
    """The Server-Sent Events of a /api/chat response, as (name, data)."""
    parsed = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        parsed.append((lines["event"], json.loads(lines["data"])))
    return parsed


class TestWebApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.patches = [mock.patch.object(Database, "DB_PATH", os.path.join(cls.tmp.name, "t.db")),
                       mock.patch.object(CacheChat, "ENABLED", False)]
        for patch in cls.patches:
            patch.start()
        Database.init_db()
        create_user("alice", "alice@example.com", "pw")
        create_user("bob", "bob@example.com", "pw")

        cls.ollama = HTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=cls.ollama.serve_forever, daemon=True).start()
        args = build_web_parser().parse_args(
            ["--model", "m", "--ollama-url", f"http://127.0.0.1:{cls.ollama.server_port}"])
        port = free_port()
        cls.url = f"http://127.0.0.1:{port}"
        cls.server = uvicorn.Server(uvicorn.Config(create_app(args), port=port, log_level="error"))
        threading.Thread(target=cls.server.run, daemon=True).start()
        while not cls.server.started:
            time.sleep(0.02)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.ollama.shutdown()
        cls.ollama.server_close()
        for patch in cls.patches:
            patch.stop()
        cls.tmp.cleanup()

    def login(self, email="alice@example.com", password="pw") -> requests.Session:
        client = requests.Session()
        with redirect_stdout(io.StringIO()):  # build_session prints its startup notes
            response = client.post(f"{self.url}/api/login", json={"email": email, "password": password})
        self.assertEqual(response.status_code, 200, response.text)
        return client

    def chat(self, client, message, conversation_id=None, answer=("Bonjour.",)):
        FakeOllama.scripted = [list(answer)]
        return client.post(f"{self.url}/api/chat", json={"message": message, "conversation_id": conversation_id})

    def test_wrong_password_is_refused(self):
        response = requests.post(f"{self.url}/api/login", json={"email": "alice@example.com", "password": "no"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Incorrect email or password.")

    def test_login_by_email_or_user_id(self):
        client = self.login()
        self.assertEqual(client.get(f"{self.url}/api/me").json(), {"user_id": "alice", "model": "m"})
        self.login(email="alice")

    def test_routes_need_a_session(self):
        self.assertEqual(requests.get(f"{self.url}/api/me").json(), {"user_id": None})
        self.assertEqual(requests.get(f"{self.url}/api/conversations").status_code, 401)
        self.assertEqual(requests.post(f"{self.url}/api/chat", json={"message": "x"}).status_code, 401)

    def test_a_first_message_creates_the_conversation_and_streams_the_answer(self):
        client = self.login()
        response = self.chat(client, "Combien de jours de congé ?", answer=("Cinq ", "semaines."))
        self.assertEqual(response.headers["content-type"].split(";")[0], "text/event-stream")
        stream = events(response)
        names = [name for name, _ in stream]
        self.assertEqual(names[0], "conversation")
        self.assertIn("context", names)
        self.assertEqual("".join(data["text"] for name, data in stream if name == "token"), "Cinq semaines.")
        self.assertEqual(stream[-2], ("usage", {"prompt": 20, "completion": 7, "approximate": False}))
        self.assertEqual(stream[-1], ("done", {"ok": True}))
        conversation = stream[0][1]
        self.assertEqual(conversation["title"], "Combien de jours de congé ?")
        self.assertEqual(load_history(conversation["id"])[-1], {"role": "assistant", "content": "Cinq semaines."})

    def test_a_missing_model_is_reported_and_nothing_is_saved(self):
        client = self.login()
        client.put(f"{self.url}/api/model", json={"name": "other:7b"})
        stream = events(self.chat(client, "Bonjour"))
        errors = [data for name, data in stream if name == "error"]
        self.assertEqual([error["kind"] for error in errors], ["model"])
        self.assertEqual(stream[-1], ("done", {"ok": False}))
        self.assertEqual(load_history(stream[0][1]["id"]), [])

    def test_empty_message_and_other_users_conversation_are_refused(self):
        client = self.login()
        self.assertEqual(self.chat(client, "   ").status_code, 422)
        foreign = create_conversation("bob", "Bob")
        self.assertEqual(self.chat(client, "Bonjour", conversation_id=foreign).status_code, 404)
        self.assertEqual(client.get(f"{self.url}/api/conversations/{foreign}/messages").status_code, 404)
        self.assertEqual(client.delete(f"{self.url}/api/conversations/{foreign}").status_code, 404)

    def test_conversations_list_rename_and_delete(self):
        client = self.login(email="bob@example.com")
        conversation = create_conversation("bob", "Première")
        save_message(conversation, "user", "Question")
        save_message(conversation, "assistant", "Une **réponse**\nsur deux lignes.")
        create_conversation("bob", "Vide")  # never answered: not listed
        listed = client.get(f"{self.url}/api/conversations").json()["conversations"]
        self.assertEqual([item["title"] for item in listed], ["Première"])
        self.assertEqual(listed[0]["preview"], "Une **réponse** sur deux lignes.")

        self.assertEqual(client.patch(f"{self.url}/api/conversations/{conversation}", json={"title": "Renommée"}).status_code, 200)
        self.assertEqual(client.get(f"{self.url}/api/conversations/{conversation}/messages").json()["conversation"]["title"], "Renommée")
        self.assertEqual(client.delete(f"{self.url}/api/conversations/{conversation}").status_code, 200)
        self.assertEqual(client.get(f"{self.url}/api/conversations").json()["conversations"], [])

    def test_editing_or_regenerating_a_question_continues_in_a_branch(self):
        client = self.login()
        first = events(self.chat(client, "Q1", answer=("A1",)))[0][1]
        root = first["id"]
        self.chat(client, "Q2", conversation_id=root, answer=("A2",))
        FakeOllama.scripted = [["A2 bis"]]
        stream = events(client.post(f"{self.url}/api/chat", json={"message": "Q2 bis", "conversation_id": root, "branch_from": 2}))
        branch = stream[0][1]
        self.assertEqual((branch["branch"], branch["title"]), (True, "Q1"))
        self.assertEqual(stream[-1], ("done", {"ok": True}))
        self.assertEqual([m["content"] for m in load_history(branch["id"])], ["Q1", "A1", "Q2 bis", "A2 bis"])
        self.assertEqual([m["content"] for m in load_history(root)], ["Q1", "A1", "Q2", "A2"])

        listed = [item["id"] for item in client.get(f"{self.url}/api/conversations").json()["conversations"]]
        self.assertIn(root, listed)
        self.assertNotIn(branch["id"], listed)
        data = client.get(f"{self.url}/api/conversations/{branch['id']}/messages").json()
        self.assertEqual((data["conversation"]["title"], data["conversation"]["root_id"]), ("Q1", root))
        self.assertEqual(data["versions"], [{"index": 2, "current": 2, "conversations": [root, branch["id"]]}])

        FakeOllama.scripted = [["A2 again"]]
        client.post(f"{self.url}/api/chat", json={"message": "Q2", "conversation_id": root, "branch_from": 2})
        versions = client.get(f"{self.url}/api/conversations/{root}/messages").json()["versions"]
        self.assertEqual([(v["index"], v["current"], len(v["conversations"])) for v in versions], [(2, 1, 3)])

        for wrong in (1, 9):
            response = client.post(f"{self.url}/api/chat", json={"message": "x", "conversation_id": root, "branch_from": wrong})
            self.assertEqual(response.status_code, 422)
        deleted = client.delete(f"{self.url}/api/conversations/{root}").json()["deleted"]
        self.assertEqual(deleted[:2], [root, branch["id"]])
        self.assertEqual(client.get(f"{self.url}/api/conversations/{branch['id']}/messages").status_code, 404)

    def test_a_branch_is_removed_even_when_its_turn_crashes(self):
        client = self.login()
        root = events(self.chat(client, "Q1", answer=("A1",)))[0][1]["id"]
        with mock.patch("Web.Routes.Chat.chat_turn", side_effect=RuntimeError("boom")), \
             self.assertLogs("Web.Routes.Chat", level="ERROR"):
            stream = events(client.post(f"{self.url}/api/chat", json={"message": "Q1 bis", "conversation_id": root, "branch_from": 0}))
        self.assertEqual(stream[-2:], [("error", {"text": "Internal server error.", "kind": "other"}), ("done", {"ok": False})])
        self.assertEqual(client.get(f"{self.url}/api/conversations/{stream[0][1]['id']}/messages").status_code, 404)

    def test_a_branch_never_answers_from_the_semantic_cache(self):
        client = self.login()
        root = events(self.chat(client, "Q1", answer=("A1",)))[0][1]["id"]
        seen = []
        with mock.patch("Web.Routes.Chat.chat_turn", side_effect=lambda session, text: seen.append(session.semantic_cache)):
            client.post(f"{self.url}/api/chat", json={"message": "Q1", "conversation_id": root, "branch_from": 0})
            client.post(f"{self.url}/api/chat", json={"message": "Q2", "conversation_id": root})
        self.assertEqual(seen, [False, True])

    def test_a_branch_whose_answer_fails_is_removed(self):
        client = self.login()
        root = events(self.chat(client, "Q1", answer=("A1",)))[0][1]["id"]
        client.put(f"{self.url}/api/model", json={"name": "other:7b"})
        stream = events(client.post(f"{self.url}/api/chat", json={"message": "Q1 bis", "conversation_id": root, "branch_from": 0}))
        self.assertEqual(stream[-1], ("done", {"ok": False}))
        self.assertEqual(client.get(f"{self.url}/api/conversations/{stream[0][1]['id']}/messages").status_code, 404)
        self.assertEqual(client.post(f"{self.url}/api/chat/stop").json(), {"stopping": False})

    def test_settings_use_the_cli_parsers(self):
        client = self.login()
        self.assertEqual(client.put(f"{self.url}/api/settings/temperature", json={"value": "0.3"}).status_code, 200)
        self.assertEqual(client.get(f"{self.url}/api/settings").json()["temperature"], 0.3)
        self.assertEqual(client.put(f"{self.url}/api/settings/temperature", json={"value": "9"}).status_code, 422)
        self.assertEqual(client.put(f"{self.url}/api/settings/num-predict", json={"value": "default"}).status_code, 200)
        self.assertEqual(client.put(f"{self.url}/api/settings/nope", json={"value": "1"}).status_code, 404)

    def test_models_and_switching(self):
        client = self.login()
        data = client.get(f"{self.url}/api/models").json()
        self.assertEqual([model["name"] for model in data["models"]], MODELS)
        self.assertTrue(data["installed"])
        self.assertEqual(client.put(f"{self.url}/api/model", json={"name": "other:7b"}).json(), {"current": "other:7b"})
        self.assertEqual(client.put(f"{self.url}/api/model", json={"name": "absent"}).status_code, 404)

    def test_personas_and_switching_keep_the_session(self):
        client = self.login()
        data = client.get(f"{self.url}/api/personas").json()
        self.assertEqual(data["current"], "default")
        self.assertIn("hr_onboarding", [persona["id"] for persona in data["personas"]])
        self.assertEqual(client.put(f"{self.url}/api/persona", json={"id": "hr_senior"}).json(), {"current": "hr_senior"})
        self.assertEqual(client.put(f"{self.url}/api/persona", json={"id": "2"}).json(), {"current": "hr_onboarding"})
        self.assertEqual(client.put(f"{self.url}/api/persona", json={"id": "nobody"}).status_code, 404)
        output = client.post(f"{self.url}/api/command", json={"text": "/persona"}).json()["output"]
        self.assertIn("(hr_onboarding)", output)

    def test_slash_commands_run_the_cli_command(self):
        client = self.login()
        run = lambda text: client.post(f"{self.url}/api/command", json={"text": text})
        result = run("/temperature 0.4").json()
        self.assertEqual(result["command"], "/temperature")
        self.assertIn("Temperature set to 0.4", result["output"])
        self.assertEqual(client.get(f"{self.url}/api/settings").json()["temperature"], 0.4)
        self.assertEqual(run("/model other:7b").json()["model"], "other:7b")
        self.assertIn("=== Personas ===", run("/personas").json()["output"])
        self.assertIn("Unknown command '/nope'", run("/nope").json()["output"])

    def test_interactive_or_unsafe_commands_are_refused(self):
        client = self.login()
        run = lambda text: client.post(f"{self.url}/api/command", json={"text": text})
        self.assertEqual(run("/new").status_code, 422)
        self.assertEqual(run("/conversations").status_code, 422)
        self.assertEqual(run("/ingest /etc").status_code, 422)
        self.assertEqual(run("bonjour").status_code, 422)
        self.assertEqual(requests.post(f"{self.url}/api/command", json={"text": "/help"}).status_code, 401)

    def test_status_and_front_files(self):
        self.assertEqual(requests.get(f"{self.url}/api/status").json()["ollama"], True)
        page = requests.get(f"{self.url}/")
        if not FRONT_DIR.is_dir():
            self.assertEqual(page.status_code, 503)
            return
        self.assertIn('<div id="root"', page.text)
        self.assertEqual(page.headers["cache-control"], "no-cache")


class TestDocumentStatuses(unittest.TestCase):
    def test_files_not_indexed_yet(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(
                Database, "DB_PATH", os.path.join(folder, "t.db")):
            Path(folder, "docs").mkdir()
            Path(folder, "docs", "conges.md").write_text("Cinq semaines.", encoding="utf-8")
            statuses = document_statuses(Path(folder, "docs"))
        self.assertEqual([(s["source"], s["status"], s["chunks"]) for s in statuses], [("conges.md", "not_indexed", 0)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
