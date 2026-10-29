"""
Tests for the semantic cache (A6): the cache itself, the policy that decides
what may be served or stored, and the chat integration.

No real Ollama: a fake server answers /api/embed with a tiny hashed
bag-of-words vector (questions that share words are close) and /api/chat with
scripted answers. The database is a temporary file.

Usage (from the project root):
    python back/tests/Test_cache.py
"""

import io
import json
import math
import os
import sys
import tempfile
import threading
import unittest
import zlib
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Cache import Chat, Policy
from Cache.SemanticCache import EmbeddingUnavailable, SemanticCache, fingerprint
from Chatbot import chat_turn
from Commands import Session, handle_command
from Memories import Compression, Database
from Memories.Auth import get_or_create_user
from Memories.Conversations import create_conversation
from Memories.Memory import load_history

DIM = 64


def fake_embedding(text: str) -> list[float]:
    vector = [0.0] * DIM
    for word in text.lower().replace("?", " ").replace("'", " ").split():
        if len(word) >= 3:
            vector[zlib.crc32(word.encode()) % DIM] += 1.0
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


class Fake(BaseHTTPRequestHandler):
    chat_requests: list = []
    embed_requests: list = []
    chat_answers: list = []
    embed_status = 200

    def _json(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/embed":
            type(self).embed_requests.append(payload)
            if type(self).embed_status != 200:
                return self._json(type(self).embed_status, {"error": "model not found"})
            return self._json(200, {"embeddings": [fake_embedding(payload["input"])]})
        type(self).chat_requests.append(payload)
        answer = type(self).chat_answers.pop(0) if type(self).chat_answers else "A default answer long enough."
        self.send_response(200); self.send_header("Content-Type", "application/x-ndjson"); self.end_headers()
        for chunk in ({"message": {"role": "assistant", "content": answer}, "done": False},
                      {"message": {"role": "assistant", "content": ""}, "done": True,
                       "prompt_eval_count": 12, "eval_count": 6}):
            self.wfile.write((json.dumps(chunk) + "\n").encode())

    def log_message(self, *a):
        pass


class CacheTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Fake)
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close()

    def setUp(self):
        Fake.chat_requests, Fake.embed_requests, Fake.chat_answers, Fake.embed_status = [], [], [], 200
        Chat._caches.clear()
        self.tmp = tempfile.TemporaryDirectory()
        for patch in (mock.patch.object(Database, "DB_PATH", os.path.join(self.tmp.name, "t.db")),
                      mock.patch.object(Compression, "DEFAULT_BUDGET", 4000)):
            patch.start(); self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)
        Database.init_db()


Q = "Comment poser un jour de congé payé"
Q_PARAPHRASE = "comment poser un jour de congé payé svp"
Q_OTHER = "Quelle est la politique de télétravail de l'entreprise"
ANSWER = "Rendez-vous dans le portail RH, rubrique congés, puis choisissez les dates."


class TestPolicy(unittest.TestCase):
    def test_self_contained_questions_may_be_served(self):
        self.assertTrue(Policy.may_serve(Q))
        self.assertTrue(Policy.may_serve("How do I request a day off?"))

    def test_questions_that_depend_on_the_conversation_may_not(self):
        for text in ("et pour demain ?", "oui", "Peux-tu expliquer ça plus simplement", "and what about it",
                     "Pourquoi pas le lundi", "merci"):
            self.assertFalse(Policy.may_serve(text), text)

    def test_time_sensitive_questions_may_not(self):
        for text in ("Quel est le match de demain pour le Barça", "Quelle est la dernière version de Python",
                     "What is the weather in Paris", "Quelle est la météo à Nantes", "fait des recherches sur le télétravail"):
            self.assertFalse(Policy.may_serve(text), text)

    def test_questions_about_the_date_or_time_are_time_sensitive(self):
        for text in ("on est quel jour ?", "Quelle date sommes-nous aujourd'hui", "quelle heure est-il maintenant",
                     "What day is it", "what time is it in Paris"):
            self.assertFalse(Policy.may_serve(text), text)

    def test_small_talk_is_not_a_conversation_but_a_real_question_is(self):
        chat = lambda *texts: [{"role": "user", "content": t} for t in texts]
        self.assertFalse(Policy.has_substantive_history([]))
        self.assertFalse(Policy.has_substantive_history(chat("hello", "hello", "fait 1 + 1", "merci beaucoup")))
        self.assertTrue(Policy.has_substantive_history(chat("hello", "Comment poser un jour de congé payé")))
        self.assertFalse(Policy.has_substantive_history([{"role": "assistant", "content": "Une longue réponse de l'assistant ici"}]))

    def test_store_rules(self):
        ok = dict(used_tools=False, had_history=False)
        self.assertTrue(Policy.may_store(Q, ANSWER, **ok))
        self.assertFalse(Policy.may_store(Q, ANSWER, used_tools=True, had_history=False))   # web results age
        self.assertFalse(Policy.may_store(Q, ANSWER, used_tools=False, had_history=True))   # may rely on the conversation
        self.assertTrue(Policy.may_store(Q, ANSWER, used_tools=False, had_history=True, context_free_only=False))
        self.assertFalse(Policy.may_store(Q, "Oui.", **ok))                                 # too short
        self.assertFalse(Policy.may_store("et pour demain ?", ANSWER, **ok))
        for refusal in ("Je suis désolé, mais en tant qu'assistant textuel, je n'ai pas la capacité de faire des recherches.",
                        "I am sorry, I cannot search the internet for you right now."):
            self.assertFalse(Policy.may_store(Q, refusal, **ok), refusal)  # would poison later turns


class TestSemanticCache(CacheTestCase):
    def cache(self, **kw):
        return SemanticCache(self.url, threshold=kw.pop("threshold", 0.85), **kw)

    def put(self, cache, user="alice", fp="f1", question=Q, answer=ANSWER):
        cache.store(user, fp, question, cache.embed(question), answer)

    def test_the_same_and_a_close_question_hit_a_different_one_misses(self):
        cache = self.cache()
        self.put(cache)
        exact = cache.lookup("alice", "f1", Q)
        self.assertEqual((exact.hit.answer, round(exact.hit.similarity, 3)), (ANSWER, 1.0))
        self.assertIsNotNone(cache.lookup("alice", "f1", Q_PARAPHRASE).hit)
        miss = cache.lookup("alice", "f1", Q_OTHER)
        self.assertIsNone(miss.hit)
        self.assertIsNotNone(miss.embedding)  # kept, so storing the miss does not embed again

    def test_other_persona_model_or_user_do_not_share_rows(self):
        cache = self.cache()
        self.put(cache)
        self.assertIsNone(cache.lookup("alice", fingerprint("other-model", "p"), Q).hit)
        self.assertIsNone(cache.lookup("bob", "f1", Q).hit)  # scope "user"
        shared = self.cache(scope="global")
        self.put(shared, user="alice", question="Combien de jours de télétravail par semaine")
        self.assertIsNotNone(shared.lookup("bob", "f1", "Combien de jours de télétravail par semaine").hit)

    def test_fingerprint_depends_on_model_and_persona_prompt(self):
        self.assertEqual(fingerprint("m", "p"), fingerprint("m", "p"))
        self.assertNotEqual(fingerprint("m", "p"), fingerprint("m2", "p"))
        self.assertNotEqual(fingerprint("m", "p"), fingerprint("m", "p2"))

    def test_expired_rows_are_not_served(self):
        cache = self.cache(ttl_hours=1)
        self.put(cache)
        self.assertIsNotNone(cache.lookup("alice", "f1", Q).hit)
        with mock.patch("Cache.SemanticCache.time.time", return_value=__import__("time").time() + 2 * 3600):
            self.assertIsNone(cache.lookup("alice", "f1", Q).hit)

    def test_size_is_bounded_and_the_least_recently_used_goes_first(self):
        cache = self.cache(max_entries=10)
        topics = ["alpha bravo charlie", "delta echo foxtrot", "golf hotel india", "juliet kilo lima",
                  "mike november oscar", "papa quebec romeo", "sierra tango uniform", "victor whiskey xray",
                  "yankee zulu amber", "bronze copper dragon", "emerald falcon garnet", "harbor island jungle"]
        for i, topic in enumerate(topics):
            self.put(cache, question=f"Question sur {topic}", answer=ANSWER + str(i))
        self.assertEqual(cache.stats()["entries"], 10)
        self.assertIsNone(cache.lookup("alice", "f1", f"Question sur {topics[0]}").hit)       # oldest, dropped
        self.assertIsNotNone(cache.lookup("alice", "f1", f"Question sur {topics[-1]}").hit)

    def test_storing_the_same_question_twice_keeps_one_row(self):
        cache = self.cache()
        self.put(cache, answer=ANSWER + " v1")
        self.put(cache, answer=ANSWER + " v2")
        self.assertEqual(cache.stats()["entries"], 1)
        self.assertTrue(cache.lookup("alice", "f1", Q).hit.answer.endswith("v2"))

    def test_hits_are_counted_and_clear_empties(self):
        cache = self.cache()
        self.put(cache)
        cache.lookup("alice", "f1", Q); cache.lookup("alice", "f1", Q)
        self.assertEqual(cache.stats("alice")["hits"], 2)
        self.assertEqual(cache.clear("alice"), 1)
        self.assertEqual(cache.stats()["entries"], 0)

    def test_a_missing_embedding_model_is_permanent_and_reported_once(self):
        Fake.embed_status = 404
        cache = self.cache()
        with self.assertRaises(EmbeddingUnavailable):
            cache.embed(Q)
        n = len(Fake.embed_requests)
        with self.assertRaises(EmbeddingUnavailable):
            cache.embed(Q)
        self.assertEqual(len(Fake.embed_requests), n)  # no new attempt
        self.assertIn(cache.embed_model, cache.unavailable_reason)

    def test_an_unreachable_ollama_is_only_a_miss(self):
        cache = SemanticCache("http://127.0.0.1:9")
        self.assertIsNone(cache.embed(Q))
        self.assertIsNone(cache.unavailable_reason)

    def test_rows_with_another_vector_size_are_ignored(self):
        cache = self.cache()
        cache.store("alice", "f1", Q, [1.0, 0.0, 0.0], ANSWER)  # written by another embedding model
        self.assertIsNone(cache.lookup("alice", "f1", Q).hit)


class TestChatIntegration(CacheTestCase):
    def setUp(self):
        super().setUp()
        for name in ("alice", "bob"):
            get_or_create_user(name, "pw", email=f"{name}@example.com")

    def session(self, user="alice", **kw):
        values = dict(user_id=user, conversation_id=create_conversation(user, "t"), model="m",
                      persona_id="default",
                      personas={"default": {"id": "default", "name": "D", "description": "",
                                            "system_prompt": "You are a test assistant."}},
                      ollama_url=self.url, search_motor="tavily", tools=None)
        values.update(kw)
        return Session(**values)

    def turn(self, session, text):
        buf = io.StringIO()
        with redirect_stdout(buf):
            done = chat_turn(session, text)
        return done, buf.getvalue()

    def history(self, session):
        return [m["content"] for m in load_history(session.conversation_id)]

    def test_a_repeated_question_is_answered_without_any_model_call(self):
        Fake.chat_answers = [ANSWER]
        first, out1 = self.turn(self.session(), Q)
        self.assertEqual(len(Fake.chat_requests), 1)
        self.assertNotIn("from the cache", out1)

        later = self.session()  # a fresh conversation of the same user
        done, out2 = self.turn(later, "comment poser un jour de congé payé ?")
        self.assertTrue(done)
        self.assertEqual(len(Fake.chat_requests), 1)          # the model was NOT called again
        self.assertIn(f"Assistant: {ANSWER}", out2)
        self.assertIn("answered from the cache", out2)
        self.assertEqual(self.history(later), ["comment poser un jour de congé payé ?", ANSWER])  # the exchange is kept like any other

    def test_a_hit_costs_no_compression_no_rag_and_no_model(self):
        Fake.chat_answers = [ANSWER]
        self.turn(self.session(), Q)
        with mock.patch("Chatbot.build_context") as context, mock.patch("Chatbot.add_documents") as docs:
            self.turn(self.session(), Q)
        context.assert_not_called(); docs.assert_not_called()

    def test_another_user_does_not_get_my_cached_answer(self):
        Fake.chat_answers = [ANSWER, "Une autre réponse, produite pour Bob uniquement."]
        self.turn(self.session("alice"), Q)
        _, out = self.turn(self.session("bob"), Q)
        self.assertEqual(len(Fake.chat_requests), 2)
        self.assertNotIn("from the cache", out)

    def test_time_sensitive_and_follow_up_questions_are_never_cached(self):
        Fake.chat_answers = [ANSWER, ANSWER, ANSWER, ANSWER]
        q = "Quel est le match de demain pour le Barça"
        self.turn(self.session(), q); self.turn(self.session(), q)
        self.assertEqual(len(Fake.chat_requests), 2)
        self.assertEqual(Fake.embed_requests, [])  # not even embedded

    def test_a_conversation_that_starts_with_small_talk_still_fills_the_cache(self):
        session = self.session()
        Fake.chat_answers = ["Bonjour ! Comment puis-je vous aider aujourd'hui ?", ANSWER]
        self.turn(session, "hello"); self.turn(session, "hello")
        self.turn(session, Q)
        self.assertEqual(Chat.get_cache(session).stats()["entries"], 1)

    def test_an_answer_given_mid_conversation_is_not_stored_by_default(self):
        session = self.session()
        Fake.chat_answers = ["Voici la politique de télétravail de l'entreprise, en détail.", ANSWER, ANSWER]
        self.turn(session, Q_OTHER)
        self.turn(session, Q)                       # a real question came before: answered, not stored
        _, out = self.turn(self.session(), Q)       # so a new conversation still has to ask the model
        self.assertNotIn("from the cache", out)

    def test_a_refusal_is_not_cached(self):
        Fake.chat_answers = ["Je suis désolé, mais je n'ai pas la capacité de faire des recherches en temps réel.", ANSWER]
        self.turn(self.session(), Q)
        _, out = self.turn(self.session(), Q)
        self.assertEqual(len(Fake.chat_requests), 2)
        self.assertIn(ANSWER, out)

    def test_it_can_be_turned_off_with_settings(self):
        Fake.chat_answers = [ANSWER, ANSWER, ANSWER]
        self.turn(self.session(), Q)
        off = self.session()
        with redirect_stdout(io.StringIO()):
            handle_command(off, "/settings cache off")
        self.assertFalse(off.semantic_cache)
        self.turn(off, Q)
        self.assertEqual(len(Fake.chat_requests), 2)

    def test_cache_command_shows_stats_and_clears(self):
        Fake.chat_answers = [ANSWER]
        session = self.session()
        self.turn(session, Q)
        buf = io.StringIO()
        with redirect_stdout(buf):
            handle_command(session, "/cache")
        self.assertIn("entries: 1", buf.getvalue())
        with redirect_stdout(buf):
            handle_command(session, "/cache clear")
        self.assertEqual(Chat.get_cache(session).stats()["entries"], 0)

    def test_ingesting_documents_forgets_the_cached_answers(self):
        Fake.chat_answers = [ANSWER]
        session = self.session(account_role="hr")
        self.turn(session, Q)
        with mock.patch("Commands.index_directory",
                        return_value={"failed": False, "indexed": 1, "chunks": 3, "unchanged": 0, "removed": 0}), \
                redirect_stdout(io.StringIO()) as buf:
            handle_command(session, f"/ingest {self.tmp.name}")
        self.assertIn("1 cached answer(s) forgotten", buf.getvalue())
        self.assertEqual(Chat.get_cache(session).stats()["entries"], 0)

    def test_a_missing_embedding_model_costs_one_note_and_nothing_else(self):
        Fake.embed_status = 404
        Fake.chat_answers = [ANSWER, ANSWER, ANSWER]
        _, out1 = self.turn(self.session(), Q)
        _, out2 = self.turn(self.session(), Q_OTHER)
        self.assertIn("semantic cache off", out1)
        self.assertNotIn("semantic cache off", out2)
        self.assertIn(ANSWER, out1 + out2)
        self.assertEqual(len(Fake.embed_requests), 1)

    def test_an_unreachable_embedding_server_never_breaks_the_turn(self):
        Fake.chat_answers = [ANSWER]
        with mock.patch.object(SemanticCache, "embed", return_value=None):
            done, out = self.turn(self.session(), Q)
        self.assertTrue(done)
        self.assertIn(ANSWER, out)


if __name__ == "__main__":
    unittest.main(verbosity=1)
