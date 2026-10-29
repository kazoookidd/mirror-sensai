"""
Tests for the user's profile [M1] (Memories/Profile.py): storage, checks, the
text added to the system prompt, /profile in the CLI, and its use in a chat
turn. No real Ollama: a fake server records what the model receives.

Usage (from the project root):
    python back/tests/Test_profile.py
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

from Cache import Chat as CacheChat
from Chatbot import chat_turn
from Commands import Session, handle_command
from Memories import Compression, Database
from Memories.Auth import create_user
from Memories.Conversations import create_conversation
from Memories.Profile import (PROMPT_HEADER, clean_profile, context_text, empty_profile, find_field,
                              get_profile, save_profile, with_profile)
from Tools.privacy import identifiers, redact

SOPHIE = {"name": "Sophie Martin", "role": "Consultante", "department": "Engineering",
          "language": "French", "tone": "concise", "instructions": "Cite toujours l'article."}


class Fake(BaseHTTPRequestHandler):
    received: list = []

    def do_POST(self):
        type(self).received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200); self.send_header("Content-Type", "application/x-ndjson"); self.end_headers()
        self.wfile.write((json.dumps({"message": {"role": "assistant", "content": "Réponse."}, "done": False})
                          + "\n").encode())
        self.wfile.write((json.dumps({"message": {"role": "assistant", "content": ""}, "done": True,
                                      "prompt_eval_count": 20, "eval_count": 7}) + "\n").encode())

    def log_message(self, *a):
        pass


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patch = mock.patch.object(Database, "DB_PATH", os.path.join(self.tmp.name, "t.db"))
        patch.start(); self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)
        Database.init_db()
        create_user("sophie", "sophie@example.com", "pw")
        create_user("marc", "marc@example.com", "pw")


class TestRoles(DatabaseTest):
    def test_cli_accounts_are_hr_and_web_ones_employee(self):
        from Memories.Auth import ROLE_EMPLOYEE, ROLE_HR, get_or_create_user, role_of
        get_or_create_user("rh2", "pw", email="rh2@example.com")  # the CLI sign-up
        create_user("emp", "emp@example.com", "pw", role=ROLE_EMPLOYEE)
        self.assertEqual((role_of("rh2"), role_of("emp"), role_of("nobody")), (ROLE_HR, ROLE_EMPLOYEE, None))
        with self.assertRaises(ValueError):
            create_user("x1", "x1@example.com", "pw", role="admin")

    def test_accounts_made_before_roles_existed_become_hr(self):
        import sqlite3
        from Memories.Auth import role_of
        path = os.path.join(self.tmp.name, "old.db")
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE users (user_id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, "
                     "password_hash TEXT NOT NULL, salt TEXT NOT NULL, created_at TEXT)")
        conn.execute("INSERT INTO users VALUES ('old', 'old@example.com', 'h', 's', NULL)")
        conn.commit(); conn.close()
        with mock.patch.object(Database, "DB_PATH", path):
            Database.init_db()
            Database.init_db()  # safe to run again
            self.assertEqual(role_of("old"), "hr")


class TestProfileStore(DatabaseTest):
    def test_a_new_account_has_an_empty_profile(self):
        self.assertEqual(get_profile("sophie"), empty_profile())

    def test_a_saved_profile_is_found_again_and_belongs_to_its_user(self):
        save_profile("sophie", SOPHIE)
        self.assertEqual(get_profile("sophie"), SOPHIE)
        self.assertEqual(get_profile("marc"), empty_profile())

    def test_saving_again_replaces_the_profile(self):
        save_profile("sophie", SOPHIE)
        save_profile("sophie", {"role": "Manager"})
        self.assertEqual(get_profile("sophie"), {**empty_profile(), "role": "Manager"})

    def test_a_bad_value_raises_and_keeps_the_saved_profile(self):
        save_profile("sophie", SOPHIE)
        with self.assertRaises(ValueError):
            save_profile("sophie", {**SOPHIE, "tone": "funny"})
        self.assertEqual(get_profile("sophie"), SOPHIE)


class TestChecks(unittest.TestCase):
    def test_values_are_tidied(self):
        profile, error = clean_profile({"name": "  Sophie   Martin ", "tone": "Detailed",
                                        "instructions": "  ligne 1  \n\n  ligne   2 "})
        self.assertIsNone(error)
        self.assertEqual((profile["name"], profile["tone"]), ("Sophie Martin", "detailed"))
        self.assertEqual(profile["instructions"], "ligne 1\n\nligne 2")

    def test_bad_values_are_refused_with_a_clear_message(self):
        cases = [({"tone": "funny"}, "tone must be one of"),
                 ({"instructions": "x" * 1001}, "too long"),
                 ({"salary": "3000"}, "Unknown profile field"),
                 ({"name": 42}, "must be text")]
        for values, message in cases:
            profile, error = clean_profile(values)
            self.assertIn(message, error or "", values)

    def test_fields_have_french_and_english_names(self):
        for name, field in (("poste", "role"), ("job", "role"), ("Service", "department"),
                            ("langue", "language"), ("ton", "tone"), ("full_name", "name")):
            self.assertEqual(find_field(name).name, field, name)
        self.assertIsNone(find_field("salary"))


class TestPromptText(unittest.TestCase):
    def test_the_text_lists_the_filled_fields_then_the_instructions(self):
        self.assertEqual(context_text(SOPHIE),
                         "[profile]\nname: Sophie Martin\njob: Consultante\ndepartment: Engineering\n"
                         "language: French\ntone: concise\n\n[instructions]\nCite toujours l'article.")
        self.assertEqual(context_text({**empty_profile(), "tone": "detailed"}), "[profile]\ntone: detailed")

    def test_an_empty_profile_changes_nothing(self):
        self.assertEqual(context_text(empty_profile()), "")
        self.assertEqual(with_profile("PROMPT", empty_profile()), "PROMPT")
        self.assertEqual(with_profile("PROMPT", None), "PROMPT")

    def test_the_profile_comes_after_the_persona_prompt(self):
        prompt = with_profile("PROMPT", SOPHIE)
        self.assertTrue(prompt.startswith(f"PROMPT\n\n{PROMPT_HEADER}\n[profile]"))


class ChatTest(DatabaseTest):
    def setUp(self):
        super().setUp()
        self.server = HTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        Fake.received = []
        for patch in (mock.patch.object(Compression, "DEFAULT_BUDGET", 4000),
                      mock.patch.object(CacheChat, "ENABLED", False)):
            patch.start(); self.addCleanup(patch.stop)

    def session(self, persona="default"):
        personas = {pid: {"id": pid, "name": pid, "description": "", "system_prompt": f"You are {pid}."}
                    for pid in ("default", "hr_senior")}
        return Session(user_id="sophie", conversation_id=create_conversation("sophie", "t"), model="m",
                       persona_id=persona, personas=personas,
                       ollama_url=f"http://127.0.0.1:{self.server.server_port}", search_motor="tavily")

    def system_sent(self) -> str:
        return Fake.received[-1]["messages"][0]["content"]

    def turn(self, session, text="Combien de jours pour un mariage ?"):
        with redirect_stdout(io.StringIO()):
            return chat_turn(session, text)

    def command(self, session, text) -> str:
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertTrue(handle_command(session, text))
        return buf.getvalue()


class TestInjection(ChatTest):
    def test_the_model_gets_the_profile_in_its_system_message(self):
        save_profile("sophie", SOPHIE)
        self.assertTrue(self.turn(self.session()))
        system = self.system_sent()
        self.assertTrue(system.startswith("You are default."))
        self.assertIn("job: Consultante", system)
        self.assertIn("Cite toujours l'article.", system)

    def test_without_profile_the_system_message_is_the_persona_prompt(self):
        self.turn(self.session())
        self.assertTrue(self.system_sent().startswith("You are default.\n\nToday is "))  # the date, no profile
        self.assertNotIn("[profile]", self.system_sent())

    def test_a_change_applies_to_the_next_answer_without_restarting(self):
        session = self.session()
        self.turn(session)
        save_profile("sophie", {"tone": "detailed"})  # e.g. from the web page
        self.turn(session)
        self.assertIn("tone: detailed", self.system_sent())

    def test_switching_persona_keeps_the_profile(self):
        save_profile("sophie", SOPHIE)
        session = self.session()
        self.command(session, "/persona hr_senior")
        self.turn(session)
        self.assertTrue(self.system_sent().startswith("You are hr_senior."))
        self.assertIn("name: Sophie Martin", self.system_sent())

    def test_the_cache_fingerprint_follows_the_profile(self):
        session = self.session()
        with mock.patch.object(CacheChat, "ENABLED", True), \
                mock.patch.object(CacheChat.Policy, "may_serve", return_value=False):
            before = CacheChat.check(session, "q").fp
            session.profile = {**empty_profile(), "language": "English"}
            after = CacheChat.check(session, "q").fp
        self.assertNotEqual(before, after)


class TestCommand(ChatTest):
    def test_profile_shows_every_field_and_how_to_change_them(self):
        out = self.command(self.session(), "/profile")
        for name in ("name", "role", "department", "language", "tone", "instructions"):
            self.assertIn(name, out)
        self.assertIn("(not set)", out)
        self.assertIn("/profile <field> <value>", out)

    def test_a_field_is_saved_and_used_by_the_next_answer(self):
        session = self.session()
        out = self.command(session, "/profile poste Consultante en mission")
        self.assertIn("role set to \"Consultante en mission\"", out)
        self.assertEqual(get_profile("sophie")["role"], "Consultante en mission")
        self.turn(session)
        self.assertIn("job: Consultante en mission", self.system_sent())

    def test_other_fields_are_kept(self):
        save_profile("sophie", SOPHIE)
        session = self.session()
        self.command(session, "/profile tone detailed")
        self.assertEqual(get_profile("sophie"), {**SOPHIE, "tone": "detailed"})

    def test_a_field_or_the_whole_profile_can_be_emptied(self):
        save_profile("sophie", SOPHIE)
        session = self.session()
        self.assertIn("language emptied", self.command(session, "/profile language clear"))
        self.assertEqual(get_profile("sophie")["language"], "")
        self.assertIn("Profile emptied", self.command(session, "/profile clear"))
        self.assertEqual(get_profile("sophie"), empty_profile())

    def test_a_bad_value_or_field_changes_nothing(self):
        save_profile("sophie", SOPHIE)
        session = self.session()
        out = self.command(session, "/profile tone funny")
        self.assertIn("Error: tone must be one of: concise, detailed", out)
        self.assertIn("unchanged", out)
        self.assertIn("unknown profile field 'salary'", self.command(session, "/profile salary 3000"))
        self.assertEqual(get_profile("sophie"), SOPHIE)

    def test_one_field_can_be_shown(self):
        save_profile("sophie", SOPHIE)
        session = self.session()
        session.profile = get_profile("sophie")
        self.assertEqual(self.command(session, "/profile ton").strip(), "tone: concise")

    def test_the_account_role_is_shown_and_cannot_be_set(self):
        session = self.session()
        session.account_role = "employee"
        self.assertIn("account       Employee (set when the account was created", self.command(session, "/profile"))
        self.assertIn("unknown profile field 'account'", self.command(session, "/profile account hr"))

    def test_help_mentions_profile(self):
        self.assertIn("/profile", self.command(self.session(), "/help"))


class TestPrivacy(unittest.TestCase):
    def test_the_name_of_the_profile_is_never_sent_to_a_search_engine(self):
        known = identifiers("u42", None, "Sophie Martin")
        clean, found = redact("congé mariage Sophie Martin durée", known)
        self.assertEqual(clean, "congé mariage durée")
        self.assertEqual(found, ["your name or user id"])


if __name__ == "__main__":
    unittest.main()
