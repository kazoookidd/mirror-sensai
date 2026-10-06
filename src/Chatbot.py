import requests
import json
import argparse
import os
import getpass
from dotenv import load_dotenv

from Memories.Database import init_db
from Memories.Auth import get_or_create_user
from Memories.Memory import save_message, load_history
from Memories.Compression import build_context
from Memories.Conversations import (
    create_conversation,
    list_conversations,
)
from Filesystem.Operations import cli_confirm
from Filesystem.Tools import TOOL_DEFINITIONS, build_filesystem, execute_tool


def load_system_prompt(path: str) -> str | None:
    """Load a system prompt from a text file. Returns None if not found."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return content if content else None
    except FileNotFoundError:
        return None


class ToolsNotSupported(Exception):
    pass


def call_ollama(base_url: str, model: str, messages: list, tools: list | None = None):
    """Send the full message history to Ollama and stream the response.
    Returns (reply_text, tool_calls) or None if the call failed.
    Raises ToolsNotSupported if the model rejects the `tools` parameter."""
    payload = {"model": model, "messages": messages, "stream": True}
    if tools:
        payload["tools"] = tools

    try:
        response = requests.post(f"{base_url}/api/chat", json=payload, stream=True)
        if response.status_code == 400 and tools and "does not support tools" in response.text:
            raise ToolsNotSupported()
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        print("Error: cannot connect to Ollama. Is it running? (ollama serve)")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"Error: model unavailable or bad request ({e})")
        return None

    full_reply = ""
    tool_calls = []
    started = False
    try:
        for line in response.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)

            if "error" in chunk:
                print(f"Error from Ollama: {chunk['error']}")
                return None

            message = chunk.get("message", {})
            content = message.get("content", "")
            if content:
                if not started:
                    print("Assistant: ", end="", flush=True)
                    started = True
                print(content, end="", flush=True)
                full_reply += content
            tool_calls.extend(message.get("tool_calls") or [])
            if chunk.get("done"):
                break
    except requests.exceptions.ChunkedEncodingError:
        print("\nError: connection interrupted while streaming.")
        return None

    if started:
        print()  # saut de ligne final
    return full_reply, tool_calls


MAX_TOOL_ROUNDS = 5


def run_turn(base_url: str, model: str, context: list, fs, tools_enabled: bool):
    """Call the model, execute any tool calls it makes (through the permission
    layer) and loop until it produces a final answer.
    Returns (reply, tools_enabled), reply being None on failure."""
    for _ in range(MAX_TOOL_ROUNDS + 1):
        try:
            result = call_ollama(base_url, model, context, TOOL_DEFINITIONS if tools_enabled else None)
        except ToolsNotSupported:
            print(f"[Model '{model}' does not support tools: file access disabled]")
            tools_enabled = False
            continue

        if result is None:
            return None, tools_enabled

        reply, tool_calls = result
        if not tool_calls:
            return reply, tools_enabled

        context.append({"role": "assistant", "content": reply, "tool_calls": tool_calls})
        for call in tool_calls:
            function = call.get("function", {})
            name = function.get("name", "")
            arguments = function.get("arguments") or {}
            print(f"[Tool] {name}({', '.join(f'{k}={v!r}' for k, v in arguments.items() if k != 'content')})")
            output = execute_tool(fs, name, arguments)
            context.append({"role": "tool", "tool_name": name, "content": output})

    print("Error: too many consecutive tool calls, giving up on this turn.")
    return None, tools_enabled


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


def prompt_new_conversation_title() -> str | None:
    title = input("Title for this conversation (optional, press Enter to skip): ").strip()
    return title or None


def select_conversation(user_id: str) -> int:
    """Show the user's existing conversations and let them pick one, or
    start a new one. Returns the chosen conversation_id."""
    conversations = list_conversations(user_id)

    print("=== Conversations ===")
    if conversations:
        for i, conv in enumerate(conversations, start=1):
            print(f"{i}. {conv['title']}  (last updated: {conv['updated_at']})")
    else:
        print("(No conversations yet)")

    choice = input(
        "Enter a number to resume a conversation, "
        "or press Enter to start a new one: "
    ).strip()

    if not choice:
        title = prompt_new_conversation_title()
        conversation_id = create_conversation(user_id, title)
        print(f"Started new conversation #{conversation_id}.\n")
        return conversation_id

    try:
        index = int(choice)
        if 1 <= index <= len(conversations):
            conv = conversations[index - 1]
            print(f"Resuming conversation '{conv['title']}'.\n")
            return conv["id"]
    except ValueError:
        pass

    print("Invalid choice, starting a new conversation instead.")
    conversation_id = create_conversation(user_id)
    return conversation_id


def main():
    load_dotenv()
    init_db()

    parser = argparse.ArgumentParser(description="Sensai CLI chatbot")
    parser.add_argument(
        "--model",
        default=os.getenv("MODEL", "llama3"),
        help="Ollama model name (overrides .env MODEL if provided)"
    )
    parser.add_argument(
        "--system-prompt",
        default=os.getenv("SYSTEM_PROMPT_PATH", "system_prompt.txt"),
        help="Path to the system prompt file (overrides .env SYSTEM_PROMPT_PATH)"
    )
    parser.add_argument(
        "--ollama-url",
        default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        help="Base URL of the Ollama server"
    )
    args = parser.parse_args()

    user_id = login_flow()
    conversation_id = select_conversation(user_id)

    fs = build_filesystem(confirm=cli_confirm, user_id=user_id)
    tools_enabled = True

    system_prompt = load_system_prompt(args.system_prompt)
    if system_prompt:
        print(f"[System prompt loaded from {args.system_prompt}]")
    else:
        system_prompt = ""
        print(f"[No system prompt found at {args.system_prompt}, continuing without one]")

    history_count = len(load_history(conversation_id))
    if history_count:
        print(f"[{history_count} previous message(s) in this conversation "
              f"- context will be compressed automatically if needed]")

    print(f"\nChatbot ready (model: {args.model}). "
          f"Type 'exit' to quit, '/new' for a new conversation, "
          f"'/conversations' to switch.\n")

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

        if stripped.lower() == "exit":
            print("Goodbye.")
            break

        if stripped.lower() == "/new":
            title = prompt_new_conversation_title()
            conversation_id = create_conversation(user_id, title)
            print(f"Started new conversation #{conversation_id}.\n")
            continue

        if stripped.lower() == "/conversations":
            conversation_id = select_conversation(user_id)
            continue

        # Context built fresh from SQLite every turn, scoped to the
        # active conversation (summary + recent messages, compressed if
        # needed). The current input is appended only in-memory, and
        # only saved to DB once we have a reply.
        context = build_context(conversation_id, system_prompt, args.model, args.ollama_url)
        context.append({"role": "user", "content": user_input})

        reply, tools_enabled = run_turn(args.ollama_url, args.model, context, fs, tools_enabled)

        if reply is None:
            # Nothing was persisted yet for this turn, so there is nothing
            # to roll back - just let the user retry.
            continue

        save_message(conversation_id, "user", user_input)
        save_message(conversation_id, "assistant", reply)


if __name__ == "__main__":
    main()