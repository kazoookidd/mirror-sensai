"""
Tests for the token limit and the token usage display.

No real Ollama is needed: a tiny local HTTP server plays the part of
POST /api/chat and reports token counts the way Ollama does, in the last
streamed chunk. The database is a temporary file.

Usage (from the project root):
    python back/tests/Test_tokens.py
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

# back/tests/Test_tokens.py -> one level up is back/, same as Chatbot.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Memories import Compression, Database
from Memories.Auth import get_or_create_user
from Memories.Conversations import create_conversation
from Memories.Memory import load_history
from Memories.TokenLimit import (
    ACTION_BLOCK,
    ACTION_CONTINUE,
    blocked_message,
    estimate_context_tokens,
    format_usage,
    is_over_limit,
    parse_bool,
    parse_limit_action,
    small,
)
from Chatbot import call_ollama, chat_turn
from Commands import Session

BUDGET = 100


class TestParsing(unittest.TestCase):
    def test_limit_action_defaults_to_block(self):
        self.assertEqual(parse_limit_action(None), (ACTION_BLOCK, None))
        self.assertEqual(parse_limit_action("  "), (ACTION_BLOCK, None))

    def test_limit_action_accepts_both_values_case_insensitively(self):
        self.assertEqual(parse_limit_action("continue"), (ACTION_CONTINUE, None))
        self.assertEqual(parse_limit_action(" BLOCK "), (ACTION_BLOCK, None))

    def test_invalid_limit_action_falls_back_to_block_with_a_warning(self):
        action, warning = parse_limit_action("ignore")
        self.assertEqual(action, ACTION_BLOCK)
        self.assertIn("ignore", warning)

    def test_parse_bool(self):
        for value in ("true", "TRUE", "1", "yes", "on"):
            self.assertTrue(parse_bool(value, False), value)
        for value in ("false", "0", "no", "off"):
            self.assertFalse(parse_bool(value, True), value)
        self.assertTrue(parse_bool(None, True))
        self.assertFalse(parse_bool("maybe", False))


class TestLimitAndFormat(unittest.TestCase):
    def test_estimate_context_tokens_uses_four_chars_per_token(self):
        messages = [{"role": "system", "content": "a" * 40}, {"role": "user", "content": "b" * 80}]
        self.assertEqual(estimate_context_tokens(messages), 10 + 20)

    def test_over_limit_is_strictly_greater_than_the_budget(self):
        self.assertFalse(is_over_limit(100, budget=100))
        self.assertTrue(is_over_limit(101, budget=100))

    def test_blocked_message_explains_how_to_get_out(self):
        text = blocked_message(150, budget=100)
        self.assertIn("150", text)
        self.assertIn("100", text)
        self.assertIn("/new", text)
        self.assertIn("TOKEN_LIMIT_ACTION=continue", text)

    def test_usage_line_has_no_percentage_below_the_threshold(self):
        line = format_usage(40, 10, budget=100, threshold_ratio=0.8)
        self.assertEqual(line, "tokens: 40 in · 10 out")
        self.assertNotIn("%", line)

    def test_usage_line_shows_the_percentage_from_the_threshold(self):
        line = format_usage(70, 10, budget=100, threshold_ratio=0.8)  # exactly 80%
        self.assertEqual(line, "tokens: 70 in · 10 out · context 80% (80/100)")

    def test_usage_line_flags_an_exceeded_limit(self):
        line = format_usage(100, 20, budget=100, threshold_ratio=0.8)
        self.assertIn("context 120% (120/100, limit exceeded)", line)

    def test_usage_line_marks_estimates_with_a_tilde(self):
        line = format_usage(70, 10, approximate=True, budget=100, threshold_ratio=0.8)
        self.assertEqual(line, "tokens: ~70 in · ~10 out · context 80% (~80/100)")

    def test_small_is_plain_text_when_piped_and_dimmed_on_a_terminal(self):
        self.assertEqual(small("x"), "x")  # tests run with stdout captured/piped
        with mock.patch("sys.stdout.isatty", return_value=True), mock.patch.dict(os.environ, clear=False):
            os.environ.pop("NO_COLOR", None)
            self.assertEqual(small("x"), "\033[2mx\033[0m")
            os.environ["NO_COLOR"] = "1"
            self.assertEqual(small("x"), "x")


class FakeChatHandler(BaseHTTPRequestHandler):
    """Streams a two-chunk answer, then the last chunk with Ollama's counts.
    Reads the instructions for the next answer from the class attributes."""
    prompt_eval_count = 30
    eval_count = 5
    report_counts = True
    received = []

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).received.append(payload)
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        chunks = [
            {"message": {"role": "assistant", "content": "Hello "}, "done": False},
            {"message": {"role": "assistant", "content": "there"}, "done": False},
        ]
        last = {"message": {"role": "assistant", "content": ""}, "done": True}
        if type(self).report_counts:
            last["prompt_eval_count"] = type(self).prompt_eval_count
            last["eval_count"] = type(self).eval_count
        for chunk in chunks + [last]:
            self.wfile.write((json.dumps(chunk) + "\n").encode())
            self.wfile.flush()

    def log_message(self, *args):
        pass


class ServerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeChatHandler)
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeChatHandler.prompt_eval_count = 30
        FakeChatHandler.eval_count = 5
        FakeChatHandler.report_counts = True
        FakeChatHandler.received = []


class TestCallOllama(ServerTestCase):
    def run_call(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            reply = call_ollama(self.url, "llama3", [{"role": "user", "content": "hi"}])
        return reply, buffer.getvalue()

    def test_returns_text_and_real_token_counts(self):
        reply, output = self.run_call()
        self.assertEqual(reply.text, "Hello there")
        self.assertEqual((reply.prompt_tokens, reply.completion_tokens), (30, 5))
        self.assertEqual(output, "Hello there\n")  # still streamed, counts not printed here

    def test_no_options_are_sent_by_default(self):
        self.run_call()
        self.assertNotIn("options", FakeChatHandler.received[0])

    def test_temperature_is_sent_to_ollama_when_set(self):
        with redirect_stdout(io.StringIO()):
            call_ollama(self.url, "llama3", [{"role": "user", "content": "hi"}], temperature=0.2)
        self.assertEqual(FakeChatHandler.received[0]["options"], {"temperature": 0.2})

    def test_temperature_zero_is_sent_and_not_mistaken_for_unset(self):
        with redirect_stdout(io.StringIO()):
            call_ollama(self.url, "llama3", [{"role": "user", "content": "hi"}], temperature=0.0)
        self.assertEqual(FakeChatHandler.received[0]["options"], {"temperature": 0.0})

    def test_counts_are_none_when_ollama_does_not_report_them(self):
        FakeChatHandler.report_counts = False
        reply, _ = self.run_call()
        self.assertEqual(reply.text, "Hello there")
        self.assertIsNone(reply.prompt_tokens)
        self.assertIsNone(reply.completion_tokens)

    # --- model options: temperature, seed, num_predict ---

    def send(self, **kwargs):
        with redirect_stdout(io.StringIO()):
            call_ollama(self.url, "llama3", [{"role": "user", "content": "hi"}], **kwargs)
        return FakeChatHandler.received[-1]

    def test_nothing_is_sent_when_nothing_is_set(self):
        self.assertNotIn("options", self.send())
        self.assertNotIn("options", self.send(options={}))

    def test_temperature_is_sent_and_zero_is_not_mistaken_for_unset(self):
        self.assertEqual(self.send(temperature=0.2)["options"], {"temperature": 0.2})
        self.assertEqual(self.send(temperature=0.0)["options"], {"temperature": 0.0})

    def test_options_are_sent_as_given(self):
        body = self.send(options={"seed": 42, "num_predict": 300})
        self.assertEqual(body["options"], {"seed": 42, "num_predict": 300})

    def test_options_and_temperature_travel_together(self):
        body = self.send(temperature=0.3, options={"seed": 7})
        self.assertEqual(body["options"], {"seed": 7, "temperature": 0.3})

    def test_the_options_dict_of_the_caller_is_left_untouched(self):
        options = {"seed": 7}
        self.send(temperature=0.3, options=options)
        self.assertEqual(options, {"seed": 7})


class TestChatTurn(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        patches = [
            mock.patch.object(Database, "DB_PATH", os.path.join(self.tmp.name, "test.db")),
            mock.patch.object(Compression, "DEFAULT_BUDGET", BUDGET),
            mock.patch.object(Compression, "DEFAULT_THRESHOLD_RATIO", 0.8),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)

        Database.init_db()
        get_or_create_user("alice", "pw", email="alice@example.com")
        self.conversation_id = create_conversation("alice", "test")

    def make_session(self, **overrides) -> Session:
        values = dict(
            user_id="alice", conversation_id=self.conversation_id, model="llama3",
            persona_id="default",
            personas={"default": {"id": "default", "name": "Default", "description": "",
                                  "system_prompt": "You are a test assistant."}},
            ollama_url=self.url, search_motor="tavily",
        )
        values.update(overrides)
        return Session(**values)

    def run_turn(self, session: Session, text: str) -> tuple[bool, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            done = chat_turn(session, text)
        return done, buffer.getvalue()

    def stored(self) -> list[str]:
        return [m["content"] for m in load_history(self.conversation_id)]

    def test_normal_turn_shows_a_minimal_usage_line_and_saves_the_exchange(self):
        done, output = self.run_turn(self.make_session(), "hello")
        self.assertTrue(done)
        self.assertIn("Assistant: Hello there", output)
        self.assertIn("tokens: 30 in · 5 out", output)
        self.assertNotIn("%", output)  # 35/100 is below the 80% threshold
        self.assertEqual(self.stored(), ["hello", "Hello there"])

    def test_usage_line_shows_the_percentage_once_80_percent_is_reached(self):
        FakeChatHandler.prompt_eval_count = 78
        FakeChatHandler.eval_count = 9
        _, output = self.run_turn(self.make_session(), "hello")
        self.assertIn("tokens: 78 in · 9 out · context 87% (87/100)", output)

    def sent_options(self) -> dict:
        """The options of the last call, without the context window that is always sent."""
        options = dict(FakeChatHandler.received[-1]["options"])
        self.assertEqual(options.pop("num_ctx"), Compression.context_window(options.get("num_predict")))
        return options

    def test_chat_turn_sends_the_session_temperature(self):
        self.run_turn(self.make_session(temperature=0.4), "hello")
        self.assertEqual(self.sent_options(), {"temperature": 0.4})

    def test_chat_turn_sends_only_the_context_window_on_the_model_default(self):
        # num_ctx is never left to Ollama's default (4,096), which would cut a longer prompt.
        self.run_turn(self.make_session(), "hello")
        self.assertEqual(self.sent_options(), {})

    def test_the_session_model_options_reach_ollama(self):
        session = self.make_session(temperature=0.4, seed=42, num_predict=300)
        self.run_turn(session, "hello")
        self.assertEqual(self.sent_options(), {"seed": 42, "num_predict": 300, "temperature": 0.4})

    def test_a_seed_of_zero_is_sent(self):
        self.run_turn(self.make_session(seed=0), "hello")
        self.assertEqual(self.sent_options(), {"seed": 0})

    def test_usage_line_can_be_turned_off(self):
        _, output = self.run_turn(self.make_session(show_token_usage=False), "hello")
        self.assertIn("Hello there", output)
        self.assertNotIn("tokens:", output)

    def test_usage_falls_back_to_estimates_when_ollama_reports_nothing(self):
        FakeChatHandler.report_counts = False
        _, output = self.run_turn(self.make_session(), "hello")
        self.assertIn("tokens: ~", output)

    def test_over_limit_blocks_the_turn_and_sends_and_saves_nothing(self):
        done, output = self.run_turn(self.make_session(), "x" * 500)  # ~125 tokens > 100
        self.assertFalse(done)
        self.assertIn("Token limit reached", output)
        self.assertEqual(FakeChatHandler.received, [])  # the model was never called
        self.assertEqual(self.stored(), [])

    def test_blocked_conversation_stays_blocked_but_a_new_one_works(self):
        session = self.make_session()
        self.run_turn(session, "x" * 500)
        done, output = self.run_turn(session, "x" * 500)  # still blocked
        self.assertFalse(done)
        self.assertIn("Token limit reached", output)

        session.conversation_id = create_conversation("alice", "fresh")
        done, output = self.run_turn(session, "hello")
        self.assertTrue(done)
        self.assertIn("Hello there", output)

    def test_continue_mode_warns_then_goes_ahead_and_exceeded_is_shown(self):
        FakeChatHandler.prompt_eval_count = 140
        FakeChatHandler.eval_count = 5
        done, output = self.run_turn(self.make_session(token_limit_action=ACTION_CONTINUE), "x" * 500)
        self.assertTrue(done)
        self.assertIn("Warning: the context is about", output)
        self.assertIn("Hello there", output)
        self.assertIn("limit exceeded", output)
        self.assertEqual(len(FakeChatHandler.received), 1)
        self.assertEqual(len(self.stored()), 2)

    def test_message_just_under_the_limit_is_not_blocked(self):
        # system prompt (~6 tokens) + 90 tokens of input stays within 100
        done, output = self.run_turn(self.make_session(), "y" * 360)
        self.assertTrue(done)
        self.assertNotIn("Token limit reached", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)