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
from Memories.Conversations import create_conversation, list_conversations
from Memories.Memory import load_history, save_message
from rag import Attachments, Store
from rag.Store import document_statuses
from Server import build_web_parser
from Web.App import FRONT_DIR, create_app
from Web.Routes import Documents

MODELS = ["m:latest", "other:7b"]
CHAT_MODELS = ["m"]  # other:7b is listed but refused by /api/chat, like a model deleted meanwhile


class FakeOllama(BaseHTTPRequestHandler):
    scripted: list = []
    received: list = []  # the /api/chat payloads, latest last

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
        type(self).received.append(payload)
        if payload["model"] not in CHAT_MODELS:
            self._json(404, {"error": f"model '{payload['model']}' not found"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        for part in type(self).scripted.pop(0):
            message = part if isinstance(part, dict) else {"content": part}  # a dict carries tool_calls
            self.wfile.write((json.dumps({"message": message, "done": False}) + "\n").encode())
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
        self.assertEqual(client.get(f"{self.url}/api/me").json(), {"user_id": "alice", "model": "m", "account_role": "hr"})
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

    def test_an_out_of_scope_question_is_refused_before_the_model(self):
        client = self.login()
        before = len(FakeOllama.received)
        stream = events(self.chat(client, "Quel est le salaire de Marc ?"))
        errors = [data for name, data in stream if name == "error"]
        self.assertEqual([error["kind"] for error in errors], ["guardrail"])
        self.assertEqual(stream[-1], ("done", {"ok": False}))
        self.assertEqual(len(FakeOllama.received), before)
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

    def test_the_history_shows_the_model_of_the_last_answer_and_the_documents_switch(self):
        client = self.login()
        conversation = events(self.chat(client, "Q1", answer=("A1",)))[0][1]["id"]
        listed = {item["id"]: item for item in client.get(f"{self.url}/api/conversations").json()["conversations"]}
        self.assertEqual(listed[conversation]["model"], client.get(f"{self.url}/api/me").json()["model"])
        self.assertTrue(client.get(f"{self.url}/api/settings").json()["hr_documents"])
        self.assertEqual(client.put(f"{self.url}/api/settings/documents", json={"value": "off"}).json(), {"name": "documents", "value": "off"})
        self.assertFalse(client.get(f"{self.url}/api/settings").json()["hr_documents"])
        client.put(f"{self.url}/api/settings/documents", json={"value": "on"})

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

    def test_only_hr_accounts_turn_the_guardrails_off(self):
        from Memories.Auth import ROLE_EMPLOYEE
        create_user("gina", "gina@example.com", "pw", role=ROLE_EMPLOYEE)
        employee = self.login("gina@example.com")
        refused = employee.put(f"{self.url}/api/settings/guardrails", json={"value": "off"})
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(employee.put(f"{self.url}/api/settings/guardrails-output", json={"value": "refuse"}).status_code, 403)
        self.assertTrue(employee.get(f"{self.url}/api/settings").json()["guardrails"])
        hr = self.login()
        self.assertEqual(hr.put(f"{self.url}/api/settings/guardrails", json={"value": "off"}).status_code, 200)
        self.assertFalse(hr.get(f"{self.url}/api/settings").json()["guardrails"])
        hr.put(f"{self.url}/api/settings/guardrails", json={"value": "on"})

    def test_profile_is_saved_checked_and_used_by_the_next_answer(self):
        client = self.login("bob@example.com")
        self.assertEqual(client.get(f"{self.url}/api/profile").json(),
                         {"profile": {"name": "", "role": "", "department": "", "language": "", "tone": "",
                                      "instructions": ""}, "context": "", "account": {"role": "hr", "label": "HR"}})
        saved = client.put(f"{self.url}/api/profile", json={"role": "  RH  ", "tone": "Concise"}).json()
        self.assertEqual((saved["profile"]["role"], saved["profile"]["tone"]), ("RH", "concise"))
        self.assertEqual(saved["context"], "[profile]\njob: RH\ntone: concise")
        refused = client.put(f"{self.url}/api/profile", json={"tone": "funny"})
        self.assertEqual(refused.status_code, 422)
        self.assertIn("tone must be one of", refused.json()["detail"])
        self.assertEqual(client.get(f"{self.url}/api/profile").json()["profile"]["tone"], "concise")
        self.assertEqual(self.login().get(f"{self.url}/api/profile").json()["context"], "")  # alice's own
        self.assertEqual(requests.get(f"{self.url}/api/profile").status_code, 401)

        events(self.chat(client, "Bonjour"))
        self.assertIn("job: RH", FakeOllama.received[-1]["messages"][0]["content"])
        output = client.post(f"{self.url}/api/command", json={"text": "/profile"}).json()["output"]
        self.assertIn("RH", output)

    def test_signing_up_creates_an_employee_account_and_logs_in(self):
        client = requests.Session()
        with redirect_stdout(io.StringIO()):
            response = client.post(f"{self.url}/api/signup", json={
                "user_id": "sophie.m", "email": " sophie@example.com ", "password": "longenough",
                "role": "hr"})  # a role sent by the client is ignored
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["account_role"], "employee")
        self.assertEqual(client.get(f"{self.url}/api/me").json()["account_role"], "employee")
        self.assertEqual(client.get(f"{self.url}/api/profile").json()["account"], {"role": "employee", "label": "Employee"})
        refused = client.put(f"{self.url}/api/profile", json={"account_role": "hr"})
        self.assertEqual(refused.status_code, 422)  # the role is not a profile field
        self.assertEqual(self.login("sophie@example.com", "longenough").get(f"{self.url}/api/me").json()["user_id"],
                         "sophie.m")

    def test_only_hr_accounts_see_every_leave_request(self):
        from Memories.Auth import ROLE_EMPLOYEE
        from Memories.Leaves import save_leave_request
        create_user("emma", "emma@example.com", "pw", role=ROLE_EMPLOYEE)
        save_leave_request("emma", {"leave_type": "bereavement", "start_date": "2026-11-03",
                                    "end_date": "2026-11-06", "reason": "deuil"})
        data = self.login().get(f"{self.url}/api/leave-requests").json()  # alice: HR
        mine = [r for r in data["requests"] if r["user_id"] == "emma"]
        self.assertEqual(len(mine), 1)
        self.assertEqual((mine[0]["email"], mine[0]["type_label"], mine[0]["status_label"]),
                         ("emma@example.com", "Bereavement", "Pending"))
        refused = self.login("emma@example.com").get(f"{self.url}/api/leave-requests")
        self.assertEqual(refused.status_code, 403)
        self.assertNotIn("requests", refused.json())
        self.assertEqual(requests.get(f"{self.url}/api/leave-requests").status_code, 401)

        # HR decides; the employee cannot, even by calling the route by hand.
        hr = self.login()
        url = f"{self.url}/api/leave-requests/{mine[0]['id']}"
        self.assertEqual(self.login("emma@example.com").put(url, json={"status": "approved"}).status_code, 403)
        decided = hr.put(url, json={"status": "approved"}).json()["request"]
        self.assertEqual((decided["status"], decided["status_label"], decided["decided_by"]), ("approved", "Approved", "alice"))
        self.assertEqual(hr.put(url, json={"status": "maybe"}).status_code, 422)
        self.assertEqual(hr.put(f"{self.url}/api/leave-requests/999999", json={"status": "approved"}).status_code, 404)
        from Memories.Leaves import STATUS_PENDING, cancel_leave_request
        hr.put(url, json={"status": STATUS_PENDING})
        cancel_leave_request("emma", mine[0]["id"])
        self.assertEqual(hr.put(url, json={"status": "approved"}).status_code, 409)

    def test_sign_up_is_refused_with_the_reason(self):
        cases = [({"user_id": "alice"}, 409, "user id is already used"),
                 ({"email": "alice@example.com"}, 409, "email address is already used"),
                 ({"user_id": "a@b"}, 422, "user id must be"),
                 ({"user_id": "x"}, 422, "user id must be"),
                 ({"email": "not-an-email"}, 422, "valid email"),
                 ({"password": "short"}, 422, "at least 8")]
        for change, status, message in cases:
            body = {"user_id": "newbie", "email": "newbie@example.com", "password": "longenough", **change}
            response = requests.post(f"{self.url}/api/signup", json=body)
            self.assertEqual(response.status_code, status, change)
            self.assertIn(message, response.json()["detail"], change)
            self.assertNotIn("set-cookie", {k.lower() for k in response.headers}, change)

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

    def test_a_conversation_is_downloaded_in_each_format(self):
        client = self.login()
        conversation = create_conversation("alice", "Congés")
        save_message(conversation, "user", "Combien ?")
        save_message(conversation, "assistant", "Cinq semaines.")
        url = f"{self.url}/api/conversations/{conversation}/export"
        markdown = client.get(url, params={"format": "md"})
        self.assertEqual(markdown.headers["content-disposition"], f'attachment; filename="sensai-{conversation}-conges.md"')
        self.assertIn("## SENSAI\n\nCinq semaines.", markdown.text)
        self.assertEqual(client.get(url, params={"format": "json"}).json()["title"], "Congés")
        self.assertTrue(client.get(url, params={"format": "pdf"}).content.startswith(b"%PDF-"))
        self.assertEqual(client.get(url, params={"format": "xml"}).status_code, 422)
        self.assertEqual(client.get(f"{self.url}/api/conversations/{create_conversation('alice')}/export").status_code, 422)
        self.assertEqual(self.login(email="bob@example.com").get(url).status_code, 404)
        self.assertEqual(requests.get(url).status_code, 401)
        self.assertEqual(client.post(f"{self.url}/api/command", json={"text": "/export pdf"}).status_code, 422)

    def test_a_public_link_works_without_logging_in_until_it_is_turned_off(self):
        client = self.login()
        conversation = create_conversation("alice", "Congés")
        save_message(conversation, "user", "Combien ?")
        save_message(conversation, "assistant", "Cinq semaines.")
        url = f"{self.url}/api/conversations/{conversation}/share"
        self.assertEqual(client.get(url).json(), {"share": None})
        share = client.post(url).json()["share"]
        self.assertEqual(client.get(url).json()["share"], share)
        self.assertEqual(self.login(email="bob@example.com").post(url).status_code, 404)
        public = requests.get(f"{self.url}/api/share/{share['token']}")
        self.assertEqual(public.status_code, 200)
        self.assertEqual(set(public.json()), {"title", "messages", "created_at", "expires_at"})
        self.assertNotIn("alice", public.text)
        self.assertEqual(public.json()["messages"][1], {"role": "assistant", "content": "Cinq semaines."})
        self.assertEqual(client.delete(url).json(), {"share": None})
        gone = requests.get(f"{self.url}/api/share/{share['token']}")
        self.assertEqual((gone.status_code, gone.json()["detail"]), (404, "This link does not exist or was turned off."))
        token = client.post(url).json()["share"]["token"]
        conn = Database.get_connection()
        conn.execute("UPDATE shares SET expires_at = datetime('now', '-1 minute')")
        conn.commit()
        conn.close()
        expired = requests.get(f"{self.url}/api/share/{token}")
        self.assertEqual((expired.status_code, expired.json()["detail"]), (410, "This link has expired."))

    def test_a_leave_request_waits_on_a_confirmation_card_until_confirm_or_cancel(self):
        create_user("carol", "carol@example.com", "pw")
        client = self.login(email="carol@example.com")
        leave = {"leave_type": "paid_leave", "start_date": "2026-11-09", "end_date": "2026-11-10", "reason": ""}
        call = {"content": "", "tool_calls": [{"function": {"name": "file_leave_request", "arguments": leave}}]}
        stream = events(self.chat(client, "Je pose lundi et mardi", answer=(call,)))
        cards = [data for name, data in stream if name == "confirmation"]
        self.assertEqual([card["title"] for card in cards], ["Leave request to confirm"])
        self.assertIn("from:   2026-11-09", cards[0]["plan"])
        conversation = stream[0][1]["id"]
        url = f"{self.url}/api/conversations/{conversation}/messages"
        self.assertEqual(client.get(url).json()["pending"], cards[0])
        other = create_conversation("carol", "Autre")
        self.assertIsNone(client.get(f"{self.url}/api/conversations/{other}/messages").json()["pending"])

        cancel = client.post(f"{self.url}/api/command", json={"text": "/cancel"}).json()
        self.assertIn("Dropped: Leave request to confirm", cancel["output"])
        self.assertIsNone(cancel["pending"])
        self.assertIsNone(client.get(url).json()["pending"])
        saved = client.get(url).json()["messages"][-1]["content"]
        self.assertTrue(saved.endswith("Cancelled: nothing was done."), saved)
        self.assertNotIn("Nothing has been done yet", saved)

        stream = events(self.chat(client, "Je pose lundi et mardi", conversation_id=conversation, answer=(call,)))
        confirm = client.post(f"{self.url}/api/command", json={"text": "/confirm", "conversation_id": conversation}).json()
        self.assertIn("saved for carol", confirm["output"])
        saved = client.get(url).json()["messages"][-1]["content"]
        self.assertIn("saved for carol", saved)
        self.assertNotIn("Nothing has been done yet", saved)
        self.assertIsNone(client.post(f"{self.url}/api/command", json={"text": "/leaves"}).json()["pending"])

    def test_the_card_stays_in_the_chat_of_its_leave_request(self):
        create_user("dora", "dora@example.com", "pw")
        client = self.login(email="dora@example.com")
        leave = {"leave_type": "paid_leave", "start_date": "2026-12-14", "end_date": "2026-12-18", "reason": ""}
        call = {"content": "", "tool_calls": [{"function": {"name": "file_leave_request", "arguments": leave}}]}
        first = events(self.chat(client, "Je pose du 14 au 18", answer=(call,)))[0][1]["id"]
        second = events(self.chat(client, "Combien de jours pour un mariage ?", answer=("Quatre jours.",)))[0][1]["id"]
        url = f"{self.url}/api/conversations/{{}}/messages"
        self.assertIsNone(client.get(url.format(second)).json()["pending"])  # was the card of the first chat
        card = client.get(url.format(first)).json()["pending"]
        self.assertEqual(card["title"], "Leave request to confirm")
        command = lambda conversation: client.post(f"{self.url}/api/command",
                                                   json={"text": "/leaves", "conversation_id": conversation}).json()
        self.assertEqual(command(first)["pending"], card)
        self.assertIsNone(command(second)["pending"])
        self.assertIn("Dropped", client.post(f"{self.url}/api/command", json={"text": "/cancel", "conversation_id": first}).json()["output"])

    def test_an_answer_keeps_its_sources_and_the_scope_limits_the_search(self):
        import Chatbot
        create_user("hugo", "hugo@example.com", "pw")
        client = self.login(email="hugo@example.com")
        sources = [{"source": "accord.md", "page": None, "score": 0.71, "semantic": 0.7, "keyword": 0.77, "excerpt": "Quatre jours."}]
        documents = {"role": "system", "content": "[accord.md]\nQuatre jours.", "sources": sources}
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(Store, "DEFAULT_DOCS_DIR", Path(folder)), \
                mock.patch.object(Chatbot, "rag_message", return_value=documents) as rag:
            Path(folder, "accord.md").write_text("# Accord", encoding="utf-8")
            scope_url = f"{self.url}/api/documents/scope"
            self.assertEqual(client.put(scope_url, json={"sources": ["absent.md"]}).status_code, 422)
            self.assertEqual(client.put(scope_url, json={"types": ["exe"]}).status_code, 422)
            chosen = client.put(scope_url, json={"sources": ["accord.md"]}).json()["scope"]
            self.assertEqual(chosen, {"sources": ["accord.md"], "types": []})
            self.assertEqual(client.get(f"{self.url}/api/settings").json()["document_scope"], chosen)

            stream = events(self.chat(client, "Mariage ?", answer=("Quatre jours [accord.md].",)))
            self.assertEqual(rag.call_args.kwargs["scope"], chosen)
            self.assertEqual([data for name, data in stream if name == "sources"], [{"sources": sources}])
            conversation = stream[0][1]["id"]
            history = client.get(f"{self.url}/api/conversations/{conversation}/messages").json()["messages"]
            self.assertNotIn("sources", history[0])
            self.assertEqual(history[1]["sources"], sources)

            # [X2] A branch keeps the sources of the answers it copies.
            self.chat(client, "Et un Pacs ?", conversation_id=conversation, answer=("Pareil.",))
            FakeOllama.scripted = [["Pareil, quatre jours."]]
            branch = events(client.post(f"{self.url}/api/chat", json={"message": "Et le Pacs ?", "conversation_id": conversation,
                                                                       "branch_from": 2}))[0][1]["id"]
            self.assertEqual(client.get(f"{self.url}/api/conversations/{branch}/messages").json()["messages"][1]["sources"], sources)

            # Hidden with /settings sources off, but still kept with the answer.
            client.put(f"{self.url}/api/settings/sources", json={"value": "off"})
            stream = events(self.chat(client, "Encore ?", answer=("Oui.",)))
            self.assertEqual([name for name, _ in stream if name == "sources"], [])
            later = client.get(f"{self.url}/api/conversations/{stream[0][1]['id']}/messages").json()["messages"]
            self.assertEqual(later[1]["sources"], sources)
            client.put(f"{self.url}/api/settings/sources", json={"value": "on"})
            self.assertIsNone(client.put(scope_url, json={}).json()["scope"])

    def upload(self, client, name, content):
        return client.post(f"{self.url}/api/documents", params={"name": name}, data=content)

    def test_an_imported_document_is_saved_in_the_base_and_indexed(self):
        client = self.login()
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(Store, "DEFAULT_DOCS_DIR", Path(folder)), \
                mock.patch.object(Store, "embed_documents", side_effect=lambda texts: [[1.0, 0.0]] * len(texts)), \
                mock.patch.object(Documents, "invalidate_cache") as invalidate:
            response = self.upload(client, "accord télétravail.md", "# Télétravail\n\nDeux jours par semaine.".encode())
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["document"]["source"], "accord télétravail.md")
            self.assertEqual(response.json()["document"]["status"], "indexed")
            self.assertEqual(Path(folder, "accord télétravail.md").read_text("utf-8"), "# Télétravail\n\nDeux jours par semaine.")
            invalidate.assert_called_once()
            listed = client.get(f"{self.url}/api/documents").json()["documents"]
            self.assertEqual([(item["source"], item["status"]) for item in listed], [("accord télétravail.md", "indexed")])
            Path(folder, "accord télétravail.md").unlink()
            Store.index_directory(folder)  # its fake vectors must not reach the other tests' retrieval

    def test_hr_renames_and_deletes_a_document_without_embedding_it_again(self):
        from Memories.Auth import ROLE_EMPLOYEE
        from rag.Retriever import load_chunks
        create_user("ines", "ines@example.com", "pw", role=ROLE_EMPLOYEE)
        hr, employee = self.login(), self.login("ines@example.com")
        embed = mock.patch.object(Store, "embed_documents", side_effect=lambda texts: [[1.0, 0.0]] * len(texts))
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(Store, "DEFAULT_DOCS_DIR", Path(folder)), \
                embed as embedded, mock.patch.object(Documents, "invalidate_cache") as invalidate:
            self.assertEqual(self.upload(hr, "accord.md", "# Accord\n\nDeux jours.".encode()).status_code, 200)
            calls = embedded.call_count
            url = f"{self.url}/api/documents"
            self.assertEqual(employee.patch(f"{url}/accord.md", json={"name": "x.md"}).status_code, 403)
            self.assertEqual(employee.delete(f"{url}/accord.md").status_code, 403)
            self.assertEqual(hr.patch(f"{url}/accord.md", json={"name": "../x.md"}).status_code, 422)
            self.assertEqual(hr.patch(f"{url}/accord.md", json={"name": "x.exe"}).status_code, 422)
            self.assertEqual(hr.patch(f"{url}/absent.md", json={"name": "x.md"}).status_code, 404)

            renamed = hr.patch(f"{url}/accord.md", json={"name": "accord télétravail.md"})
            self.assertEqual(renamed.status_code, 200, renamed.text)
            self.assertEqual((renamed.json()["document"]["source"], renamed.json()["document"]["status"]),
                             ("accord télétravail.md", "indexed"))
            self.assertEqual(embedded.call_count, calls)  # same text: the vectors are kept
            self.assertEqual([chunk["source"] for chunk in load_chunks()[0]], ["accord télétravail.md"])
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), ["accord télétravail.md"])

            self.upload(hr, "autre.md", b"# Autre")
            self.assertEqual(hr.patch(f"{url}/autre.md", json={"name": "accord télétravail.md"}).status_code, 409)
            with mock.patch.object(Store, "embed_documents", return_value=None):  # Ollama down: deleting still works
                self.assertEqual(hr.delete(f"{url}/accord télétravail.md").json(), {"deleted": "accord télétravail.md"})
                self.assertEqual(hr.delete(f"{url}/accord télétravail.md").status_code, 404)
                hr.delete(f"{url}/autre.md")
            self.assertEqual(load_chunks()[0], [])
            self.assertEqual(list(Path(folder).iterdir()), [])
            self.assertGreaterEqual(invalidate.call_count, 3)

    def test_an_import_is_refused_when_the_file_cannot_be_a_document(self):
        client = self.login()
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(Store, "DEFAULT_DOCS_DIR", Path(folder)):
            for name in ("../evil.md", "sub/evil.md", ".hidden.md", "virus.exe", ""):
                self.assertEqual(self.upload(client, name, b"text").status_code, 422, name)
            self.assertEqual(self.upload(client, "empty.md", b"").json()["detail"], "The file is empty.")
            scanned = self.upload(client, "scan.pdf", b"not a pdf")
            self.assertEqual((scanned.status_code, scanned.json()["detail"][:30]), (422, "SENSAI could not read any text"))
            with mock.patch.object(Documents, "MAX_UPLOAD_BYTES", 10):
                self.assertEqual(self.upload(client, "big.md", b"x" * 11).status_code, 413)
            self.assertEqual(list(Path(folder).iterdir()), [])
            self.assertEqual(requests.post(f"{self.url}/api/documents", params={"name": "a.md"}, data=b"x").status_code, 401)

    def test_only_hr_accounts_add_documents_to_the_shared_base(self):
        from Memories.Auth import ROLE_EMPLOYEE
        create_user("eve", "eve@example.com", "pw", role=ROLE_EMPLOYEE)
        employee = self.login("eve@example.com")
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(Store, "DEFAULT_DOCS_DIR", Path(folder)), \
                mock.patch.object(Store, "index_directory") as index:
            refused = self.upload(employee, "accord.md", b"# Accord")
            self.assertEqual(refused.status_code, 403)
            self.assertIn("Only HR accounts", refused.json()["detail"])
            self.assertEqual(list(Path(folder).iterdir()), [])
            self.assertEqual(employee.get(f"{self.url}/api/documents").status_code, 200)
            ingest = employee.post(f"{self.url}/api/command", json={"text": "/ingest"}).json()
            self.assertIn("only HR accounts", ingest["output"])
            index.assert_not_called()

    def test_an_import_without_ollama_keeps_the_file_to_index_later(self):
        client = self.login()
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(Store, "DEFAULT_DOCS_DIR", Path(folder)), \
                mock.patch.object(Store, "embed_documents", return_value=None):
            response = self.upload(client, "conges.txt", b"Cinq semaines.")
            self.assertEqual(response.status_code, 503)
            self.assertIn("not indexed yet", response.json()["detail"])
            listed = client.get(f"{self.url}/api/documents").json()["documents"]
            self.assertEqual([(item["source"], item["status"]) for item in listed], [("conges.txt", "not_indexed")])

    def test_a_file_joined_to_a_chat_stays_in_that_chat(self):
        client = self.login()
        join = lambda name, content, conversation=None: client.post(
            f"{self.url}/api/attachments", params={"name": name, "conversation_id": conversation}, data=content)
        with mock.patch.object(Attachments, "embed_documents", side_effect=lambda texts: [[1.0, 0.0]] * len(texts)):
            first = join("contrat.md", "Congés : 25 jours.".encode())
            self.assertEqual(first.status_code, 200, first.text)
            conversation = first.json()["conversation"]
            self.assertEqual((conversation["title"], first.json()["attachment"]["chunks"]), ("contrat.md", 1))
            self.assertEqual(join("avenant.txt", b"Prime : 35 euros.", conversation["id"]).status_code, 200)
            messages = client.get(f"{self.url}/api/conversations/{conversation['id']}/messages").json()
            self.assertEqual([item["source"] for item in messages["attachments"]], ["contrat.md", "avenant.txt"])
            mine = client.get(f"{self.url}/api/attachments").json()["attachments"]
            self.assertEqual([(item["source"], item["conversation_id"], item["conversation_title"]) for item in mine],
                             [("avenant.txt", conversation["id"], "contrat.md"), ("contrat.md", conversation["id"], "contrat.md")])
            others = self.login(email="bob@example.com").get(f"{self.url}/api/attachments").json()["attachments"]
            self.assertNotIn(conversation["id"], [item["conversation_id"] for item in others])
            avenant = mine[0]["id"]
            self.assertEqual(self.login(email="bob@example.com").delete(f"{self.url}/api/attachments/{avenant}").status_code, 404)
            self.assertEqual(client.delete(f"{self.url}/api/attachments/{avenant}").json(), {"deleted": avenant})
            self.assertEqual(client.delete(f"{self.url}/api/attachments/{avenant}").status_code, 404)
            self.assertEqual([item["source"] for item in client.get(f"{self.url}/api/attachments").json()["attachments"]], ["contrat.md"])
            self.assertEqual(self.login(email="bob@example.com").post(
                f"{self.url}/api/attachments", params={"name": "x.md", "conversation_id": conversation["id"]}, data=b"x").status_code, 404)
            self.assertEqual(join("../x.md", b"x").status_code, 422)
            ids_before = {item["id"] for item in list_conversations("alice")}
            with self.assertLogs(level="WARNING"):
                self.assertEqual(join("scan.pdf", b"not a pdf").status_code, 422)
            self.assertEqual({item["id"] for item in list_conversations("alice")}, ids_before)
        with mock.patch.object(Attachments, "embed_documents", return_value=None):
            self.assertEqual(join("contrat.md", b"x", conversation["id"]).status_code, 503)

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
