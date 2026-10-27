"""
Tools the agent can call.

A Tool = a spec (name, description, parameters; read from tools.json) + a
Python function (bound by name). The agent never calls a function directly:
it goes through ToolRegistry.run(), which never raises. Any problem (unknown
tool, bad arguments, exception inside the tool) comes back as text, so the
model can read the error and correct itself on the next step.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable

from Agents.Confirmation import PendingAction

MAX_OBSERVATION_CHARS = int(os.getenv("AGENT_MAX_OBSERVATION_CHARS", "4000"))

_JSON_TYPES = {
    "string": str, "integer": int, "number": (int, float),
    "boolean": bool, "array": list, "object": dict,
}


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}})
    func: Callable[..., Any] | None = None
    label: str = ""  # optional human wording shown to the user, e.g. "Searching the web"
    # [A3] Critical tool: its function does not act, it PREPARES the action and returns a
    # PendingAction. The agent suspends and only the user's /confirm runs it.
    critical: bool = False

    def required(self) -> list[str]:
        return list(self.parameters.get("required", []))

    def signature(self) -> str:
        """One-line signature for the prompt: name(query: string, k?: integer)."""
        props = self.parameters.get("properties", {})
        required = set(self.required())
        parts = []
        for pname, spec in props.items():
            ptype = spec.get("type", "any") if isinstance(spec, dict) else "any"
            parts.append(f"{pname}{'' if pname in required else '?'}: {ptype}")
        return f"{self.name}({', '.join(parts)})"


def _normalize(entry: dict) -> dict | None:
    """Accept OpenAI/Ollama style {"type":"function","function":{...}} and flat style."""
    if not isinstance(entry, dict):
        return None
    spec = entry.get("function", entry)
    if not isinstance(spec, dict) or not spec.get("name"):
        return None
    params = spec.get("parameters") or spec.get("input_schema") or spec.get("args") or {}
    if not isinstance(params, dict):
        params = {}
    label = spec.get("label") or entry.get("label") or ""
    critical = spec.get("critical", entry.get("critical", False)) is True
    return {"name": str(spec["name"]), "description": str(spec.get("description", "")),
            "parameters": params, "label": str(label), "critical": critical}


def load_tool_specs(path: str) -> list[dict]:
    """Read tools.json. Accepts a list, {"tools": [...]} or {name: spec}.
    Raises FileNotFoundError / ValueError with a clear message."""
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"{path} is not valid JSON: {e}") from e
    if isinstance(data, dict) and isinstance(data.get("tools"), list):
        data = data["tools"]
    elif isinstance(data, dict):
        data = [{"name": k, **v} for k, v in data.items() if isinstance(v, dict)]
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a list of tools")
    specs = [s for s in (_normalize(e) for e in data) if s]
    if not specs:
        raise ValueError(f"{path}: no usable tool found")
    return specs


def truncate(text: str, limit: int = MAX_OBSERVATION_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[... truncated, {len(text) - limit} more characters]"


def _check_args(tool: Tool, args: dict) -> str | None:
    """Return an error message, or None when the arguments fit the spec."""
    props = tool.parameters.get("properties", {})
    missing = [p for p in tool.required() if p not in args]
    if missing:
        return f"missing argument(s): {', '.join(missing)}. Expected: {tool.signature()}"
    unknown = [a for a in args if props and a not in props]
    if unknown:
        return f"unknown argument(s): {', '.join(unknown)}. Expected: {tool.signature()}"
    for name, value in args.items():
        expected = _JSON_TYPES.get(props.get(name, {}).get("type")) if isinstance(props.get(name), dict) else None
        if expected is None:
            continue
        if isinstance(value, bool) and expected is not bool:
            return f"argument '{name}' must be {props[name]['type']}"
        if not isinstance(value, expected):
            return f"argument '{name}' must be {props[name]['type']}"
    return None


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        self.tools = {t.name: t for t in tools}

    def ollama_tools(self) -> list[dict]:
        """The tools in the format of Ollama's `tools` field (same as tools.json)."""
        return [{"type": "function", "function": {
            "name": t.name, "description": t.description, "parameters": t.parameters}}
            for t in self.tools.values()]

    @classmethod
    def from_json(cls, path: str, functions: dict[str, Callable[..., Any]]) -> "ToolRegistry":
        """Bind the specs of tools.json to Python functions by name.
        A spec without a function (or a function without a spec) is an error:
        better to fail at startup than in the middle of a run."""
        specs = load_tool_specs(path)
        names = {s["name"] for s in specs}
        unbound = names - set(functions)
        if unbound:
            raise ValueError(
                f"tools.json declares {sorted(unbound)} but no function was provided "
                f"(available: {sorted(functions)})")
        return cls([Tool(s["name"], s["description"], s["parameters"], functions[s["name"]],
                         s["label"], s["critical"])
                    for s in specs])

    def names(self) -> list[str]:
        return list(self.tools)

    def is_critical(self, name: str) -> bool:
        tool = self.tools.get(name)
        return tool is not None and tool.critical

    def propose(self, name: str, args: Any) -> tuple[PendingAction | None, str]:
        """[A3] Prepare a critical tool. Returns (action, "") or (None, error text).
        Nothing is done here: the action only runs when the user confirms.
        Fails closed: anything that is not a PendingAction is an error."""
        tool = self.tools.get(name)
        if tool is None or not tool.critical:
            return None, f"Error: '{name}' is not a tool that needs confirmation."
        problem = _check_args(tool, args if isinstance(args, dict) else {})
        if problem or not isinstance(args, dict):
            return None, f"Error calling {name}: {problem or 'arguments must be a JSON object'}"
        try:
            pending = tool.func(**args)
        except Exception as e:  # e.g. the request could not be understood: the model may retry
            return None, f"Error: {name} failed ({type(e).__name__}: {e})"
        if not isinstance(pending, PendingAction):
            return None, f"Error: {name} did not prepare an action."
        return pending, ""

    def run(self, name: str, args: Any) -> tuple[str, bool]:
        """Execute a tool. Returns (observation_text, ok). Never raises."""
        tool = self.tools.get(name)
        if tool is None:
            return f"Error: unknown tool '{name}'. Available tools: {', '.join(self.tools)}", False
        if tool.critical:
            # Safety net: a critical tool never runs directly, whoever asks.
            return f"Error: '{name}' needs the user's confirmation and cannot be run directly.", False
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return f"Error: Action Input must be a JSON object, e.g. {tool.signature()}", False
        problem = _check_args(tool, args)
        if problem:
            return f"Error calling {name}: {problem}", False
        try:
            result = tool.func(**args)
        except Exception as e:  # a tool must never crash the agent
            return f"Error: {name} failed ({type(e).__name__}: {e})", False
        if not isinstance(result, str):
            try:
                result = json.dumps(result, ensure_ascii=False, default=str)
            except Exception:
                result = str(result)
        result = result.strip() or "(empty result)"
        return truncate(result), True
