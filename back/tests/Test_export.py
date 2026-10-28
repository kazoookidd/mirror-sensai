"""
Tests for [X3]: exporting a conversation (Export/Formats.py, /export in the CLI)
and its public links (Export/Shares.py). The web routes are tested in Test_web.py.

No Ollama needed: the database is a temporary file.

Usage (from the project root):
    python back/tests/Test_export.py
"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import Commands
from Export.Formats import export
from Export.Shares import active_share, create_share, find_share, revoke_shares
from Memories import Database
from Memories.Auth import create_user
from Memories.Branches import create_branch, delete_family
from Memories.Conversations import create_conversation
from Memories.Memory import save_message

ANSWER = "## Règles\nVous avez **25 jours** ouvrés.\n\n- Premier point\n1. Un\n\nEmoji 😀 et 中文."


class TempDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patch = mock.patch.object(Database, "DB_PATH", os.path.join(self.tmp.name, "t.db"))
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)
        Database.init_db()
        create_user("alice", "alice@example.com", "pw")

    def conversation(self, *contents, title="Congés payés") -> int:
        conversation_id = create_conversation("alice", title)
        for index, content in enumerate(contents):
            save_message(conversation_id, "user" if index % 2 == 0 else "assistant", content)
        return conversation_id


class FormatTests(TempDatabase):
    def test_markdown_has_the_title_and_each_author(self):
        conversation = self.conversation("Combien de jours ?", ANSWER)
        name, media_type, content = export(conversation, "md")
        text = content.decode("utf-8")
        self.assertEqual(name, f"sensai-{conversation}-conges-payes.md")
        self.assertTrue(media_type.startswith("text/markdown"))
        self.assertTrue(text.startswith("# Congés payés\n\n_Exported from SENSAI on "))
        self.assertIn("2 messages._", text)
        self.assertIn("## You\n\nCombien de jours ?\n\n## SENSAI\n\n## Règles", text)

    def test_json_keeps_every_message_with_its_date(self):
        conversation = self.conversation("Q1", "A1")
        doc = json.loads(export(conversation, "json")[2])
        self.assertEqual(doc["title"], "Congés payés")
        self.assertEqual([(m["role"], m["content"]) for m in doc["messages"]], [("user", "Q1"), ("assistant", "A1")])
        self.assertRegex(doc["messages"][0]["created_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertRegex(doc["exported_at"], r"Z$")

    def test_pdf_is_a_pdf_even_with_characters_the_font_lacks(self):
        conversation = self.conversation("Combien de jours ?", ANSWER)
        name, media_type, content = export(conversation, "pdf")
        self.assertEqual((name[-4:], media_type), (".pdf", "application/pdf"))
        self.assertTrue(content.startswith(b"%PDF-"))
        self.assertTrue(content.rstrip().endswith(b"%%EOF"))

    def test_a_branch_exports_the_version_shown_under_the_root_title(self):
        root = self.conversation("Q1", "A1", "Q2", "A2")
        branch = create_branch(root, 2)
        save_message(branch, "user", "Q2 bis")
        save_message(branch, "assistant", "A2 bis")
        doc = json.loads(export(branch, "json")[2])
        self.assertEqual(doc["title"], "Congés payés")
        self.assertEqual([m["content"] for m in doc["messages"]], ["Q1", "A1", "Q2 bis", "A2 bis"])

    def test_unknown_format_and_empty_chat_are_refused(self):
        with self.assertRaisesRegex(ValueError, "Unknown format 'xml'"):
            export(self.conversation("Q", "A"), "xml")
        with self.assertRaisesRegex(ValueError, "no messages yet"):
            export(self.conversation(), "md")

    def test_a_title_without_letters_still_gives_a_file_name(self):
        self.assertEqual(export(self.conversation("Q", "A", title="???"), "md")[0][-8:], "-chat.md")


class ShareTests(TempDatabase):
    def test_a_link_is_a_frozen_copy_that_expires_in_seven_days(self):
        conversation = self.conversation("Q1", "A1")
        share = create_share(conversation)
        save_message(conversation, "user", "Q2")
        found = find_share(share["token"])
        self.assertEqual(found["messages"], [{"role": "user", "content": "Q1"}, {"role": "assistant", "content": "A1"}])
        self.assertEqual((found["title"], found["expired"]), ("Congés payés", False))
        self.assertGreaterEqual(len(share["token"]), 32)
        conn = Database.get_connection()
        days = conn.execute("SELECT julianday(expires_at) - julianday(created_at) FROM shares").fetchone()[0]
        conn.close()
        self.assertAlmostEqual(days, 7, places=3)
        self.assertEqual(active_share(conversation), share)

    def test_sharing_again_replaces_the_previous_link(self):
        conversation = self.conversation("Q1", "A1")
        first = create_share(conversation)
        second = create_share(conversation)
        self.assertNotEqual(first["token"], second["token"])
        self.assertIsNone(find_share(first["token"]))
        self.assertIsNotNone(find_share(second["token"]))

    def test_turning_off_expiring_or_deleting_ends_the_link(self):
        conversation = self.conversation("Q1", "A1")
        token = create_share(conversation)["token"]
        self.assertEqual(revoke_shares(conversation), 1)
        self.assertIsNone(find_share(token))
        self.assertIsNone(active_share(conversation))

        token = create_share(conversation)["token"]
        conn = Database.get_connection()
        conn.execute("UPDATE shares SET expires_at = datetime('now', '-1 minute')")
        conn.commit()
        conn.close()
        self.assertTrue(find_share(token)["expired"])
        self.assertIsNone(active_share(conversation))

        branch = create_branch(conversation, 0)
        save_message(branch, "user", "Q1 bis")
        token = create_share(branch)["token"]
        delete_family(conversation)
        self.assertIsNone(find_share(token))

    def test_an_empty_chat_cannot_be_shared(self):
        with self.assertRaisesRegex(ValueError, "no messages yet"):
            create_share(self.conversation())


class CliTests(TempDatabase):
    def run_command(self, session, text) -> str:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertTrue(Commands.handle_command(session, text))
        return output.getvalue()

    def test_export_writes_the_file_in_the_exports_folder(self):
        session = mock.Mock(conversation_id=self.conversation("Q1", "A1"))
        folder = Path(self.tmp.name, "exports")
        with mock.patch.object(Commands, "EXPORTS_DIR", folder):
            printed = self.run_command(session, "/export JSON")
            self.assertIn(f"Conversation saved to {folder}", printed)
            self.assertEqual(json.loads(next(folder.glob("*.json")).read_text("utf-8"))["messages"][1]["content"], "A1")
            self.run_command(session, "/export")
            self.assertEqual(len(list(folder.glob("*.md"))), 1)
            self.assertIn("Error: Unknown format 'xml'", self.run_command(session, "/export xml"))
        self.assertIn("/export [md|json|pdf]", Commands.HELP_TEXT)


if __name__ == "__main__":
    unittest.main()
