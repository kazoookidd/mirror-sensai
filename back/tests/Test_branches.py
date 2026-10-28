"""
Tests for [X2]: branches of a conversation (Memories/Branches.py) and stopping
an answer while it is generated (call_ollama, chat_turn, Ctrl+C in the CLI).

No real Ollama: the streamed answer is a fake response, the database a temporary file.

Usage (from the project root):
    python back/tests/Test_branches.py
"""

import io
import json
import os
import signal
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import Chatbot
import Commands
from Agents import Engine
from Agents.ReAct import ModelReply
from Agents.Tooling import Tool, ToolRegistry
from Memories import Database
from Memories.Auth import create_user
from Memories.Branches import (branch_ids, create_branch, delete_family, family, rename_family, root_of, versions)
from Memories.Conversations import create_conversation, get_conversation
from Memories.Memory import load_history, save_message
from Runtime.Output import CliOutput


class TempDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patch = mock.patch.object(Database, "DB_PATH", os.path.join(self.tmp.name, "t.db"))
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)
        Database.init_db()
        create_user("alice", "alice@example.com", "pw")

    def conversation(self, *contents) -> int:
        conversation_id = create_conversation("alice", "Leave")
        for index, content in enumerate(contents):
            save_message(conversation_id, "user" if index % 2 == 0 else "assistant", content)
        return conversation_id


class BranchTests(TempDatabase):
    def test_a_branch_copies_the_messages_before_the_edited_question(self):
        root = self.conversation("Q1", "A1", "Q2", "A2")
        branch = create_branch(root, 2)
        self.assertEqual([m["content"] for m in load_history(branch)], ["Q1", "A1"])
        self.assertEqual(get_conversation(branch)["title"], "Leave (branch 2)")
        self.assertEqual((root_of(branch), root_of(root)), (root, root))
        self.assertEqual(family(branch), [root, branch])
        self.assertEqual(branch_ids(), {branch})

    def test_versions_appear_where_the_copies_differ(self):
        root = self.conversation("Q1", "A1", "Q2", "A2")
        edited = create_branch(root, 2)
        save_message(edited, "user", "Q2 bis")
        save_message(edited, "assistant", "A2 bis")
        self.assertEqual(versions(root), [{"index": 2, "current": 1, "conversations": [root, edited]}])
        self.assertEqual(versions(edited), [{"index": 2, "current": 2, "conversations": [root, edited]}])

    def test_a_regenerated_answer_is_another_version_of_the_same_question(self):
        root = self.conversation("Q1", "A1")
        again = create_branch(root, 0)
        save_message(again, "user", "Q1")
        save_message(again, "assistant", "A1 again")
        self.assertEqual(versions(again), [{"index": 0, "current": 2, "conversations": [root, again]}])

    def test_a_regenerated_answer_equal_to_the_first_is_still_a_new_version(self):
        root = self.conversation("Q1", "one")
        again = create_branch(root, 0)
        save_message(again, "user", "Q1")
        save_message(again, "assistant", "one")
        self.assertEqual(versions(root), [{"index": 0, "current": 1, "conversations": [root, again]}])

    def test_versions_follow_branches_of_branches(self):
        root = self.conversation("Q1", "A1", "Q2", "A2")
        first = create_branch(root, 2)
        save_message(first, "user", "Q2 bis")
        save_message(first, "assistant", "A2 bis")
        second = create_branch(first, 2)
        save_message(second, "user", "Q2 ter")
        save_message(second, "assistant", "A2 ter")
        self.assertEqual(versions(second), [{"index": 2, "current": 3, "conversations": [root, first, second]}])
        self.assertEqual(versions(first)[0]["current"], 2)

    def test_a_branch_made_further_down_is_not_a_version_of_earlier_questions(self):
        root = self.conversation("Q1", "A1", "Q2", "A2")
        later = create_branch(root, 2)
        save_message(later, "user", "Q2 bis")
        save_message(later, "assistant", "A2 bis")
        self.assertEqual([version["index"] for version in versions(later)], [2])

    def test_rename_and_delete_act_on_the_whole_family(self):
        root = self.conversation("Q1", "A1")
        branch = create_branch(root, 0)
        rename_family(branch, "Remote work")
        self.assertEqual(get_conversation(root)["title"], "Remote work")
        self.assertEqual(get_conversation(branch)["title"], "Remote work (branch 2)")
        delete_family(branch)
        self.assertIsNone(get_conversation(root))
        self.assertIsNone(get_conversation(branch))
        self.assertEqual(branch_ids(), set())


class FakeStream:
    def __init__(self, tokens):
        self.lines = [json.dumps({"message": {"content": token}, "done": False}).encode() for token in tokens]
        self.closed = False

    def raise_for_status(self):
        pass

    def iter_lines(self):
        yield from self.lines

    def close(self):
        self.closed = True


class StopAfter(CliOutput):
    """Stops once `count` tokens were shown, like a user pressing Stop."""

    def __init__(self, count):
        super().__init__()
        self.shown = []
        self.count = count

    def stream_start(self, prefix):
        pass

    def stream_token(self, text):
        self.shown.append(text)

    def stream_end(self):
        pass

    def stopped(self):
        return len(self.shown) >= self.count


class StopTests(unittest.TestCase):
    def test_the_stream_stops_and_keeps_what_arrived(self):
        stream = FakeStream(["Five ", "weeks ", "of ", "paid ", "leave."])
        with mock.patch.object(Chatbot.requests, "post", return_value=stream):
            reply = Chatbot.call_ollama("http://x", "m", [], out=StopAfter(2))
        self.assertEqual(reply.text, "Five weeks ")
        self.assertTrue(stream.closed)

    def test_a_stop_during_the_agent_runs_no_tool_and_keeps_the_text(self):
        searches = []
        tools = ToolRegistry([Tool("search_internet", "Search", {"type": "object", "properties": {}},
                                   lambda **_: searches.append(1), "Searching")])
        session = Commands.Session(
            user_id="a", conversation_id=1, model="m", persona_id="p", personas={"p": {"system_prompt": ""}},
            ollama_url="http://x", search_motor="none", tools=tools, show_tool_activity=False,
        )
        session.out = mock.Mock(stopped=mock.Mock(return_value=True))
        wanted = {"function": {"name": "search_internet", "arguments": {}}}
        with mock.patch.object(Engine, "ollama_llm", return_value=lambda *_: ModelReply("Let me check", [wanted])):
            reply = Engine.generate_reply(session, [{"role": "user", "content": "Latest Python version?"}], "Latest Python version?")
        self.assertEqual(reply.text, "Let me check")
        self.assertEqual(searches, [])

    def test_ctrl_c_during_a_turn_stops_the_answer_instead_of_quitting(self):
        out = CliOutput()
        before = signal.getsignal(signal.SIGINT)
        with out.interruptible():
            os.kill(os.getpid(), signal.SIGINT)
        self.assertTrue(out.stopped())
        self.assertIs(signal.getsignal(signal.SIGINT), before)


class StoppedTurnTests(TempDatabase):
    def setUp(self):
        super().setUp()
        self.session = Commands.Session(
            user_id="alice", conversation_id=self.conversation(), model="m", persona_id="p",
            personas={"p": {"system_prompt": "Tu es RH."}}, ollama_url="http://x", search_motor="none",
            show_token_usage=False, semantic_cache=False,
        )
        self.session.out = mock.Mock(stopped=mock.Mock(return_value=True))
        for name, value in (("add_documents", None), ("remember_answer", None)):
            patch = mock.patch.object(Chatbot, name, return_value=value)
            patch.start()
            self.addCleanup(patch.stop)

    def turn(self, text):
        with mock.patch.object(Chatbot, "generate_reply", return_value=Chatbot.Reply(text)), \
             redirect_stdout(io.StringIO()):
            return Chatbot.chat_turn(self.session, "Combien de jours ?")

    def test_a_stopped_answer_is_saved_but_never_cached(self):
        self.assertTrue(self.turn("Cinq sem"))
        self.assertEqual([m["content"] for m in load_history(self.session.conversation_id)], ["Combien de jours ?", "Cinq sem"])
        Chatbot.remember_answer.assert_not_called()
        self.session.out.note.assert_called_with("[answer stopped]")

    def test_an_answer_stopped_before_any_text_saves_nothing_but_says_so(self):
        self.assertFalse(self.turn("  "))
        self.assertEqual(load_history(self.session.conversation_id), [])
        self.session.out.note.assert_called_with("[answer stopped]")


if __name__ == "__main__":
    unittest.main()
