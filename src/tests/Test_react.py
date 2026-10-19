"""
Tests for the ReAct loop (A1) on Ollama's native tool calling.
No real model: a scripted LLM plays the model, and the end-to-end tests use a
fake Ollama server with the real call_ollama.

Usage (from the project root):
    python src/tests/Test_react.py
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

from Agents.ReAct import LLMError, ModelReply, ReActAgent, ollama_llm, parse_tool_call
from Agents.Setup import build_registry, format_search_results
from Agents.Tooling import Tool, ToolRegistry, load_tool_specs
from Commands import Session

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
        self.assertEqual(registry.names(), ["search_internet", "read_webpage"])
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


if __name__ == "__main__":
    unittest.main(verbosity=1)
