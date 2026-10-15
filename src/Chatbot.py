import requests
import json
import argparse
import os
import getpass
from dataclasses import dataclass
from dotenv import load_dotenv

from Memories.Database import init_db
from Memories.Auth import get_or_create_user
from Memories.Memory import save_message, load_history
from Memories.Compression import build_context, estimate_tokens
from Memories.TokenLimit import (
    ACTION_BLOCK,
    LIMIT_ACTIONS,
    blocked_message,
    estimate_context_tokens,
    format_usage,
    is_over_limit,
    parse_bool,
    parse_limit_action,
    small,
    warning_message,
)
from Runtime.Personas import DEFAULT_PERSONA_ID, load_personas, resolve_persona
from Commands import Session, handle_command, select_conversation

FALLBACK_SYSTEM_PROMPT = "You are Sensai, a helpful assistant."


@dataclass
class Reply:
    """A completed answer from the model, with the token counts Ollama
    reports in its last streamed chunk (None when it did not report them)."""
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


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


def call_ollama(base_url: str, model: str, messages: list) -> Reply | None:
    """Send the full message history to Ollama and stream the response.
    Returns the full answer with its token counts, or None if the call failed."""
    try:
        response = requests.post(
            f"{base_url}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": True
            },
            stream=True
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        print("Error: cannot connect to Ollama. Is it running? (ollama serve)")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"Error: model unavailable or bad request ({e})")
        return None

    full_reply = ""
    prompt_tokens = None
    completion_tokens = None
    try:
        for line in response.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)

            if "error" in chunk:
                print(f"Error from Ollama: {chunk['error']}")
                return None

            content = chunk.get("message", {}).get("content", "")
            print(content, end="", flush=True)
            full_reply += content
            if chunk.get("done"):
                # Only the last chunk carries the real token counts.
                prompt_tokens = _as_count(chunk.get("prompt_eval_count"))
                completion_tokens = _as_count(chunk.get("eval_count"))
                break
    except requests.exceptions.ChunkedEncodingError:
        print("\nError: connection interrupted while streaming.")
        return None

    print()  # saut de ligne final
    return Reply(full_reply, prompt_tokens, completion_tokens)


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

        print(f"Account created for {user['user_id']}.\n")
        return user["user_id"]


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
    context = build_context(
        session.conversation_id,
        session.persona["system_prompt"],
        session.model,
        session.ollama_url,
    )
    context.append({"role": "user", "content": user_input})

    # Token limit: compression had its chance, this is what is left.
    context_tokens = estimate_context_tokens(context)
    if is_over_limit(context_tokens):
        if session.token_limit_action == ACTION_BLOCK:
            print(blocked_message(context_tokens))
            return False
        print(warning_message(context_tokens))

    print("Assistant: ", end="", flush=True)
    reply = call_ollama(session.ollama_url, session.model, context)

    if reply is None:
        # Nothing was persisted yet for this turn, so there is nothing
        # to roll back — just let the user retry.
        return False

    save_message(session.conversation_id, "user", user_input)
    save_message(session.conversation_id, "assistant", reply.text)

    if session.show_token_usage:
        # Prefer Ollama's own counts; fall back to the estimate if absent.
        approximate = reply.prompt_tokens is None or reply.completion_tokens is None
        prompt_tokens = reply.prompt_tokens if reply.prompt_tokens is not None else context_tokens
        completion_tokens = (
            reply.completion_tokens if reply.completion_tokens is not None
            else estimate_tokens(reply.text)
        )
        print(small(format_usage(prompt_tokens, completion_tokens, approximate)))
    return True


def main():
    load_dotenv()
    init_db()

    parser = argparse.ArgumentParser(description="Sensai CLI chatbot")
    parser.add_argument(
        "--model",
        default=os.getenv("MODEL", "llama3"),
        help="Ollama model name at startup (overrides .env MODEL). "
             "Can be changed at runtime with /model"
    )
    parser.add_argument(
        "--system-prompt",
        default=os.getenv("SYSTEM_PROMPT_PATH", "system_prompt.txt"),
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
        default=os.getenv("PERSONAS_DIR", "personas"),
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
    args = parser.parse_args()

    user_id = login_flow()
    conversation_id = select_conversation(user_id)

    default_prompt = load_system_prompt(args.system_prompt)
    if default_prompt:
        print(f"[System prompt loaded from {args.system_prompt}]")
    else:
        default_prompt = FALLBACK_SYSTEM_PROMPT
        print(f"[No system prompt found at {args.system_prompt}, "
              f"using a built-in default for the default persona]")

    personas, warnings = load_personas(args.personas_dir, default_prompt)
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

    session = Session(
        user_id=user_id,
        conversation_id=conversation_id,
        model=args.model,
        persona_id=persona_id,
        personas=personas,
        ollama_url=args.ollama_url,
        search_motor="tavily",
        token_limit_action=token_limit_action,
        show_token_usage=parse_bool(os.getenv("SHOW_TOKEN_USAGE"), True),
    )

    history_count = len(load_history(session.conversation_id))
    if history_count:
        print(f"[{history_count} previous message(s) in this conversation "
              f"— context will be compressed automatically if needed]")

    print(f"\nChatbot ready (model: {session.model}, persona: {session.persona['name']}). "
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

        chat_turn(session, user_input)


if __name__ == "__main__":
    main()