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
from Memories.Compression import build_context
from Memories.Conversations import (
    create_conversation,
    list_conversations,
)
from Runtime.Personas import DEFAULT_PERSONA_ID, load_personas, resolve_persona
from Runtime.Models import list_models, resolve_model, looks_like_embedding_model

FALLBACK_SYSTEM_PROMPT = "You are Sensai, a helpful assistant."

HELP_TEXT = """Available commands:
  /help                 show this help
  /new                  start a new conversation
  /conversations        list your conversations and switch to one
  /personas             list the available personas
  /persona [id|number]  show the current persona, or switch to another one
  /models               list the models installed in Ollama
  /model [name|number]  show the current model, or switch to another one
  exit                  quit

Switching persona or model keeps the conversation history."""


@dataclass
class Session:
    """State that can change while the chatbot is running."""
    user_id: str
    conversation_id: int
    model: str
    persona_id: str
    personas: dict
    ollama_url: str

    @property
    def persona(self) -> dict:
        return self.personas[self.persona_id]


def load_system_prompt(path: str) -> str | None:
    """Load a system prompt from a text file. Returns None if not found."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return content if content else None
    except FileNotFoundError:
        return None


def call_ollama(base_url: str, model: str, messages: list) -> str | None:
    """Send the full message history to Ollama and stream the response.
    Returns the full assistant reply as a string, or None if the call failed."""
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
                break
    except requests.exceptions.ChunkedEncodingError:
        print("\nError: connection interrupted while streaming.")
        return None

    print()  # saut de ligne final
    return full_reply


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


# ---------------------------------------------------------------------
# Slash commands (persona / model switching at runtime)
# ---------------------------------------------------------------------

def print_personas(session: Session) -> None:
    print("=== Personas ===")
    for i, (persona_id, persona) in enumerate(session.personas.items(), start=1):
        marker = "*" if persona_id == session.persona_id else " "
        description = f" — {persona['description']}" if persona["description"] else ""
        print(f"{marker} {i}. {persona_id}: {persona['name']}{description}")
    print("(* = active)  Switch with /persona <id or number>")


def switch_persona(session: Session, requested: str) -> None:
    if not requested:
        print(f"Current persona: {session.persona['name']} ({session.persona_id})")
        print_personas(session)
        return

    persona_id = resolve_persona(requested, session.personas)
    if persona_id is None:
        print(f"Error: unknown persona '{requested}'. Type /personas to see the list.")
        return

    session.persona_id = persona_id
    print(f"Persona switched to '{session.persona['name']}'. "
          f"The conversation history is kept.")


def print_models(session: Session, installed: list[str]) -> None:
    print("=== Models installed in Ollama ===")
    if not installed:
        print("(none — pull one with: ollama pull <name>)")
    # Ollama resolves "llama3" to "llama3:latest", so the active model may be
    # configured without its tag and still be installed.
    active = resolve_model(session.model, installed)
    for i, name in enumerate(installed, start=1):
        marker = "*" if name == active else " "
        note = "   (embedding model, not usable for chat)" if looks_like_embedding_model(name) else ""
        print(f"{marker} {i}. {name}{note}")
    if active is None:
        print(f"Note: the current model '{session.model}' is not in this list.")
    print("(* = active)  Switch with /model <name or number>")


def show_models(session: Session) -> None:
    try:
        installed = list_models(session.ollama_url)
    except RuntimeError as e:
        print(f"Error: {e}")
        return
    print_models(session, installed)


def switch_model(session: Session, requested: str) -> None:
    if not requested:
        print(f"Current model: {session.model}")
        show_models(session)
        return

    try:
        installed = list_models(session.ollama_url)
    except RuntimeError as e:
        print(f"Error: {e} (model unchanged: {session.model})")
        return

    model = resolve_model(requested, installed)
    if model is None:
        print(f"Error: model '{requested}' is not installed. "
              f"Pull it with: ollama pull {requested}")
        print_models(session, installed)
        return

    if looks_like_embedding_model(model):
        print(f"Warning: '{model}' looks like an embedding model and may not "
              f"be able to answer chat messages.")

    session.model = model
    print(f"Model switched to '{session.model}'. The conversation history is kept.")


def handle_command(session: Session, text: str) -> bool:
    """Run a slash command if `text` is one. Returns True when the input
    was a command (and must NOT be sent to the model), False otherwise."""
    if not text.startswith("/"):
        return False

    command, _, argument = text.partition(" ")
    command = command.lower()
    argument = argument.strip()

    if command == "/help":
        print(HELP_TEXT)
    elif command == "/new":
        title = prompt_new_conversation_title()
        session.conversation_id = create_conversation(session.user_id, title)
        print(f"Started new conversation #{session.conversation_id}.\n")
    elif command == "/conversations":
        session.conversation_id = select_conversation(session.user_id)
    elif command == "/personas":
        print_personas(session)
    elif command == "/persona":
        switch_persona(session, argument)
    elif command == "/models":
        show_models(session)
    elif command == "/model":
        switch_model(session, argument)
    else:
        print(f"Unknown command '{command}'. Type /help to see the available commands.")
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

    session = Session(
        user_id=user_id,
        conversation_id=conversation_id,
        model=args.model,
        persona_id=persona_id,
        personas=personas,
        ollama_url=args.ollama_url,
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

        # Context built fresh from SQLite every turn, scoped to the
        # active conversation (summary + recent messages, compressed if
        # needed). The system prompt comes from the ACTIVE persona and the
        # model is the ACTIVE model, so both can change between two turns
        # without touching the stored history. The current input is
        # appended only in-memory, and only saved to DB once we have a reply.
        context = build_context(
            session.conversation_id,
            session.persona["system_prompt"],
            session.model,
            session.ollama_url,
        )
        context.append({"role": "user", "content": user_input})

        print("Assistant: ", end="", flush=True)
        reply = call_ollama(session.ollama_url, session.model, context)

        if reply is None:
            # Nothing was persisted yet for this turn, so there is nothing
            # to roll back — just let the user retry.
            continue

        save_message(session.conversation_id, "user", user_input)
        save_message(session.conversation_id, "assistant", reply)


if __name__ == "__main__":
    main()