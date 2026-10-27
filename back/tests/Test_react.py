"""
Tests for the ReAct loop (A1) on Ollama's native tool calling.
No real model: a scripted LLM plays the model, and the end-to-end tests use a
fake Ollama server with the real call_ollama.

Usage (from the project root):
    python back/tests/Test_react.py
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

from Agents.ReAct import LLMError, ModelReply, ReActAgent, ollama_llm, parse_tool_call, repeats_earlier_answer
from Agents.Confirmation import PendingAction
from Agents.Engine import generate_reply
from Agents.Setup import DEFAULT_TOOLS_PATH, build_registry, format_search_results, hr_tools
from Agents.Tooling import Tool, ToolRegistry, load_tool_specs
from Commands import Session, handle_command

SEARCH = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
READ = {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}


def make_registry(calls=None, search=None):
    calls = calls if calls is not None else []

    def search_internet(query):
        calls.append(("search_internet", query))
        return search(query) if search else f"results for {query}"

    def read_webpage(url):
        calls.append(("read_webpage", url))
        return "page text " * 1000

    return ToolRegistry([Tool("search_internet", "Search", SEARCH, search_internet),
                         Tool("read_webpage", "Read", READ, read_webpage)])


def call(name, args):
    return {"function": {"name": name, "arguments": args}}


def tools_reply(*calls, content=""):
    return ModelReply(content, list(calls))


def say(text):
    return ModelReply(text)


class Script:
    """LLM stand-in: returns prepared replies in order; records messages, tools, temperature."""
    def __init__(self, *replies):
        self.replies, self.seen, self.tools, self.temps = list(replies), [], [], []

    def __call__(self, messages, tools, temperature):
        self.seen.append(json.loads(json.dumps(messages)))
        self.tools.append(tools)
        self.temps.append(temperature)
        if not self.replies:
            raise AssertionError("the agent called the model more times than expected")
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class TestParseToolCall(unittest.TestCase):
    def test_object_arguments(self):
        self.assertEqual(parse_tool_call(call("a", {"x": 1})), ("a", {"x": 1}, None))

    def test_string_arguments_are_decoded(self):
        self.assertEqual(parse_tool_call(call("a", '{"x": 1}')), ("a", {"x": 1}, None))

    def test_missing_arguments_mean_empty(self):
        self.assertEqual(parse_tool_call({"function": {"name": "a"}}), ("a", {}, None))

    def test_broken_calls_give_an_error_not_an_exception(self):
        self.assertIsNotNone(parse_tool_call(call("a", "{oops"))[2])
        self.assertIsNotNone(parse_tool_call(call("a", [1]))[2])
        self.assertIsNotNone(parse_tool_call({"function": {}})[2])
        self.assertIsNotNone(parse_tool_call("junk")[2])


class TestAgent(unittest.TestCase):
    def test_direct_answer_makes_one_call_and_no_tool_call(self):
        calls = []
        llm = Script(say("4"))
        r = ReActAgent(llm, make_registry(calls)).run("2+2?")
        self.assertEqual((r.answer, r.status, calls, len(llm.seen)), ("4", "final", [], 1))

    def test_tool_specs_system_prompt_and_temperature_are_passed(self):
        llm = Script(say("x"))
        ReActAgent(llm, make_registry(), temperature=0.1).run("q")
        self.assertEqual([t["function"]["name"] for t in llm.tools[0]], ["search_internet", "read_webpage"])
        self.assertEqual(llm.seen[0][0]["role"], "system")
        self.assertEqual(llm.temps, [0.1])

    def test_search_then_answer_sends_a_tool_message_back(self):
        calls = []
        llm = Script(tools_reply(call("search_internet", {"query": "onboarding"}), content="need facts"),
                     say("done"))
        r = ReActAgent(llm, make_registry(calls)).run("q")
        self.assertEqual((r.answer, r.status, calls), ("done", "final", [("search_internet", "onboarding")]))
        second = llm.seen[1]
        self.assertEqual(second[-2]["role"], "assistant")
        self.assertEqual(second[-2]["content"], "need facts")
        self.assertEqual(second[-2]["tool_calls"][0]["function"],
                         {"name": "search_internet", "arguments": {"query": "onboarding"}})
        self.assertEqual(second[-1], {"role": "tool", "tool_name": "search_internet",
                                      "content": "results for onboarding"})
        self.assertEqual(r.steps[0].thought, "need facts")
        self.assertEqual(r.tools_used, ["search_internet"])

    def test_two_tools_in_sequence(self):
        calls = []
        llm = Script(tools_reply(call("search_internet", {"query": "a"})),
                     tools_reply(call("read_webpage", {"url": "http://x"})), say("ok"))
        r = ReActAgent(llm, make_registry(calls)).run("q")
        self.assertEqual([c[0] for c in calls], ["search_internet", "read_webpage"])
        self.assertEqual(r.status, "final")

    def test_parallel_calls_each_get_a_tool_message(self):
        calls = []
        llm = Script(tools_reply(call("search_internet", {"query": "a"}), call("search_internet", {"query": "b"})),
                     say("ok"))
        ReActAgent(llm, make_registry(calls)).run("q")
        self.assertEqual(len(calls), 2)
        tool_msgs = [m for m in llm.seen[1] if m["role"] == "tool"]
        self.assertEqual([m["content"] for m in tool_msgs], ["results for a", "results for b"])

    def test_history_is_sent_before_the_question(self):
        llm = Script(say("x"))
        ReActAgent(llm, make_registry()).run("q2", history=[
            {"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"},
            {"role": "system", "content": "ignored"}])
        self.assertEqual([m["role"] for m in llm.seen[0]], ["system", "user", "assistant", "user"])

    def test_unknown_tool_is_reported_and_the_agent_recovers(self):
        llm = Script(tools_reply(call("delete_all", {})), say("sorry"))
        r = ReActAgent(llm, make_registry()).run("q")
        self.assertIn("unknown tool 'delete_all'", llm.seen[1][-1]["content"])
        self.assertEqual(r.answer, "sorry")

    def test_bad_arguments_are_reported_not_executed(self):
        calls = []
        llm = Script(tools_reply(call("search_internet", {"q": "x"})),
                     tools_reply(call("search_internet", {"query": 5})), say("ok"))
        ReActAgent(llm, make_registry(calls)).run("q")
        self.assertEqual(calls, [])
        self.assertIn("missing argument", llm.seen[1][-1]["content"])
        self.assertIn("must be string", llm.seen[2][-1]["content"])

    def test_unparsable_arguments_are_reported(self):
        llm = Script(tools_reply(call("search_internet", "{oops")), say("ok"))
        ReActAgent(llm, make_registry()).run("q")
        self.assertIn("not valid JSON", llm.seen[1][-1]["content"])

    def test_a_crashing_tool_becomes_an_observation(self):
        def boom(q): raise RuntimeError("network down")
        llm = Script(tools_reply(call("search_internet", {"query": "x"})), say("no network"))
        r = ReActAgent(llm, make_registry(search=boom)).run("q")
        self.assertIn("RuntimeError: network down", llm.seen[1][-1]["content"])
        self.assertFalse(r.steps[0].ok)
        self.assertEqual(r.status, "final")

    def test_long_observation_is_truncated(self):
        llm = Script(tools_reply(call("read_webpage", {"url": "u"})), say("ok"))
        ReActAgent(llm, make_registry()).run("q")
        obs = llm.seen[1][-1]["content"]
        self.assertIn("truncated", obs)
        self.assertLess(len(obs), 4200)

    def test_repeated_call_is_not_rerun_and_forces_an_answer_without_tools(self):
        calls = []
        same = call("search_internet", {"query": "x"})
        llm = Script(tools_reply(same), tools_reply(same), say("from what I have"))
        r = ReActAgent(llm, make_registry(calls)).run("q")
        self.assertEqual(len(calls), 1)
        self.assertEqual((r.status, r.answer), ("repeated", "from what I have"))
        self.assertIsNone(llm.tools[-1])  # the forcing call offers no tools

    def test_max_steps_forces_a_final_answer_without_tools(self):
        llm = Script(*[tools_reply(call("search_internet", {"query": str(i)})) for i in range(3)],
                     say("best guess"))
        r = ReActAgent(llm, make_registry(), max_steps=3).run("q")
        self.assertEqual((r.status, r.answer, len(r.steps)), ("max_steps", "best guess", 3))
        self.assertIsNone(llm.tools[-1])

    def test_context_budget_forces_an_answer(self):
        llm = Script(tools_reply(call("read_webpage", {"url": "u"})), say("stopped early"))
        r = ReActAgent(llm, make_registry(), context_char_budget=3000).run("q")
        self.assertEqual((r.status, r.answer), ("context_full", "stopped early"))

    def test_empty_reply_is_retried_once(self):
        llm = Script(say(""), say("now an answer"))
        r = ReActAgent(llm, make_registry()).run("q")
        self.assertEqual((r.answer, r.status), ("now an answer", "final"))
        llm = Script(say(""), say(""))
        r = ReActAgent(llm, make_registry()).run("q")
        self.assertEqual(r.status, "final")
        self.assertIn("could not", r.answer)

    def test_llm_error_is_reported(self):
        r = ReActAgent(Script(LLMError("cannot connect")), make_registry()).run("q")
        self.assertEqual(r.status, "llm_error")
        self.assertIn("cannot connect", r.answer)

    def test_events_are_emitted_in_order(self):
        events = []
        llm = Script(tools_reply(call("search_internet", {"query": "x"}), content="need"), say("ok"))
        ReActAgent(llm, make_registry(), on_event=lambda k, t: events.append(k)).run("q")
        self.assertEqual(events, ["thought", "action", "observation"])



class TestRepeatGuard(unittest.TestCase):
    OLD = "Je suis désolé, mais je ne peux pas faire de recherches en temps réel sur Internet."

    def history(self):
        return [{"role": "system", "content": "sys"}, {"role": "user", "content": "q1"},
                {"role": "assistant", "content": self.OLD}, {"role": "user", "content": "Comment mettre en place le télétravail ?"}]

    def test_detects_a_word_for_word_repeat_ignoring_spacing_and_case(self):
        self.assertTrue(repeats_earlier_answer("  " + self.OLD.upper() + "\n", self.history()))
        self.assertFalse(repeats_earlier_answer("Voici les étapes du télétravail, une par une.", self.history()))
        self.assertFalse(repeats_earlier_answer("ok", [{"role": "assistant", "content": "ok"}]))  # too short to matter

    def test_a_repeated_old_answer_is_retried_and_the_bad_answer_is_not_kept(self):
        llm = Script(say(self.OLD), say("Voici les étapes : ..."))
        events = []
        r = ReActAgent(llm, make_registry(), on_event=lambda k, t: events.append(k)).run_messages(self.history())
        self.assertEqual((r.answer, r.status, len(llm.seen)), ("Voici les étapes : ...", "final", 2))
        retry = llm.seen[1]
        self.assertEqual(retry[-1]["role"], "user")
        self.assertIn("Comment mettre en place le télétravail ?", retry[-1]["content"])
        self.assertEqual([m["content"] for m in retry if m["role"] == "assistant"], [self.OLD])  # only the old one
        self.assertIn("note", events)

    def test_it_retries_only_once(self):
        r = ReActAgent(Script(say(self.OLD), say(self.OLD)), make_registry()).run_messages(self.history())
        self.assertEqual(r.answer, self.OLD)

    def test_guidance_has_the_date_the_language_rule_and_the_search_reminder(self):
        llm = Script(say("x"))
        ReActAgent(llm, make_registry()).run("q")
        system = llm.seen[0][0]["content"]
        from datetime import date, timedelta
        self.assertIn(date.today().isoformat(), system)
        self.assertIn((date.today() + timedelta(days=1)).isoformat(), system)
        self.assertIn("ignore them", system)
        self.assertIn("language the user writes in", system)


class TestTooling(unittest.TestCase):
    def write(self, data):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "tools.json")
        with open(p, "w") as f:
            json.dump(data, f)
        return p

    def test_three_json_layouts_are_accepted(self):
        flat = [{"name": "a", "description": "d", "parameters": SEARCH}]
        openai = [{"type": "function", "function": flat[0]}]
        for data in (flat, openai, {"tools": flat}, {"a": {"description": "d", "parameters": SEARCH}}):
            specs = load_tool_specs(self.write(data))
            self.assertEqual([s["name"] for s in specs], ["a"])

    def test_missing_function_fails_at_startup(self):
        p = self.write([{"name": "a", "description": "d"}, {"name": "b", "description": "d"}])
        with self.assertRaises(ValueError) as ctx:
            ToolRegistry.from_json(p, {"a": lambda: "x"})
        self.assertIn("'b'", str(ctx.exception))

    def test_invalid_json_gives_a_clear_error(self):
        d = tempfile.mkdtemp(); p = os.path.join(d, "t.json")
        with open(p, "w") as f:
            f.write("{oops")
        with self.assertRaises(ValueError):
            load_tool_specs(p)

    def test_non_string_results_are_serialized(self):
        reg = ToolRegistry([Tool("t", "d", {}, lambda: [{"a": 1}])])
        self.assertEqual(reg.run("t", {}), ('[{"a": 1}]', True))


class TestSetup(unittest.TestCase):
    def session(self, motor="tavily"):
        return Session(user_id="u", conversation_id=1, model="m", persona_id="default",
                       personas={}, ollama_url="x", search_motor=motor)

    def test_results_are_formatted_for_the_model(self):
        text = format_search_results([{"title": "T", "url": "http://a", "snippet": "S", "extra": 1}])
        self.assertEqual(text, "[1] T\nhttp://a\nS")
        self.assertEqual(format_search_results([]), "No results.")

    def test_real_tools_json_binds_and_the_engine_is_read_from_the_session_at_call_time(self):
        session = self.session("tavily")
        registry = build_registry(session)
        self.assertEqual(registry.names(), ["search_internet", "read_webpage", "file_leave_request"])
        with mock.patch("Tools.web_search.search_internet", return_value=[]) as fake:
            registry.run("search_internet", {"query": "x"})
            session.search_motor = "exa"  # /switch_search
            registry.run("search_internet", {"query": "y"})
        self.assertEqual([c.args for c in fake.call_args_list], [("x", "tavily"), ("y", "exa")])

    def test_a_missing_api_key_reaches_the_model_as_an_error(self):
        registry = build_registry(self.session("brave"))
        with mock.patch.dict(os.environ, {}, clear=True):
            text, ok = registry.run("search_internet", {"query": "x"})
        self.assertFalse(ok)
        self.assertIn("BRAVE_SEARCH_API_KEY", text)


VALID_LEAVE = {"leave_type": "paid_leave", "start_date": "2026-11-03",
               "end_date": "2026-11-07", "reason": "vacances"}
SAVE = "Agents.Leave.save_leave_request"
CRITICAL = {"type": "object", "properties": {"request": {"type": "string"}}, "required": ["request"]}


def critical_registry(executed, prepare=None, searched=None):
    """A registry with one critical tool. `executed` records the real side effect."""
    def file_it(request):
        return PendingAction("Leave to confirm", f"I will file: {request}",
                             lambda: executed.append(request) or "filed")

    def search_internet(query):
        (searched if searched is not None else []).append(query)
        return "results"

    return ToolRegistry([Tool("file_leave_request", "File", CRITICAL, prepare or file_it, critical=True),
                         Tool("search_internet", "Search", SEARCH, search_internet)])


class TestHumanInTheLoop(unittest.TestCase):
    """[A3] A critical tool never acts: the agent suspends and waits for the user."""

    def test_the_agent_suspends_presents_its_plan_and_does_nothing(self):
        executed = []
        llm = Script(tools_reply(call("file_leave_request", {"request": "lundi"})))
        result = ReActAgent(llm, critical_registry(executed)).run("je pose lundi")
        self.assertEqual(result.status, "awaiting_confirmation")
        self.assertEqual(executed, [])
        self.assertEqual(result.llm_calls, 1)  # suspended: no further model call
        self.assertIn("I will file: lundi", result.answer)
        self.assertIn("/confirm", result.answer)
        self.assertIn("/cancel", result.answer)

    def test_the_action_runs_only_when_the_user_confirms(self):
        executed = []
        result = ReActAgent(Script(tools_reply(call("file_leave_request", {"request": "lundi"}))),
                            critical_registry(executed)).run("q")
        self.assertEqual(executed, [])
        self.assertEqual(result.pending.execute(), "filed")  # what /confirm does
        self.assertEqual(executed, ["lundi"])

    def test_a_critical_tool_cannot_be_run_directly(self):
        executed = []
        registry = critical_registry(executed)
        text, ok = registry.run("file_leave_request", {"request": "lundi"})
        self.assertFalse(ok)
        self.assertIn("confirmation", text)
        self.assertEqual(executed, [])

    def test_a_call_that_cannot_be_prepared_goes_back_to_the_model_and_nothing_waits(self):
        def refuse(request):
            raise ValueError("no dates found")
        llm = Script(tools_reply(call("file_leave_request", {"request": "bof"})), say("Which dates?"))
        result = ReActAgent(llm, critical_registry([], prepare=refuse)).run("q")
        self.assertEqual((result.status, result.answer), ("final", "Which dates?"))
        self.assertIsNone(result.pending)
        self.assertIn("no dates found", llm.seen[1][-1]["content"])

    def test_a_critical_tool_that_does_not_return_an_action_fails_closed(self):
        executed = []
        llm = Script(tools_reply(call("file_leave_request", {"request": "x"})), say("sorry"))
        result = ReActAgent(llm, critical_registry(executed, prepare=lambda request: "done")).run("q")
        self.assertIsNone(result.pending)
        self.assertEqual(result.status, "final")
        self.assertEqual(executed, [])

    def test_bad_arguments_never_reach_a_critical_tool(self):
        prepared = []
        llm = Script(tools_reply(call("file_leave_request", {"request": 42})), say("ok"))
        ReActAgent(llm, critical_registry([], prepare=lambda request: prepared.append(request))).run("q")
        self.assertEqual(prepared, [])

    def test_nothing_else_runs_in_the_turn_once_an_action_is_waiting(self):
        searched = []
        llm = Script(tools_reply(call("file_leave_request", {"request": "lundi"}),
                                 call("search_internet", {"query": "x"})))
        result = ReActAgent(llm, critical_registry([], searched=searched)).run("q")
        self.assertEqual(result.status, "awaiting_confirmation")
        self.assertEqual(searched, [])

    def test_ordinary_tools_still_run_without_confirmation(self):
        searched = []
        llm = Script(tools_reply(call("search_internet", {"query": "x"})), say("done"))
        result = ReActAgent(llm, critical_registry([], searched=searched)).run("q")
        self.assertEqual((result.status, searched), ("final", ["x"]))
        self.assertIsNone(result.pending)

    def test_tools_json_declares_the_leave_tool_as_critical_and_the_others_as_not(self):
        flags = {s["name"]: s["critical"] for s in load_tool_specs(DEFAULT_TOOLS_PATH)}
        self.assertTrue(flags["file_leave_request"])
        self.assertFalse(flags["search_internet"])
        self.assertFalse(flags["read_webpage"])

    def test_the_real_leave_tool_prepares_without_saving(self):
        session = Session(user_id="alice", conversation_id=1, model="m", persona_id="default",
                          personas={}, ollama_url="x", search_motor="tavily")
        registry = ToolRegistry.from_json(DEFAULT_TOOLS_PATH, {
            "search_internet": lambda query: "", "read_webpage": lambda url: "", **hr_tools(session)})
        self.assertTrue(registry.is_critical("file_leave_request"))
        with mock.patch(SAVE) as save:
            pending, problem = registry.propose("file_leave_request", VALID_LEAVE)
            self.assertEqual(problem, "")
            save.assert_not_called()
            self.assertIn("2026-11-03", pending.plan)
            text, ok = registry.run("file_leave_request", VALID_LEAVE)
            self.assertFalse(ok)
            save.assert_not_called()

    def test_bad_leave_fields_go_back_to_the_model_and_nothing_is_saved(self):
        session = Session(user_id="alice", conversation_id=1, model="m", persona_id="default",
                          personas={}, ollama_url="x", search_motor="tavily")
        registry = ToolRegistry.from_json(DEFAULT_TOOLS_PATH, {
            "search_internet": lambda query: "", "read_webpage": lambda url: "", **hr_tools(session)})
        llm = Script(tools_reply(call("file_leave_request",
                                      {**VALID_LEAVE, "leave_type": "holiday"})),
                     say("Which type of leave?"))
        with mock.patch(SAVE) as save:
            result = ReActAgent(llm, registry).run("q")
        self.assertEqual(result.status, "final")
        self.assertIsNone(result.pending)
        save.assert_not_called()
        self.assertIn("leave_type", llm.seen[1][-1]["content"])


class FakeOllama(BaseHTTPRequestHandler):
    scripted: list = []   # each item: list of message dicts (one per streamed chunk)
    received: list = []
    status = 200

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).received.append(payload)
        if type(self).status != 200:
            body = json.dumps({"error": "registry.ollama.ai/library/x does not support tools"}).encode()
            self.send_response(type(self).status); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            return
        chunks = type(self).scripted.pop(0)
        self.send_response(200); self.send_header("Content-Type", "application/x-ndjson"); self.end_headers()
        for message in chunks:
            self.wfile.write((json.dumps({"message": {"role": "assistant", **message}, "done": False}) + "\n").encode())
        self.wfile.write((json.dumps({"message": {"role": "assistant", "content": ""}, "done": True,
                                      "prompt_eval_count": 10, "eval_count": 5}) + "\n").encode())

    def log_message(self, *a):
        pass


class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeOllama)
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close()

    def setUp(self):
        FakeOllama.received, FakeOllama.status = [], 200

    def test_full_loop_over_streaming_http(self):
        # Tool call spread over streamed chunks: a thought, then the call.
        FakeOllama.scripted = [
            [{"content": "I should "}, {"content": "search."},
             {"content": "", "tool_calls": [call("search_internet", {"query": "x"})]}],
            [{"content": "all "}, {"content": "good"}],
        ]
        calls, buf = [], io.StringIO()
        with redirect_stdout(buf):
            r = ReActAgent(ollama_llm(self.url, "llama3"), make_registry(calls), temperature=0.3).run("q")
        self.assertEqual((r.answer, r.status), ("all good", "final"))
        self.assertEqual(buf.getvalue(), "")  # streaming stays off the screen
        self.assertEqual(calls, [("search_internet", "x")])
        first, second = FakeOllama.received
        self.assertEqual(first["options"], {"temperature": 0.3})
        self.assertEqual([t["function"]["name"] for t in first["tools"]], ["search_internet", "read_webpage"])
        self.assertEqual(second["messages"][-1]["role"], "tool")
        self.assertEqual(r.steps[0].thought, "I should search.")

    def test_forced_answer_sends_no_tools(self):
        FakeOllama.scripted = [[{"content": "", "tool_calls": [call("search_internet", {"query": "a"})]}],
                               [{"content": "final"}]]
        ReActAgent(ollama_llm(self.url, "llama3"), make_registry(), max_steps=1).run("q")
        self.assertIn("tools", FakeOllama.received[0])
        self.assertNotIn("tools", FakeOllama.received[1])

    def test_model_without_tool_support_gives_ollamas_explanation(self):
        FakeOllama.status = 400
        r = ReActAgent(ollama_llm(self.url, "x"), make_registry()).run("q")
        self.assertEqual(r.status, "llm_error")
        self.assertIn("does not support tools", r.answer)

    def test_ollama_down_is_an_llm_error(self):
        r = ReActAgent(ollama_llm("http://127.0.0.1:9", "llama3"), make_registry()).run("q")
        self.assertEqual(r.status, "llm_error")
        self.assertIn("cannot connect", r.answer)

    def test_chat_turn_suspends_on_the_leave_tool_and_only_confirm_saves(self):
        """[A3] Whole path: model -> agent -> engine -> /confirm."""
        FakeOllama.scripted = [[{"content": "", "tool_calls": [
            call("file_leave_request", VALID_LEAVE)]}]]
        session = Session(user_id="alice", conversation_id=1, model="llama3", persona_id="default",
                          personas={}, ollama_url=self.url, search_motor="tavily")
        session.tools = ToolRegistry.from_json(DEFAULT_TOOLS_PATH, {
            "search_internet": lambda query: "", "read_webpage": lambda url: "", **hr_tools(session)})
        context = [{"role": "system", "content": "s"}, {"role": "user", "content": "je pose lundi"}]
        buf = io.StringIO()
        with mock.patch(SAVE, return_value=4) as save:
            with redirect_stdout(buf):
                reply = generate_reply(session, context, "je pose lundi")
                self.assertEqual(len(FakeOllama.received), 1)  # the agent stopped: no second call
                save.assert_not_called()
                self.assertIsNotNone(session.pending_action)
                self.assertTrue(reply.used_tools)  # so the semantic cache never keeps this answer
                self.assertIn("/confirm", reply.text)
                handle_command(session, "/confirm")
            save.assert_called_once_with("alice", VALID_LEAVE)
        self.assertIsNone(session.pending_action)
        self.assertIn("#4", buf.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=1)
