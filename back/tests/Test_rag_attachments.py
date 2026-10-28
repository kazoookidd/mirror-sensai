"""
Tests for the files joined to a conversation (rag/Attachments.py) and how the chat
turn uses them (Chatbot.add_documents, no semantic cache).

No real Ollama: the embeddings are faked, the database is a temporary file.

Usage (from the project root):
    python back/tests/Test_rag_attachments.py
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import Chatbot
from Agents import Engine
from Agents.Router import refers_to_attachments
from Memories import Database
from Memories.Auth import create_user
from Memories.Branches import create_branch, delete_family
from Memories.Compression import estimate_tokens
from Memories.Conversations import create_conversation
from Memories.Memory import save_message
from rag import Attachments

# Each chunk text says which axis it points to, so the fake embeddings know which passage is closest.
AXES = {"conges": [1.0, 0.0, 0.0], "salaire": [0.0, 1.0, 0.0], "velo": [0.0, 0.0, 1.0]}


def fake_vector(text: str) -> list[float]:
    return next((vector for word, vector in AXES.items() if word in text.lower()), [0.3, 0.3, 0.3])


class AttachmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for patch in (mock.patch.object(Database, "DB_PATH", os.path.join(self.tmp.name, "t.db")),
                      mock.patch.object(Attachments, "embed_documents", side_effect=lambda texts: [fake_vector(t) for t in texts]),
                      mock.patch.object(Attachments, "embed_query", side_effect=lambda text, url=None: fake_vector(text)),
                      mock.patch.object(Attachments, "embed_model", return_value="fake")):
            patch.start()
            self.addCleanup(patch.stop)
        Database.init_db()
        create_user("alice", "alice@example.com", "pw")
        self.conversation = create_conversation("alice", "Contrat")

    def file(self, name: str, text: str) -> Path:
        path = Path(self.tmp.name, name)
        path.write_text(text, encoding="utf-8")
        return path

    def join(self, name: str, *paragraphs: str, conversation=None) -> dict:
        return Attachments.attach(conversation or self.conversation, self.file(name, "\n\n".join(paragraphs)), name)

    def test_a_joined_file_is_chunked_and_listed_for_its_conversation_only(self):
        attachment = self.join("contrat.md", "Congés : 25 jours.")
        self.assertEqual((attachment["source"], attachment["chunks"]), ("contrat.md", 1))
        self.assertEqual([item["source"] for item in Attachments.list_attachments(self.conversation)], ["contrat.md"])
        other = create_conversation("alice", "Autre")
        self.assertEqual(Attachments.list_attachments(other), [])
        self.assertIsNone(Attachments.attachments_message(other, "congés ?", 1000))
        self.assertFalse(Attachments.has_attachments(other))
        self.assertFalse(Attachments.has_attachments(None))

    def test_a_small_file_goes_in_whole_in_file_order(self):
        self.join("note.md", "Le vélo est remboursé.", "Les congés sont de 25 jours.")
        with mock.patch.object(Attachments, "chunk_pages", side_effect=lambda pages: [
                {"page": None, "chunk_index": i, "text": text} for i, text in enumerate(pages[0]["text"].split("\n\n"))]):
            self.join("note.md", "Le vélo est remboursé.", "Les congés sont de 25 jours.")
        message = Attachments.attachments_message(self.conversation, "Combien de congés ?", 1000)["content"]
        self.assertTrue(message.startswith(Attachments.CONTEXT_HEADER))
        self.assertLess(message.index("vélo"), message.index("congés sont"))
        self.assertEqual(len(Attachments.list_attachments(self.conversation)), 1)  # same name: replaced

    def test_a_big_file_gives_its_closest_passages_within_the_room(self):
        with mock.patch.object(Attachments, "chunk_pages", side_effect=lambda pages: [
                {"page": i + 1, "chunk_index": i, "text": text} for i, text in enumerate(pages[0]["text"].split("\n\n"))]):
            self.join("accord.md", "Salaire : grille A. " * 20, "Congés : 25 jours. " * 20, "Vélo : 35 euros. " * 20)
        one_passage = estimate_tokens(Attachments.CONTEXT_HEADER) + estimate_tokens("\n\n[accord.md, p. 2]\n" + "Congés : 25 jours. " * 20) + 5
        message = Attachments.attachments_message(self.conversation, "Combien de congés ?", one_passage)["content"]
        self.assertIn("[accord.md, p. 2]", message)
        self.assertNotIn("Salaire", message)
        self.assertNotIn("Vélo", message)
        self.assertIsNone(Attachments.attachments_message(self.conversation, "congés", 10))

    def test_unreadable_files_and_ollama_errors_are_refused_and_nothing_is_kept(self):
        with self.assertRaisesRegex(ValueError, "could not read any text"), self.assertLogs(level="WARNING"):
            Attachments.attach(self.conversation, self.file("scan.pdf", "not a pdf"), "scan.pdf")
        with mock.patch.object(Attachments, "embed_documents", return_value=None), \
                self.assertRaisesRegex(ConnectionError, "Ollama did not answer"):
            self.join("contrat.md", "Congés : 25 jours.")
        self.assertEqual(Attachments.list_attachments(self.conversation), [])

    def test_branches_share_the_files_and_deleting_the_conversation_deletes_them(self):
        save_message(self.conversation, "user", "Q1")
        save_message(self.conversation, "assistant", "A1")
        self.join("contrat.md", "Congés : 25 jours.")
        branch = create_branch(self.conversation, 0)
        self.assertEqual([item["source"] for item in Attachments.list_attachments(branch)], ["contrat.md"])
        self.assertIn("25 jours", Attachments.attachments_message(branch, "congés", 1000)["content"])
        delete_family(self.conversation)
        conn = Database.get_connection()
        left = conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0], conn.execute("SELECT COUNT(*) FROM attachment_chunks").fetchone()[0]
        conn.close()
        self.assertEqual(left, (0, 0))

    def test_the_chat_turn_puts_the_files_before_the_hr_documents_and_skips_the_cache(self):
        self.join("contrat.md", "Congés : 25 jours.")
        context = [{"role": "system", "content": "s"}]
        with mock.patch.object(Chatbot, "rag_message", return_value={"role": "system", "content": "docs RH"}) as rag:
            Chatbot.add_documents(context, "Combien de congés ?", "http://x", self.conversation)
        self.assertEqual([m["content"][:30] for m in context[1:]], [Attachments.CONTEXT_HEADER[:30], "docs RH"])
        self.assertLess(rag.call_args.args[1], Chatbot.get_budget())
        session = mock.MagicMock(conversation_id=self.conversation)
        with mock.patch.object(Chatbot, "check_cache") as check, \
                mock.patch.object(Chatbot, "build_context", side_effect=RuntimeError("stop here")), \
                self.assertRaises(RuntimeError):
            Chatbot.chat_turn(session, "Combien de congés ?")
        check.assert_not_called()

    def test_a_question_about_the_joined_file_is_answered_without_tools(self):
        self.assertTrue(all(map(refers_to_attachments, ["Résume le fichier joint", "Que dit ce document ?", "Summarize the attached file"])))
        self.assertFalse(any(map(refers_to_attachments, ["Quelle est la durée légale du préavis ?", "Cherche sur internet", "Bonjour"])))
        session = mock.MagicMock(conversation_id=self.conversation, tools_enabled=True, model="m")
        session.tools.names.return_value = ["read_webpage"]
        self.assertTrue(Engine.tools_available(session, "Résume le fichier joint"))  # nothing joined yet
        self.join("contrat.md", "Congés : 25 jours.")
        self.assertFalse(Engine.tools_available(session, "Résume le fichier joint"))
        self.assertTrue(Engine.tools_available(session, "Quelle est la loi sur le télétravail ?"))


if __name__ == "__main__":
    unittest.main()
