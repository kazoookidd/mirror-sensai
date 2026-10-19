"""
[A1] Reasoning loop (ReAct) on Ollama's native tool calling.

The model is given the tool specs (tools.json). When it wants a tool it does
NOT write it in the text: Ollama returns it in `message.tool_calls`, a
structured field. That field, not the prompt, is how the loop knows an
execution is requested:

    user question
      -> model: content ("thought") + tool_calls        (Reason + Act)
      -> agent runs the tools, appends {"role": "tool", ...}   (Observe)
      -> model again ... until a reply WITHOUT tool_calls = the final answer

The loop knows nothing about Ollama or about a specific tool: the model call
(`llm`) and the tools (`ToolRegistry`) are injected, so it is testable with a
scripted model.

Guards, because a small local model WILL misbehave:
  - max_steps         hard stop, then one last call WITHOUT tools to force an answer
  - same call twice   same tool + same arguments -> not re-run, answer forced
  - bad tool call     unknown tool, missing or mistyped arguments, tool that
                      raises: the error goes back as a tool message, no crash
  - huge result       truncated; a context that is too large forces the answer
  - empty reply       retried once with a nudge

Cost of a simple question: ONE model call. A reply without tool_calls is
already the final answer, so there is no extra "thinking" round.
"""

import io
import json
import os
from contextlib import nullcontext, redirect_stdout
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from Agents.Tooling import ToolRegistry

MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "4"))
TEMPERATURE = float(os.getenv("AGENT_TEMPERATURE", "0.2"))
CONTEXT_CHAR_BUDGET = int(os.getenv("AGENT_CONTEXT_CHARS", "24000"))  # ~6000 tokens

DEFAULT_PROMPT = "You are a helpful assistant."

# Appended to the system prompt of the active persona when tools are offered.
TOOL_GUIDANCE = """

--- Tools ---
You can call tools. Today's date is {date}.
- Answer directly, with no tool, whenever you can do so reliably: general knowledge, explanations, writing, reformulating, advice, anything about this conversation.
- Use a tool only for information that is recent, current, or must be verified externally (news, prices, versions, rules that may have changed), or for the content of a specific web page.
- One well-chosen call is usually enough. Search first, read a page only if the snippets are not sufficient. Never repeat an identical call; if a result is useless, change the query or answer with what you have.
- Never invent results or sources. If the tools gave nothing useful, say so.
- After using tools, answer in the user's language and cite the URLs you relied on."""


class LLMError(Exception):
    """The model call failed (Ollama down, model without tool support...).
    The message is the user-readable text, already starting with "Error"."""


@dataclass
class ModelReply:
    """What the agent needs from one model call."""
    content: str = ""
    tool_calls: list = field(default_factory=list)  # [{"function": {"name", "arguments"}}]
    prompt_tokens: int | None = None      # as reported by Ollama, None if absent
    completion_tokens: int | None = None


@dataclass
class Step:
    thought: str = ""
    action: str | None = None
    action_input: dict | None = None
    observation: str | None = None
    ok: bool = True


@dataclass
class AgentResult:
    answer: str
    status: str  # final | max_steps | repeated | context_full | llm_error
    steps: list[Step] = field(default_factory=list)
    llm_calls: int = 0
    prompt_tokens: int | None = None      # size of the LAST call = the real context size
    completion_tokens: int | None = None  # summed over all calls

    @property
    def tools_used(self) -> list[str]:
        return [s.action for s in self.steps if s.action]


def parse_tool_call(call: Any) -> tuple[str, dict | None, str | None]:
    """(name, arguments, error) from one entry of message.tool_calls.
    Ollama sends arguments as an object; some models send a JSON string."""
    fn = call.get("function", call) if isinstance(call, dict) else {}
    name = fn.get("name") if isinstance(fn, dict) else None
    if not name or not isinstance(name, str):
        return "", None, "tool call without a name"
    args = fn.get("arguments", {})
    if args in (None, ""):
        args = {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return name, None, "arguments are not valid JSON"
    if not isinstance(args, dict):
        return name, None, "arguments must be a JSON object"
    return name, args, None


Event = Callable[[str, str], None]  # (kind, text): thought | action | observation | note
LLM = Callable[[list[dict], list[dict] | None, float], ModelReply]


class ReActAgent:
    def __init__(self, llm: LLM, registry: ToolRegistry, system_prompt: str | None = None,
                 max_steps: int = MAX_STEPS, temperature: float | None = TEMPERATURE,
                 on_event: Event | None = None, context_char_budget: int = CONTEXT_CHAR_BUDGET,
                 guidance: str = TOOL_GUIDANCE):
        self.llm = llm
        self.registry = registry
        self.system_prompt = system_prompt or DEFAULT_PROMPT
        self.max_steps = max_steps
        self.temperature = temperature
        self.on_event = on_event or (lambda kind, text: None)
        self.context_char_budget = context_char_budget
        self.guidance = guidance

    # -- bookkeeping -------------------------------------------------------
    def _call(self, messages, tools, tally: dict) -> ModelReply:
        reply = self.llm(messages, tools, self.temperature)
        tally["calls"] += 1
        if reply.prompt_tokens is not None:
            tally["prompt"] = reply.prompt_tokens
        if reply.completion_tokens is not None:
            tally["completion"] = (tally["completion"] or 0) + reply.completion_tokens
        return reply

    @staticmethod
    def _result(tally: dict, answer: str, status: str | None, steps: list[Step]) -> AgentResult:
        return AgentResult(answer, status, steps, tally["calls"], tally["prompt"], tally["completion"])

    @staticmethod
    def _size(messages: list[dict]) -> int:
        return sum(len(m.get("content") or "") for m in messages)

    def _with_guidance(self, messages: list[dict]) -> list[dict]:
        """Copy of messages whose system prompt also carries the tool guidance."""
        guidance = self.guidance.replace("{date}", date.today().isoformat())
        messages = [dict(m) for m in messages]
        if messages and messages[0].get("role") == "system":
            messages[0]["content"] = f"{messages[0]['content']}{guidance}"
        else:
            messages.insert(0, {"role": "system", "content": f"{self.system_prompt}{guidance}"})
        return messages

    def _force_answer(self, messages, why: str, tally, steps) -> AgentResult:
        """One last call with NO tools, so the model can only answer."""
        messages = messages + [{"role": "user", "content":
            f"{why} Do not call any tool. Answer now with what you have, and say what is missing."}]
        try:
            reply = self._call(messages, None, tally)
        except LLMError as e:
            return self._result(tally, str(e), "llm_error", steps)
        return self._result(tally, reply.content.strip() or "I could not reach a reliable answer.",
                            None, steps)

    # -- entry points ------------------------------------------------------
    def run(self, question: str, history: list[dict] | None = None) -> AgentResult:
        """history: earlier user/assistant messages of the conversation (optional)."""
        messages = [{"role": "system", "content": self.system_prompt}]
        messages += [m for m in (history or []) if m.get("role") in ("user", "assistant")]
        messages.append({"role": "user", "content": question})
        return self.run_messages(messages)

    def run_messages(self, messages: list[dict]) -> AgentResult:
        """Run from a prepared context (system prompt first, current question last),
        e.g. the one built from the database. The tool guidance is added to the
        system prompt; the caller's list is not modified."""
        messages = self._with_guidance(messages)
        tools = self.registry.ollama_tools()
        steps: list[Step] = []
        seen: set[str] = set()
        tally = {"calls": 0, "prompt": None, "completion": None}
        empty_retry = True

        def finish(result: AgentResult, status: str) -> AgentResult:
            if result.status is None:
                result.status = status
            return result

        for _ in range(self.max_steps):
            # Never refuse the very first call: the caller already applied the token limit policy.
            if steps and self._size(messages) > self.context_char_budget:
                return finish(self._force_answer(messages, "The context is full.", tally, steps),
                              "context_full")
            try:
                reply = self._call(messages, tools, tally)
            except LLMError as e:
                return self._result(tally, str(e), "llm_error", steps)

            thought = reply.content.strip()
            if not reply.tool_calls:
                # No tool_calls: this is the final answer.
                if not thought and empty_retry:
                    empty_retry = False
                    self.on_event("note", "empty reply, retrying")
                    messages.append({"role": "user", "content": "Your reply was empty. Answer the question."})
                    continue
                return self._result(tally, thought or "I could not produce an answer.", "final", steps)

            if thought:
                self.on_event("thought", thought)
            # Keep the assistant message exactly as a tool-calling turn needs it.
            messages.append({"role": "assistant", "content": thought, "tool_calls": [
                {"function": {"name": c.get("function", {}).get("name", ""),
                              "arguments": parse_tool_call(c)[1] or {}}}
                for c in reply.tool_calls if isinstance(c, dict)]})

            repeated = False
            for tool_call in reply.tool_calls:
                name, args, error = parse_tool_call(tool_call)
                step = Step(thought, name or None, args)
                thought = ""  # the thought belongs to the first call only
                steps.append(step)
                self.on_event("action", self._describe(name, args))

                if error:
                    step.observation, step.ok = f"Error calling {name or '?'}: {error}", False
                else:
                    key = f"{name}|{json.dumps(args, sort_keys=True, default=str)}"
                    if key in seen:
                        step.observation, step.ok = "Error: you already ran this exact call.", False
                        repeated = True
                    else:
                        seen.add(key)
                        step.observation, step.ok = self.registry.run(name, args)
                self.on_event("observation" if step.ok else "tool_error", step.observation)
                messages.append({"role": "tool", "tool_name": name, "content": step.observation})

            if repeated:
                return finish(self._force_answer(messages, "You are repeating the same call.", tally, steps),
                              "repeated")

        return finish(self._force_answer(messages, f"You used all {self.max_steps} steps.", tally, steps),
                      "max_steps")

    def _describe(self, name: str, args: dict | None) -> str:
        """Human wording of a call for the activity line: 'Searching the web: query'."""
        tool = self.registry.tools.get(name)
        label = (tool.label if tool and tool.label else name) or "?"
        values = ", ".join(str(v) for v in (args or {}).values())
        return f"{label}: {values}" if values else label


def ollama_llm(base_url: str, model: str, echo: bool = False, prefix: str = "") -> LLM:
    """Adapter over the existing streaming call_ollama.
    echo=False: silent. echo=True: the text is written to the screen as it
    arrives (chat mode), `prefix` printed once before the first character.
    A failed call becomes an LLMError carrying the message call_ollama
    reports (nothing is printed: the caller decides what the user sees)."""
    def llm(messages: list[dict], tools: list[dict] | None, temperature: float | None) -> ModelReply:
        from Chatbot import call_ollama  # lazy: Chatbot imports Engine, avoid a cycle
        errors: list[str] = []
        silent = io.StringIO()
        with (nullcontext() if echo else redirect_stdout(silent)):
            reply = call_ollama(base_url, model, messages, temperature=temperature, tools=tools,
                                echo=echo, prefix=prefix, on_error=errors.append)
        if reply is None:
            raise LLMError(errors[-1] if errors else "Error: model call failed")
        return ModelReply(reply.text, reply.tool_calls, reply.prompt_tokens, reply.completion_tokens)
    return llm

