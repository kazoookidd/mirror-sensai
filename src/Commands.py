"""
Interactive side of the CLI: the session state and the slash commands.

Chatbot.py owns the startup and the chat loop; everything the user can
type that starts with "/" (and the conversation picker it relies on) lives
here, so the two files can evolve independently.
"""

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from Memories.Conversations import (
    create_conversation,
    list_conversations,
)
from Memories.TokenLimit import DEFAULT_ACTION
from StructuredOutput.Extractor import StructuredOutputError, extract_leave_request
from StructuredOutput.Store import list_leave_requests, save_leave_request
from Runtime.Personas import resolve_persona
from Runtime.Parameters import (
    MAX_TEMPERATURE,
    MIN_TEMPERATURE,
    describe_temperature,
    generation_options,
    parse_temperature,
)
from Runtime.Settings import (
    SETTINGS,
    apply_setting,
    current_value,
    find_setting,
)
from Runtime.Models import list_models, resolve_model, looks_like_embedding_model
from Tools.web_search import print_search_moteur, switch_search_motor
from rag.Store import DEFAULT_DOCS_DIR, index_directory
from Cache.Chat import get_cache, invalidate as invalidate_cache

HELP_TEXT = """Available commands:
  /help                         show this help
  /new                          start a new conversation
  /conversations                list your conversations and switch to one
  /personas                     list the available personas
  /persona [id|number]          show the current persona, or switch to another one
  /models                       list the models installed in Ollama
  /model [name|number]          show the current model, or switch to another one
  /temperature [value|default]  show or set how creative the answers are (0 to 2)
  /settings [name [value]]      list the settings, or show/change one
                                (e.g. /settings seed 42, /settings num-predict 300,
                                /settings token-limit continue)
  /switch_search [name|number]  switch the search motor
  /search                       list the search motors
  /leave <your request>         file a leave request in plain language
                                (e.g. /leave I take Nov 3 to 7 for a holiday)
  /leaves                       list the leave requests you have filed
  /ingest [folder]              index HR documents so answers can use them (default: data/docs)
  /cache [clear]                show the semantic cache, or empty it
  exit                          quit


Switching persona, model or any setting keeps the conversation history.
/set is accepted as an alias of /settings.
(/leave always runs at temperature 0 so its result is reproducible.)
/conge and /conges are accepted as aliases of /leave and /leaves."""


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
    # Sampling temperature of the chat answers; None = the model's default
    temperature: float | None = None
    # Let the model use its tools (web search...) when it judges it useful
    tools_enabled: bool = True
    # ToolRegistry built at startup (None = no tools available), see Agents/Setup.py
    tools: object | None = None
    # Print a dimmed line for each tool the agent uses
    show_tool_activity: bool = True
    # More options of the model, None = the model's default (see Runtime/Parameters.py)
    # [A6] answer questions that mean the same as an earlier one from the cache
    semantic_cache: bool = True
    seed: int | None = None
    num_predict: int | None = None

    @property
    def persona(self) -> dict:
        return self.personas[self.persona_id]

    def model_options(self) -> dict:
        """seed / num_predict to send to Ollama (only those that are set).
        The temperature travels on its own, like before."""
        return generation_options(self.seed, self.num_predict)


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
        description = f" : {persona['description']}" if persona["description"] else ""
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
        print("(none, pull one with: ollama pull <name>)")
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


# ---------------------------------------------------------------------
# Leave requests (structured output)
# ---------------------------------------------------------------------

def file_leave_request(session: Session, text: str) -> None:
    if not text:
        print("Usage: /leave <your request in plain language>")
        print("Example: /leave I take Nov 3 to 7 for a holiday")
        return

    print("Analysing your request...")
    try:
        data = extract_leave_request(text, session.ollama_url, session.model)
    except StructuredOutputError as e:
        print(f"Error: {e}")
        print("Nothing was saved.")
        return

    try:
        request_id = save_leave_request(session.user_id, data)
    except sqlite3.Error as e:
        print(f"Error: could not save the request ({e}).")
        return

    print(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"Leave request #{request_id} saved for {session.user_id}. "
          f"See all yours with /leaves.")


def print_leave_requests(session: Session) -> None:
    try:
        requests_ = list_leave_requests(session.user_id)
    except sqlite3.Error as e:
        print(f"Error: could not read your leave requests ({e}).")
        return

    print("=== Your leave requests ===")
    if not requests_:
        print("(none yet, file one with /leave <your request>)")
        return
    for r in requests_:
        reason = f" : {r['reason']}" if r["reason"] else ""
        print(f"#{r['id']}  {r['start_date']} -> {r['end_date']}  "
              f"{r['leave_type']}{reason}")


def set_temperature(session: Session, requested: str) -> None:
    if not requested:
        print(f"Current temperature: {describe_temperature(session.temperature)}")
        print(f"Set it with /temperature <{MIN_TEMPERATURE:g} to {MAX_TEMPERATURE:g}> "
              f"(low = precise and repeatable, high = creative), "
              f"or /temperature default for the model's own value.")
        return

    temperature, error = parse_temperature(requested)
    if error:
        print(f"Error: {error} Temperature unchanged: "
              f"{describe_temperature(session.temperature)}.")
        return

    session.temperature = temperature
    print(f"Temperature set to {describe_temperature(temperature)}. "
          f"It applies to the next answers.")


def print_settings(session: Session) -> None:
    print("=== Settings ===")
    width = max(len(s.name) for s in SETTINGS)
    value_width = max(len(current_value(session, s)) for s in SETTINGS)
    for setting in SETTINGS:
        print(f"  {setting.name:<{width}}  {current_value(session, setting):<{value_width}}  "
              f"{setting.summary}")
    print("Change one with /settings <name> <value>, "
          "or see what it accepts with /settings <name>.")


def change_setting(session: Session, argument: str) -> None:
    if not argument:
        print_settings(session)
        return

    name, _, value = argument.partition(" ")
    value = value.strip()
    setting = find_setting(name)
    if setting is None:
        print(f"Error: unknown setting '{name}'.")
        print_settings(session)
        return

    if not value:
        print(f"{setting.name}: {current_value(session, setting)}")
        print(f"  {setting.summary}")
        print(f"  Accepts: {setting.accepted}")
        return

    previous = current_value(session, setting)
    new_value, error = apply_setting(session, setting, value)
    if error:
        print(f"Error: {error} {setting.name} unchanged: {previous}.")
        print(f"  Accepts: {setting.accepted}")
        return
    print(f"{setting.name} set to {new_value}. It applies to the next answers.")


def ingest_documents(argument: str) -> None:
    """Index a folder of documents for the RAG."""
    folder = DEFAULT_DOCS_DIR
    if argument:
        folder = Path(argument)
    if not folder.is_dir():
        print(f"Error: {folder} is not a folder. Usage: /ingest [folder]")
        return
    print(f"Indexing {folder}...")
    stats = index_directory(folder)
    if stats["failed"]:
        print("Indexing stopped: Ollama did not answer.")
        return
    print(f"{stats['indexed']} document(s) indexed ({stats['chunks']} chunks), "
          f"{stats['unchanged']} unchanged, {stats['removed']} removed.")
    # The cached answers were written from the OLD documents: forget them.
    removed = invalidate_cache()
    if removed:
        print(f"{removed} cached answer(s) forgotten (the documents changed).")


def cache_command(session: Session, argument: str) -> None:
    cache = get_cache(session)
    if argument.strip().lower() == "clear":
        print(f"{cache.clear(session.user_id)} cached answer(s) removed.")
        return
    stats = cache.stats(session.user_id)
    state = "on" if session.semantic_cache else "off"
    print(f"=== Semantic cache ({state}) ===")
    print(f"  entries: {stats['entries']}   hits so far: {stats['hits']}   scope: {stats['scope']}")
    print(f"  similarity threshold: {stats['threshold']:g}   expires after: "
          f"{'never' if not stats['ttl_hours'] else str(int(stats['ttl_hours'])) + ' h'}   "
          f"embedding model: {stats['embed_model']}")
    if cache.unavailable_reason:
        print(f"  unavailable: {cache.unavailable_reason}")
    print("Turn it on or off with /settings cache on|off, empty it with /cache clear.")


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
    elif command == "/temperature":
        set_temperature(session, argument)
    elif command in ("/settings", "/set"):
        change_setting(session, argument)
    elif command in ("/leave", "/conge"):
        file_leave_request(session, argument)
    elif command in ("/leaves", "/conges"):
        print_leave_requests(session)
    elif command == "/ingest":
        ingest_documents(argument)
    elif command == "/cache":
        cache_command(session, argument)
    else:
        print(f"Unknown command '{command}'. Type /help to see the available commands.")
    return True