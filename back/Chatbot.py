import requests
import json
import argparse
import os
import getpass
import sqlite3
from dataclasses import dataclass, field

from Runtime.Env import load_env, project_path

# Before the project imports below: some of them read their settings when imported.
load_env()

from Memories.Database import init_db
from Memories.Auth import ROLE_EMPLOYEE, email_of, get_or_create_user, role_of
from Memories.Memory import save_message, load_history
from Memories.Conversations import record_model
from Memories.Profile import context_text, get_profile
from Memories.Compression import build_context, estimate_tokens
from Memories.TokenLimit import (
    ACTION_BLOCK,
    LIMIT_ACTIONS,
    blocked_message,
    estimate_context_tokens,
    get_budget,
    is_over_limit,
    parse_bool,
    parse_limit_action,
    warning_message,
)
from Runtime.Personas import DEFAULT_PERSONA_ID, load_personas, resolve_persona
from Runtime.Parameters import (
    describe_temperature,
    parse_num_predict,
    parse_seed,
    parse_temperature,
)
from Commands import Session, handle_command, select_conversation
from rag.Attachments import SHARE_OF_ROOM, attachments_message, has_attachments
from rag.Retriever import rag_message
from Agents.Engine import generate_reply
from Agents.ReAct import tool_calls_in_text
from Agents.Router import asks_for_leave
from Cache.Chat import CacheTurn, check as check_cache, hit_note, remember as remember_answer
from Cache.Policy import has_substantive_history
from Agents.Setup import build_registry
from Runtime.Output import CliOutput

FALLBACK_SYSTEM_PROMPT = "You are Sensai, a helpful assistant."


@dataclass
class Reply:
    """A completed answer from the model, with the token counts Ollama
    reports in its last streamed chunk (None when it did not report them)."""
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    # Tool calls requested by the model (message.tool_calls), as sent by Ollama:
    # [{"function": {"name": ..., "arguments": {...}}}]. Empty for a plain answer.
    tool_calls: list = field(default_factory=list)
    # True when tools were used to produce this answer (their results can go stale)
    used_tools: bool = False


def load_system_prompt(path: str) -> str | None:
    """Load a system prompt from a text file. Returns None if not found."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return content if content else None
    except FileNotFoundError:
        return None


def _as_count(value) -> int | None:
    """Ollama's token counts are plain integers; anything else is ignored."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def call_ollama(base_url: str, model: str, messages: list,
                temperature: float | None = None, tools: list | None = None,
                echo: bool = True, prefix: str = "",
                on_error=None, options: dict | None = None, out=None) -> Reply | None:
    """Send the full message history to Ollama and stream the response.
    Returns the full answer with its token counts and any tool calls the
    model requested, or None if the call failed.

    tools:    tool specs (tools.json format) the model may call.
    echo:     stream the text to stdout (False = silent).
    prefix:   printed once, just before the first streamed character, so an
              answer that is empty (a pure tool call) leaves no dangling label.
    on_error: receives the error message instead of printing it.
    options:  more Ollama options (seed, num_predict...), sent as is.
              Nothing is sent for what is not set: the model's default applies.
    out:      where the answer and errors are written (default: the terminal)."""
    out = out or CliOutput()
    report = on_error or out.error
    payload = {"model": model, "messages": messages, "stream": True}
    sent_options = dict(options or {})
    if temperature is not None:
        sent_options["temperature"] = temperature
    if sent_options:
        payload["options"] = sent_options
    if tools:
        payload["tools"] = tools
    try:
        response = requests.post(f"{base_url}/api/chat", json=payload, stream=True)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        report("Error: cannot connect to Ollama. Is it running? (ollama serve)")
        return None
    except requests.exceptions.HTTPError as e:
        # Ollama explains the refusal in the body (e.g. "does not support tools").
        detail = ""
        try:
            detail = response.json().get("error", "")
        except ValueError:
            pass
        report(f"Error: model unavailable or bad request ({e}){': ' + detail if detail else ''}")
        return None

    full_reply = ""
    tool_calls = []
    prompt_tokens = None
    completion_tokens = None
    started = False
    # With tools offered, a reply that starts like JSON may be a tool call WRITTEN as text
    # by a small model: it is held back, not streamed, until the end tells what it is.
    tool_names = {(spec.get("function") or spec).get("name") for spec in tools or []}
    held = None
    try:
        for line in response.iter_lines():
            if not line:
                continue
            if out.stopped():  # [X2] the user stopped the answer: keep what arrived
                response.close()
                break
            chunk = json.loads(line)

            if "error" in chunk:
                report(f"Error from Ollama: {chunk['error']}")
                return None

            content = chunk.get("message", {}).get("content", "")
            if (tool_names and held is None and not started and not full_reply.strip()
                    and content.lstrip()[:1] in ("{", "}", "[", "]", "<", "`")):
                held = ""
            if held is not None:
                held += content
            elif echo and content:
                if not started:
                    out.stream_start(prefix)
                    started = True
                out.stream_token(content)
            full_reply += content
            # Tool calls arrive in message.tool_calls, possibly across chunks.
            tool_calls.extend(chunk.get("message", {}).get("tool_calls") or [])
            if chunk.get("done"):
                # Only the last chunk carries the real token counts.
                prompt_tokens = _as_count(chunk.get("prompt_eval_count"))
                completion_tokens = _as_count(chunk.get("eval_count"))
                break
    except requests.exceptions.ChunkedEncodingError:
        if started:
            out.stream_end()
        report("Error: connection interrupted while streaming.")
        return None

    if held is not None:
        written = [] if tool_calls else tool_calls_in_text(full_reply, tool_names)
        if tool_calls or written:
            # A tool call, not an answer: never shown, and not kept as the model's "thought".
            tool_calls, full_reply = tool_calls or written, ""
        elif echo and held:
            out.stream_start(prefix)  # an ordinary answer after all (JSON, code...): shown at once
            started = True
            out.stream_token(held)
    if started:
        out.stream_end()  # saut de ligne final
    return Reply(full_reply, prompt_tokens, completion_tokens, tool_calls)


def login_flow() -> str:
    """Prompt for user_id and password at startup.
    - If the account exists, authenticate against the stored password.
    - If it doesn't, collect an email and create a new account.
    Returns the authenticated user_id, or exits the program on failure."""
    print("=== Login ===")
    user_id = input("User ID: ").strip()

    if not user_id:
        print("Error: user ID cannot be empty.")
        raise SystemExit(1)

    password = getpass.getpass("Password: ")

    try:
        user = get_or_create_user(user_id, password)
        print(f"Welcome back, {user['user_id']}.\n")
        return user["user_id"]
    except ValueError as e:
        if str(e) == "Incorrect password.":
            print("Error: incorrect password.")
            raise SystemExit(1)

        # user_id not found -> create a new account
        print(f"No account found for '{user_id}'. Let's create one.")
        email = input("Email: ").strip()
        password_confirm = getpass.getpass("Confirm password: ")

        if password != password_confirm:
            print("Error: passwords do not match.")
            raise SystemExit(1)

        try:
            user = get_or_create_user(user_id, password, email=email)
        except ValueError as e2:
            print(f"Error: {e2}")
            raise SystemExit(1)

        print(f"HR account created for {user['user_id']}. Employees create theirs on the web interface.\n")
        return user["user_id"]


def add_documents(context: list[dict], user_input: str, ollama_url: str, conversation_id: int | None = None, search_base: bool = True) -> None:
    """Add the files joined to the conversation, then the HR documents relevant to `user_input`, within the token limit.
    They go INTO the system message, as described sections after the persona and the profile (the tool
    guidance comes last). A second system message right before the question was read by small models as
    the order of the turn: they stopped calling tools whenever an excerpt was found."""
    question = {"role": "user", "content": user_input}
    room = get_budget() - estimate_context_tokens(context + [question])
    attached = attachments_message(conversation_id, user_input, int(room * SHARE_OF_ROOM), ollama_url)
    if attached:
        _add_to_system(context, attached["content"])
        room -= estimate_tokens(attached["content"])
    # A leave request is an action: excerpts about leave rules made small models explain the rules
    # instead of preparing the request (docs/benchmarks/chat_models.md). The joined files are kept.
    documents = None if not search_base or asks_for_leave(user_input) else rag_message(user_input, room, ollama_url=ollama_url)
    if documents:
        _add_to_system(context, documents["content"])


def _add_to_system(context: list[dict], section: str) -> None:
    """Append `section` to the system message (the first message), or start one."""
    if context and context[0].get("role") == "system":
        context[0] = {**context[0], "content": f"{context[0]['content']}\n\n{section}"}
    else:
        context.insert(0, {"role": "system", "content": section})


def refresh_profile(session: Session) -> None:
    """[M1] Load the user's profile from the database into the session."""
    try:
        session.profile = get_profile(session.user_id)
    except sqlite3.Error:
        pass  # keep the one already loaded: the profile must never block a turn


def chat_turn(session: Session, user_input: str) -> bool:
    """Run one user -> assistant exchange.
    Returns True when the exchange completed and was saved, False when it
    was refused (token limit) or failed (nothing is persisted in that case)."""
    # Context built fresh from SQLite every turn, scoped to the active
    # conversation (summary + recent messages, compressed if needed). The
    # system prompt comes from the ACTIVE persona and the model is the
    # ACTIVE model, so both can change between two turns without touching
    # the stored history. The current input is appended only in-memory, and
    # only saved to DB once we have a reply.
    # [A6] Semantic cache: a question that means the same as an earlier one is
    # answered from the cache, BEFORE anything costly (compression, RAG search,
    # model call). Only self-contained, non time-sensitive questions qualify.
    # A chat with joined files never uses the cache: the answer depends on the files.
    # [M1] The profile is read again at every turn: /profile or the web page may have
    # changed it. It is part of the system prompt, so also of the cache fingerprint.
    refresh_profile(session)
    # Without the HR documents, a cached answer written from them would not be the answer asked for.
    skip_cache = has_attachments(session.conversation_id) or not session.hr_documents
    cache_turn = CacheTurn() if skip_cache else check_cache(session, user_input)
    if cache_turn.hit is not None:
        session.out.answer(cache_turn.hit.answer)
        session.out.note(hit_note(cache_turn.hit))
        save_message(session.conversation_id, "user", user_input)
        save_message(session.conversation_id, "assistant", cache_turn.hit.answer)
        return True

    had_history = has_substantive_history(load_history(session.conversation_id))
    context = build_context(
        session.conversation_id,
        session.system_prompt,
        session.model,
        session.ollama_url,
    )
    add_documents(context, user_input, session.ollama_url, session.conversation_id, session.hr_documents)
    context.append({"role": "user", "content": user_input})

    # Token limit: compression had its chance, this is what is left.
    context_tokens = estimate_context_tokens(context)
    session.out.context(context_tokens, get_budget())
    if is_over_limit(context_tokens):
        if session.token_limit_action == ACTION_BLOCK:
            session.out.error(blocked_message(context_tokens))
            return False
        session.out.warning(warning_message(context_tokens))

    # generate_reply replaces the direct model call: it streams the answer and
    # lets the model use its tools when it judges it useful. A message that
    # needs no tool still costs ONE model call.
    reply = generate_reply(session, context, user_input)
    stopped = session.out.stopped()
    if stopped:
        session.out.note("[answer stopped]")  # [X2] what arrived is kept, but never served from the cache

    if reply is None or (stopped and not reply.text.strip()):
        # Nothing was persisted yet for this turn, so there is nothing
        # to roll back, just let the user retry.
        return False

    save_message(session.conversation_id, "user", user_input)
    save_message(session.conversation_id, "assistant", reply.text)
    record_model(session.conversation_id, session.model)
    if stopped:
        return True
    remember_answer(session, cache_turn, user_input, reply.text,
                    used_tools=reply.used_tools, had_history=had_history)

    if session.show_token_usage:
        # Prefer Ollama's own counts; fall back to the estimate if absent.
        approximate = reply.prompt_tokens is None or reply.completion_tokens is None
        prompt_tokens = reply.prompt_tokens if reply.prompt_tokens is not None else context_tokens
        completion_tokens = (
            reply.completion_tokens if reply.completion_tokens is not None
            else estimate_tokens(reply.text)
        )
        session.out.usage(prompt_tokens, completion_tokens, approximate)
    return True


def build_parser(description: str = "Sensai CLI chatbot") -> argparse.ArgumentParser:
    """Command-line options shared by the CLI and the web UI (.env gives the defaults)."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--model",
        default=os.getenv("MODEL", "llama3"),
        help="Ollama model name at startup (overrides .env MODEL). "
             "Can be changed at runtime with /model"
    )
    parser.add_argument(
        "--system-prompt",
        default=os.getenv("SYSTEM_PROMPT_PATH", "back/config/system_prompt.txt"),
        help="Path to the system prompt file used by the default persona "
             "(overrides .env SYSTEM_PROMPT_PATH)"
    )
    parser.add_argument(
        "--ollama-url",
        default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        help="Base URL of the Ollama server"
    )
    parser.add_argument(
        "--personas-dir",
        default=os.getenv("PERSONAS_DIR", "back/config/personas"),
        help="Directory containing persona JSON files (overrides .env PERSONAS_DIR)"
    )
    parser.add_argument(
        "--persona",
        default=os.getenv("DEFAULT_PERSONA", DEFAULT_PERSONA_ID),
        help="Persona active at startup (overrides .env DEFAULT_PERSONA). "
             "Can be changed at runtime with /persona"
    )
    parser.add_argument(
        "--on-token-limit",
        default=os.getenv("TOKEN_LIMIT_ACTION"),
        help=f"What to do when the context is over the token limit, even after "
             f"compression: {' or '.join(LIMIT_ACTIONS)} "
             f"(overrides .env TOKEN_LIMIT_ACTION)"
    )
    parser.add_argument(
        "--temperature",
        default=os.getenv("TEMPERATURE"),
        help="Sampling temperature of the answers, 0 (deterministic) to 2 "
             "(creative); unset = the model's default (overrides .env "
             "TEMPERATURE). Can be changed at runtime with /temperature"
    )
    parser.add_argument(
        "--seed",
        default=os.getenv("SEED"),
        help="Fixed seed: same seed + same question + same settings = same answer; "
             "unset = not fixed (overrides .env SEED). Runtime: /settings seed"
    )
    parser.add_argument(
        "--num-predict",
        default=os.getenv("NUM_PREDICT"),
        help="Maximum length of an answer, in tokens; unset = the model's default "
             "(overrides .env NUM_PREDICT). Runtime: /settings num-predict"
    )
    return parser


def build_session(args, user_id: str, conversation_id: int) -> Session:
    """The Session of a logged-in user, from the command-line options.
    Configuration problems are printed as warnings and replaced by defaults."""
    default_prompt = load_system_prompt(project_path(args.system_prompt))
    if default_prompt:
        print(f"[System prompt loaded from {args.system_prompt}]")
    else:
        default_prompt = FALLBACK_SYSTEM_PROMPT
        print(f"[No system prompt found at {args.system_prompt}, "
              f"using a built-in default for the default persona]")

    personas, warnings = load_personas(project_path(args.personas_dir), default_prompt)
    for warning in warnings:
        print(f"[Warning: {warning}]")

    persona_id = resolve_persona(args.persona, personas)
    if persona_id is None:
        print(f"[Warning: unknown persona '{args.persona}', "
              f"falling back to '{DEFAULT_PERSONA_ID}']")
        persona_id = DEFAULT_PERSONA_ID

    token_limit_action, action_warning = parse_limit_action(args.on_token_limit)
    if action_warning:
        print(f"[Warning: {action_warning}]")

    temperature, temperature_error = parse_temperature(args.temperature)
    if temperature_error:
        print(f"[Warning: {temperature_error} Using the model default.]")

    seed, seed_error = parse_seed(args.seed)
    num_predict, num_predict_error = parse_num_predict(args.num_predict)
    for option_error in (seed_error, num_predict_error):
        if option_error:
            print(f"[Warning: {option_error} Using the model default.]")

    session = Session(
        user_id=user_id,
        conversation_id=conversation_id,
        model=args.model,
        persona_id=persona_id,
        personas=personas,
        ollama_url=args.ollama_url,
        search_motor=os.getenv("SEARCH_ENGINE", "tavily").strip().lower() or "tavily",
        token_limit_action=token_limit_action,
        show_token_usage=parse_bool(os.getenv("SHOW_TOKEN_USAGE"), True),
        temperature=temperature,
        seed=seed,
        num_predict=num_predict,
        tools_enabled=parse_bool(os.getenv("AGENT_TOOLS"), True),
        show_tool_activity=parse_bool(os.getenv("AGENT_SHOW_ACTIVITY"), True),
        email=email_of(user_id),
        account_role=role_of(user_id) or ROLE_EMPLOYEE,
    )
    refresh_profile(session)
    if session.tools_enabled:
        try:
            session.tools = build_registry(session)
        except Exception as e:  # missing tools.json, missing dependency...: chat must still work
            print(f"[Warning: tools unavailable, answering without them ({type(e).__name__}: {e})]")
    return session


def main():
    init_db()
    args = build_parser().parse_args()

    user_id = login_flow()
    conversation_id = select_conversation(user_id)
    session = build_session(args, user_id, conversation_id)

    history_count = len(load_history(session.conversation_id))
    if history_count:
        print(f"[{history_count} previous message(s) in this conversation; "
              f"context will be compressed automatically if needed]")

    if context_text(session.profile):
        print("[Your profile is added to every answer: /profile to see or change it]")
    else:
        print("[No profile yet: /profile to tell Sensai who you are (job, language, tone...)]")

    print(f"\nChatbot ready (model: {session.model}, persona: {session.persona['name']}, "
          f"temperature: {describe_temperature(session.temperature)}). "
          f"Type /help for the commands, 'exit' to quit.\n")

    while True:
        try:
            user_input = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        stripped = user_input.strip()

        if not stripped:
            print("Error: empty input. Please type something.")
            continue

        if stripped.lower() in ("exit", "/exit"):
            print("Goodbye.")
            break

        if handle_command(session, stripped):
            continue

        with session.out.interruptible():
            chat_turn(session, user_input)


if __name__ == "__main__":
    main()