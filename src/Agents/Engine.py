"""
The single entry point the chat uses to get an answer.

    generate_reply(session, context, user_input) -> Reply | None

Tools are part of every normal turn; the user never has to ask for them.

  * no tools available / disabled / small talk -> one plain streaming call,
    exactly as before the agent existed
  * otherwise -> the SAME first call, with the tools offered. If the model
    just answers, that is the whole turn (one call, streamed, no overhead).
    Only when the model asks for a tool does the ReAct loop continue
  * a model that cannot do tool calling is detected once, remembered, and
    served without tools: nothing breaks, the user sees one dimmed note
"""

from Agents.ReAct import ReActAgent, ollama_llm
from Agents.Router import should_offer_tools
from Memories import Compression
from Memories.TokenLimit import small

PREFIX = "Assistant: "
CHARS_PER_TOKEN = 4  # same estimate as the compression module

# Models Ollama refused tools for. Process-wide: it is a property of the model.
_NO_TOOLS: set[str] = set()


def _is_tools_refusal(message: str) -> bool:
    return "support tools" in message.lower()


def _print_activity(kind: str, text: str) -> None:
    """Discreet line under the answer so the user sees WHERE it comes from."""
    if kind == "action":
        print(small(f"  · {text[:110]}"))
    elif kind == "tool_error":
        print(small(f"  · failed: {text[:110]}"))


def tools_available(session, user_input: str) -> bool:
    return bool(
        session.tools is not None
        and session.tools.names()
        and session.tools_enabled
        and session.model not in _NO_TOOLS
        and should_offer_tools(user_input)
    )


def generate_reply(session, context: list[dict], user_input: str):
    """context: the system prompt + history + the current user message.
    Streams the answer to stdout. Returns a Reply, or None if the call failed
    (the error has been printed)."""
    from Chatbot import Reply, call_ollama  # lazy: Chatbot imports this module

    def plain() -> Reply | None:
        return call_ollama(session.ollama_url, session.model, context,
                           temperature=session.temperature, prefix=PREFIX)

    if not tools_available(session, user_input):
        return plain()

    last_text = {"value": ""}
    base_llm = ollama_llm(session.ollama_url, session.model, echo=True, prefix=PREFIX)

    def llm(messages, tools, temperature):
        reply = base_llm(messages, tools, temperature)
        last_text["value"] = reply.content
        return reply

    agent = ReActAgent(
        llm, session.tools, temperature=session.temperature,
        on_event=_print_activity if session.show_tool_activity else None,
        context_char_budget=Compression.DEFAULT_BUDGET * CHARS_PER_TOKEN,
    )
    result = agent.run_messages(context)

    if result.status == "llm_error":
        if not result.steps and _is_tools_refusal(result.answer):
            _NO_TOOLS.add(session.model)
            print(small(f"[{session.model} cannot use tools: answering without them]"))
            return plain()
        print(result.answer)
        return None

    if result.answer.strip() != last_text["value"].strip():
        print(f"{PREFIX}{result.answer}")  # answer produced by a fallback, not streamed
    return Reply(result.answer, result.prompt_tokens, result.completion_tokens)
