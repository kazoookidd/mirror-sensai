"""
Interactive side of the CLI: the session state and the slash commands.

Chatbot.py owns the startup and the chat loop; everything the user can
type that starts with "/" (and the conversation picker it relies on) lives
here, so the two files can evolve independently.
"""

from dataclasses import dataclass

from Memories.Conversations import (
    create_conversation,
    list_conversations,
)
from Memories.TokenLimit import DEFAULT_ACTION
from Runtime.Personas import resolve_persona
from Runtime.Models import list_models, resolve_model, looks_like_embedding_model
from Tools.web_search import print_search_moteur, switch_search_motor

HELP_TEXT = """Available commands:
  /help                         show this help
  /new                          start a new conversation
  /conversations                list your conversations and switch to one
  /personas                     list the available personas
  /persona [id|number]          show the current persona, or switch to another one
  /models                       list the models installed in Ollama
  /model [name|number]          show the current model, or switch to another one
  /switch_search [name|number]  switch the search motor
  /search                       list the search motors
  exit                          quit


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
    search_motor : str
    # What to do when the context is over the token limit: "block" or "continue"
    token_limit_action: str = DEFAULT_ACTION
    # Show the small token usage line under each answer
    show_token_usage: bool = True

    @property
    def persona(self) -> dict:
        return self.personas[self.persona_id]


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
    elif command == "/search":
        print_search_moteur(session)
    elif command == "/switch_search":
        switch_search_motor(session, argument)
    else:
        print(f"Unknown command '{command}'. Type /help to see the available commands.")
    return True