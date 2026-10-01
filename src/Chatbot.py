import requests
import json
import argparse
import os
import getpass
from dotenv import load_dotenv

from Memories.Database import init_db
from Memories.Auth import get_or_create_user
from Memories.Memory import save_message, load_history


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

    # Build the context: fresh system prompt (never persisted) + stored history
    messages = []

    system_prompt = load_system_prompt(args.system_prompt)
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
        print(f"[System prompt loaded from {args.system_prompt}]")
    else:
        print(f"[No system prompt found at {args.system_prompt}, continuing without one]")

    history = load_history(user_id)
    messages.extend(history)
    if history:
        print(f"[Loaded {len(history)} previous message(s) for {user_id}]")

    print(f"\nChatbot ready (model: {args.model}). Type 'exit' to quit.\n")

    while True:
        try:
            user_input = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_input.strip():
            print("Error: empty input. Please type something.")
            continue

        if user_input.strip().lower() == "exit":
            print("Goodbye.")
            break

        messages.append({"role": "user", "content": user_input})
        save_message(user_id, "user", user_input)

        print("Assistant: ", end="", flush=True)
        reply = call_ollama(args.ollama_url, args.model, messages)

        if reply is None:
            # Connection or model error: drop the last user message so it
            # doesn't pollute in-memory context, but it's already persisted
            # in history as an unanswered turn is NOT saved here (save only
            # happens below, on success).
            messages.pop()
            continue

        messages.append({"role": "assistant", "content": reply})
        save_message(user_id, "assistant", reply)


if __name__ == "__main__":
    main()