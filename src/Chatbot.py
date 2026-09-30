import requests
import json
import argparse
import os
from dotenv import load_dotenv


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
    Returns the full assistant reply as a string (to append to history),
    or None if the call failed."""
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


def main():
    load_dotenv()  # charge les variables depuis le fichier .env

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

    messages = []

    system_prompt = load_system_prompt(args.system_prompt)
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
        print(f"[System prompt loaded from {args.system_prompt}]")
    else:
        print(f"[No system prompt found at {args.system_prompt}, continuing without one]")

    print(f"Chatbot ready (model: {args.model}). Type 'exit' to quit.\n")

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

        print("Assistant: ", end="", flush=True)
        reply = call_ollama(args.ollama_url, args.model, messages)

        if reply is None:
            # Connection or model error: drop the last user message so it
            # doesn't pollute history with an unanswered turn, but keep chatting.
            messages.pop()
            continue

        messages.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    main()