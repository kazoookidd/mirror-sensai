"""Tests for rag.Retriever, the RAG step of the chat and /ingest."""

import contextlib
import io
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import Chatbot
import Commands
from Memories.Compression import estimate_tokens
from rag import Retriever

CHUNKS = [
    {"source": "loi_conge_mariage_pacs.md", "page": None, "chunk_index": 0,
     "text": "Le salarié a droit à 4 jours de congé pour son mariage."},
    {"source": "loi_teletravail.md", "page": None, "chunk_index": 0,
     "text": "Le télétravail est mis en place par accord collectif."},
    {"source": "syd_accord_nao_2026.pdf", "page": 4, "chunk_index": 3,
     "text": "Augmentation générale de 2 % au 1er janvier."},
]

MATRIX = np.array([[0.9, 0.436], [0.75, 0.661], [0.3, 0.954]], dtype=np.float32)
QUESTION_VECTOR = [1.0, 0.0]


def _index(chunks=CHUNKS, matrix=MATRIX):
    return mock.patch.object(Retriever, "load_chunks", return_value=(chunks, matrix))


def _embedding(vector=QUESTION_VECTOR):
    return mock.patch.object(Retriever, "embed_query", return_value=vector)


class RetrieveTests(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {"RAG_MIN_SCORE": "", "RAG_TOP_K": ""})
        env.start()
        self.addCleanup(env.stop)

    def test_relevant_chunks_come_best_first_with_their_score(self):
        with _index(), _embedding():
            found = Retriever.retrieve("congé mariage ?")
        self.assertEqual([c["source"] for c in found],
                         ["loi_conge_mariage_pacs.md", "loi_teletravail.md"])
        self.assertAlmostEqual(found[0]["score"], 0.9, places=2)

    def test_chunks_under_the_min_score_are_dropped(self):
        with _index(), _embedding():
            found = Retriever.retrieve("question")
        self.assertNotIn("syd_accord_nao_2026.pdf", [c["source"] for c in found])

    def test_off_topic_question_gets_nothing(self):
        with _index(), _embedding([0.0, -1.0]):
            self.assertEqual(Retriever.retrieve("recette de la pizza ?"), [])

    def test_top_k_and_min_score_come_from_env(self):
        with _index(), _embedding(), \
             mock.patch.dict(os.environ, {"RAG_TOP_K": "1", "RAG_MIN_SCORE": "0.1"}):
            found = Retriever.retrieve("question")
        self.assertEqual([c["source"] for c in found], ["loi_conge_mariage_pacs.md"])

    def test_scores_are_cosine_even_for_unnormalized_vectors(self):
        with _index(matrix=MATRIX * 7), _embedding([3.0, 0.0]):
            found = Retriever.retrieve("question")
        self.assertAlmostEqual(found[0]["score"], 0.9, places=2)

    def test_empty_index_does_not_call_ollama(self):
        empty = ([], np.empty((0, 0), dtype=np.float32))
        with mock.patch.object(Retriever, "load_chunks", return_value=empty), \
             _embedding() as embed:
            self.assertEqual(Retriever.retrieve("question"), [])
        embed.assert_not_called()

    def test_ollama_failure_gives_no_chunk(self):
        with _index(), _embedding(None):
            self.assertEqual(Retriever.retrieve("question"), [])

    def test_invalid_setting_warns_and_uses_the_default(self):
        with _index(), _embedding(), mock.patch.dict(os.environ, {"RAG_MIN_SCORE": "0,7"}), \
             self.assertLogs("rag.Retriever", logging.WARNING) as logs:
            found = Retriever.retrieve("question")
        self.assertIn("RAG_MIN_SCORE", logs.output[0])
        self.assertEqual(len(found), 2)

    def test_index_built_with_other_embeddings_gives_nothing(self):
        with _index(), _embedding([1.0, 0.0, 0.0]), \
             self.assertLogs("rag.Retriever", logging.WARNING) as logs:
            self.assertEqual(Retriever.retrieve("question"), [])
        self.assertIn("/ingest", logs.output[0])

    def test_zero_vector_is_ignored_without_warning(self):
        matrix = np.vstack([np.zeros(2, dtype=np.float32), MATRIX[0]])
        with _index(CHUNKS[:2], matrix), _embedding():
            found = Retriever.retrieve("question")
        self.assertEqual([c["source"] for c in found], ["loi_teletravail.md"])

    def test_question_is_embedded_on_the_chat_ollama_server(self):
        with _index(), _embedding() as embed:
            Retriever.retrieve("question", ollama_url="http://other:11434")
        embed.assert_called_once_with("question", "http://other:11434")


class DocumentsMessageTests(unittest.TestCase):
    def test_message_lists_sources_with_pages(self):
        message = Retriever.documents_message(CHUNKS, 10_000)
        self.assertEqual(message["role"], "system")
        self.assertIn("[loi_conge_mariage_pacs.md]\nLe salarié", message["content"])
        self.assertIn("[syd_accord_nao_2026.pdf, p. 4]\n", message["content"])

    def test_only_chunks_that_fit_are_added_best_first(self):
        one_chunk = f"{Retriever.CONTEXT_HEADER}\n\n{Retriever._format_chunk(CHUNKS[0])}"
        message = Retriever.documents_message(CHUNKS, estimate_tokens(one_chunk))
        self.assertEqual(message["content"], one_chunk)

    def test_message_never_exceeds_the_budget(self):
        for max_tokens in range(0, 200):
            message = Retriever.documents_message(CHUNKS, max_tokens)
            if message:
                self.assertLessEqual(estimate_tokens(message["content"]), max_tokens)

    def test_nothing_fits_or_nothing_found_gives_none(self):
        self.assertIsNone(Retriever.documents_message(CHUNKS, 5))
        self.assertIsNone(Retriever.documents_message([], 10_000))

    def test_no_room_for_a_chunk_skips_the_search(self):
        header = estimate_tokens(Retriever.CONTEXT_HEADER)
        with mock.patch.object(Retriever, "retrieve") as retrieve:
            self.assertIsNone(Retriever.rag_message("question", 0))
            self.assertIsNone(Retriever.rag_message("question", header))
        retrieve.assert_not_called()


class ChatTurnTests(unittest.TestCase):
    def setUp(self):
        self.session = Commands.Session(
            user_id="u", conversation_id=1, model="m", persona_id="p",
            personas={"p": {"system_prompt": "Tu es RH."}},
            ollama_url="http://x", search_motor="none", show_token_usage=False,
        )
        self.sent = []
        patches = [
            mock.patch.object(Chatbot, "build_context",
                              return_value=[{"role": "system", "content": "Tu es RH."}]),
            mock.patch.object(Chatbot, "call_ollama", side_effect=self._fake_ollama),
            mock.patch.object(Chatbot, "save_message"),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _fake_ollama(self, url, model, context, temperature):
        self.sent = list(context)
        return Chatbot.Reply(text="4 jours.")

    def test_documents_go_right_before_the_question_and_are_not_saved(self):
        documents = {"role": "system", "content": "[loi.md]\n4 jours."}
        with mock.patch.object(Chatbot, "rag_message", return_value=documents), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(Chatbot.chat_turn(self.session, "Congé mariage ?"))
        question = {"role": "user", "content": "Congé mariage ?"}
        self.assertEqual(self.sent[-2:], [documents, question])
        saved = [call.args[2] for call in Chatbot.save_message.call_args_list]
        self.assertEqual(saved, ["Congé mariage ?", "4 jours."])

    def test_rag_gets_only_the_room_left_under_the_token_limit(self):
        with mock.patch.object(Chatbot, "rag_message", return_value=None) as rag, \
             mock.patch.object(Chatbot, "get_budget", return_value=100), \
             contextlib.redirect_stdout(io.StringIO()):
            Chatbot.chat_turn(self.session, "Question ?")
        used = estimate_tokens("Tu es RH.") + estimate_tokens("Question ?")
        rag.assert_called_once_with("Question ?", 100 - used, ollama_url="http://x")
        self.assertEqual(len(self.sent), 2)


class IngestCommandTests(unittest.TestCase):
    def _run(self, text, stats):
        output = io.StringIO()
        with mock.patch.object(Commands, "index_directory", return_value=stats) as index, \
             contextlib.redirect_stdout(output):
            Commands.handle_command(None, text)
        return index, output.getvalue()

    def test_default_folder_and_summary(self):
        stats = {"indexed": 8, "unchanged": 0, "removed": 0, "chunks": 69, "failed": False}
        index, output = self._run("/ingest", stats)
        index.assert_called_once_with(Commands.DEFAULT_DOCS_DIR)
        self.assertIn("8 document(s) indexed (69 chunks)", output)

    def test_custom_folder_and_failure(self):
        stats = {"indexed": 0, "unchanged": 0, "removed": 0, "chunks": 0, "failed": True}
        with tempfile.TemporaryDirectory() as folder:
            index, output = self._run(f"/ingest {folder}", stats)
        index.assert_called_once_with(Path(folder))
        self.assertIn("Indexing stopped", output)

    def test_missing_folder_is_an_error_not_a_success(self):
        index, output = self._run("/ingest /no/such/folder", None)
        index.assert_not_called()
        self.assertIn("is not a folder", output)


if __name__ == "__main__":
    unittest.main()
