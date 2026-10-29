"""
Wiring between the agent and the rest of Sensai: which tool functions exist,
bound to the tools declared in tools.json.

To add a tool (RAG search, calendar, HR database...):
  1. declare it in Tools/tools.json (name, description, parameters, optional "label")
  2. register a provider returning {tool name: python function}:

        @register_provider
        def rag_tools(session):
            return {"search_documents": lambda query: rag.search(session.user_id, query)}

A provider receives the live Session, so a function can read what the user
changed at runtime (the search engine, the persona...) at call time.
"""

import os
from typing import Callable

from Agents.Tooling import ToolRegistry
from Memories.TokenLimit import parse_bool

# The tools that reach the internet (see Tools/privacy.py)
WEB_TOOLS = ("search_internet", "read_webpage")

DEFAULT_TOOLS_PATH = os.getenv(
    "AGENT_TOOLS_PATH", os.path.join(os.path.dirname(__file__), "..", "Tools", "tools.json"))

Provider = Callable[[object], dict[str, Callable]]
PROVIDERS: list[Provider] = []


def register_provider(fn: Provider) -> Provider:
    PROVIDERS.append(fn)
    return fn


def format_search_results(results: list[dict]) -> str:
    """search_internet returns [{title, url, snippet, ...}]: turn it into text the model can read."""
    if not results:
        return "No results."
    blocks = []
    for i, r in enumerate(results, start=1):
        blocks.append(f"[{i}] {r.get('title', '')}\n{r.get('url', '')}\n{r.get('snippet', '')}".strip())
    return "\n\n".join(blocks)


@register_provider
def web_tools(session) -> dict[str, Callable]:
    """The only tools that send something outside: what they send is checked first (Tools/privacy.py)."""
    from Tools import web_search          # imported here: a missing optional
    from Tools.read_websearch import read_webpage  # dependency must not break startup
    from Tools.privacy import identifiers, redact

    def private() -> tuple[str, ...]:
        return identifiers(session.user_id, session.email, (session.profile or {}).get("name"))

    def search_internet(query: str) -> str:
        clean, removed = redact(query, private())
        if removed and not clean:
            return (f"Not sent: the query only held personal details ({', '.join(removed)}). "
                    "Search for the general rule instead, without any personal detail.")
        # session.search_motor is read at CALL time, so /switch_search applies at once.
        results = format_search_results(web_search.search_internet(clean, session.search_motor))
        if removed:
            return (f"Personal details were removed before the query left this machine "
                    f"({', '.join(removed)}). Query sent: {clean}\n\n{results}")
        return results

    def read_page(url: str) -> str:
        _, found = redact(url, private())
        if found:
            raise ValueError(f"not opened, the address holds personal details ({', '.join(found)})")
        return read_webpage(url)

    return {"search_internet": search_internet, "read_webpage": read_page}


@register_provider
def hr_tools(session) -> dict[str, Callable]:
    """[A3] Critical tools: they only prepare the action, the user's /confirm does it.
    The user is always the session's: the model never chooses whose request it touches."""
    from Agents.Leave import prepare_cancellation, prepare_leave_request

    def file_leave_request(leave_type: str, start_date: str, end_date: str,
                           reason: str = "") -> object:
        return prepare_leave_request(session, leave_type, start_date, end_date, reason)

    def cancel_leave_request(start_date: str) -> object:
        return prepare_cancellation(session, start_date)

    return {"file_leave_request": file_leave_request, "cancel_leave_request": cancel_leave_request}


def build_registry(session, tools_path: str = DEFAULT_TOOLS_PATH) -> ToolRegistry:
    """Bind every tool declared in tools.json to the function a provider offers.
    A declared tool nobody provides fails with a clear message at startup;
    a provided function that tools.json does not declare is simply not offered.
    AGENT_WEB_TOOLS=false removes the web tools: nothing at all leaves the machine."""
    functions: dict[str, Callable] = {}
    for provider in PROVIDERS:
        functions.update(provider(session))
    registry = ToolRegistry.from_json(tools_path, functions)
    if not parse_bool(os.getenv("AGENT_WEB_TOOLS"), True):
        for name in WEB_TOOLS:
            registry.tools.pop(name, None)
    return registry
