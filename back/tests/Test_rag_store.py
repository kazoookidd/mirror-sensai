"""Tests for rag.Embeddings and rag.Store, with a fake Ollama."""

import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import numpy as np
import requests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from rag import Embeddings
from rag.Store import index_directory, load_chunks

FAKE_DIM = 4

class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload

class _FakeOllama:
    """Fake requests.post for /api/embed: same text, same vector."""
    def __init__(self):
        self.calls = []

    def __call__(self, url, json, timeout):
        self.calls.append(json)
        vectors = [[len(text) / 7, (sum(map(ord, text)) % 97) / 3, 0.1, i / 9]
                   for i, text in enumerate(json["input"])]
        return _FakeResponse({"embeddings": vectors})

    def embedded_texts(self):
        return [text for call in self.calls for text in call["input"]]

class EmbeddingsTests(unittest.TestCase):
    def setUp(self):
        self.fake = _FakeOllama()
        patcher = mock.patch.object(Embeddings.requests, "post", self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_documents_and_queries_get_their_nomic_prefix(self):
        Embeddings.embed_documents(["contrat"])
        Embeddings.embed_query("congés ?")
        self.assertEqual(self.fake.embedded_texts(),
                         ["search_document: contrat", "search_query: congés ?"])

    def test_large_inputs_are_batched_in_order(self):
        texts = [f"chunk {i}" for i in range(Embeddings.BATCH_SIZE * 2 + 5)]
        vectors = Embeddings.embed_documents(texts)
        self.assertEqual(len(self.fake.calls), 3)
        self.assertEqual(len(vectors), len(texts))
        self.assertEqual(self.fake.embedded_texts(),
                         [Embeddings.DOCUMENT_PREFIX + t for t in texts])

    def test_model_comes_from_env_at_call_time(self):
        with mock.patch.dict(os.environ, {"RAG_EMBED_MODEL": "other-embed"}):
            Embeddings.embed_query("x")
        with mock.patch.dict(os.environ, {"RAG_EMBED_MODEL": ""}):
            Embeddings.embed_query("x")
        self.assertEqual([c["model"] for c in self.fake.calls],
                         ["other-embed", Embeddings.DEFAULT_EMBED_MODEL])

    def test_unreachable_ollama_returns_none_with_warning(self):
        down = mock.Mock(side_effect=requests.exceptions.ConnectionError())
        with mock.patch.object(Embeddings.requests, "post", down), \
             self.assertLogs("rag.Embeddings", logging.WARNING) as logs:
            self.assertIsNone(Embeddings.embed_query("x"))
        self.assertIn("cannot connect to Ollama", logs.output[0])

    def test_wrong_number_of_vectors_returns_none(self):
        short = mock.Mock(return_value=_FakeResponse({"embeddings": []}))
        with mock.patch.object(Embeddings.requests, "post", short), \
             self.assertLogs("rag.Embeddings", logging.WARNING):
            self.assertIsNone(Embeddings.embed_documents(["a", "b"]))

class StoreTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.db = str(self.root / "test.db")
        self.docs = self.root / "docs"
        self.docs.mkdir()
        conges = "Le salarié a droit à 25 jours de congés payés."
        mariage = "# Mariage\n\nQuatre jours de congé pour un mariage."
        (self.docs / "conges.txt").write_text(conges, encoding="utf-8")
        (self.docs / "mariage.md").write_text(mariage, encoding="utf-8")

        self.fake = _FakeOllama()
        patcher = mock.patch.object(Embeddings.requests, "post", self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {"RAG_EMBED_MODEL": "fake-embed"})
        env.start()
        self.addCleanup(env.stop)

    def _index(self, folder=None):
        if not folder:
            folder = self.docs
        return index_directory(folder, db_path=self.db)

    def test_chunks_and_vectors_round_trip(self):
        stats = self._index()
        chunks, matrix = load_chunks(self.db)
        self.assertEqual((stats["indexed"], stats["chunks"]), (2, 2))
        self.assertEqual(matrix.shape, (2, FAKE_DIM))
        self.assertEqual(matrix.dtype, np.float32)
        self.assertEqual({c["source"] for c in chunks}, {"conges.txt", "mariage.md"})
        for chunk, row in zip(chunks, matrix):
            sent = {"input": [Embeddings.DOCUMENT_PREFIX + chunk["text"]]}
            expected = self.fake(None, sent, None).json()["embeddings"][0]
            np.testing.assert_array_equal(row, np.asarray(expected, dtype=np.float32))

    def test_unchanged_files_are_not_embedded_again(self):
        self._index()
        calls = len(self.fake.calls)
        stats = self._index()
        self.assertEqual((stats["indexed"], stats["unchanged"]), (0, 2))
        self.assertEqual(len(self.fake.calls), calls)

    def test_modified_file_replaces_its_old_chunks(self):
        self._index()
        (self.docs / "conges.txt").write_text("Trente jours de congés.", encoding="utf-8")
        stats = self._index()
        chunks, matrix = load_chunks(self.db)
        self.assertEqual((stats["indexed"], stats["unchanged"]), (1, 1))
        self.assertEqual(len(chunks), 2)
        self.assertEqual(matrix.shape[0], 2)
        self.assertIn("Trente", next(c["text"] for c in chunks if c["source"] == "conges.txt"))

    def test_deleted_file_loses_its_chunks(self):
        self._index()
        (self.docs / "mariage.md").unlink()
        stats = self._index()
        chunks, _ = load_chunks(self.db)
        self.assertEqual(stats["removed"], 1)
        self.assertEqual([c["source"] for c in chunks], ["conges.txt"])

    def test_unreadable_file_keeps_its_previous_chunks(self):
        self._index()
        (self.docs / "conges.txt").write_bytes(b"\xff\xfe invalid utf-8")
        (self.docs / "mariage.md").write_text("", encoding="utf-8")
        with self.assertLogs("rag", logging.WARNING) as logs:
            stats = self._index()
        chunks, _ = load_chunks(self.db)
        self.assertEqual((stats["indexed"], stats["removed"]), (0, 0))
        self.assertEqual(len(chunks), 2)
        self.assertIn("25 jours", " ".join(c["text"] for c in chunks))
        self.assertTrue(any("keeping its previous chunks" in line for line in logs.output))

    def test_unchanged_files_are_not_parsed_again(self):
        self._index()
        with mock.patch("rag.Store.load_document") as load:
            self._index()
        load.assert_not_called()

    def test_changing_embed_model_reindexes_everything(self):
        self._index()
        with mock.patch.dict(os.environ, {"RAG_EMBED_MODEL": "new-embed"}):
            stats = self._index()
            chunks, _ = load_chunks(self.db)
        self.assertEqual(stats["indexed"], 2)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(self.fake.calls[-1]["model"], "new-embed")

    def test_ollama_failure_keeps_the_existing_index(self):
        self._index()
        (self.docs / "conges.txt").write_text("Version modifiée.", encoding="utf-8")
        (self.docs / "mariage.md").unlink()
        down = mock.Mock(side_effect=requests.exceptions.ConnectionError())
        with mock.patch.object(Embeddings.requests, "post", down), \
             self.assertLogs("rag", logging.WARNING):
            stats = self._index()
        chunks, _ = load_chunks(self.db)
        self.assertTrue(stats["failed"])
        self.assertEqual(stats["removed"], 0)
        self.assertEqual(len(chunks), 2)
        self.assertNotIn("modifiée", " ".join(c["text"] for c in chunks))

    def test_missing_folder_removes_nothing(self):
        self._index()
        with self.assertLogs("rag.Store", logging.WARNING):
            stats = self._index(self.root / "nope")
        self.assertEqual(stats["indexed"] + stats["removed"], 0)
        self.assertEqual(len(load_chunks(self.db)[0]), 2)

    def test_two_folders_with_same_file_names_coexist(self):
        other = self.root / "other"
        other.mkdir()
        (other / "conges.txt").write_text("Autre entreprise : 30 jours.", encoding="utf-8")
        self._index()
        self._index(other)
        chunks, _ = load_chunks(self.db)
        self.assertEqual([c["source"] for c in chunks].count("conges.txt"), 2)

    def test_empty_database_gives_empty_matrix(self):
        chunks, matrix = load_chunks(self.db)
        self.assertEqual((chunks, matrix.shape[0]), ([], 0))

if __name__ == "__main__":
    unittest.main()
