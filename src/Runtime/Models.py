"""
Runtime model selection.

Lists the models installed on the Ollama server (GET /api/tags) and
resolves what the user typed to an installed model name, so the model can
be switched in the middle of a session without restarting.
"""

import requests

TAGS_TIMEOUT_SECONDS = 10


def list_models(base_url: str) -> list[str]:
    """Return the names of the models installed on the Ollama server,
    sorted alphabetically (stable numbering for /models).
    Raises RuntimeError with a user-presentable message on any failure."""
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=TAGS_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.ConnectionError:
        raise RuntimeError("cannot connect to Ollama. Is it running? (ollama serve)")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"could not list models ({e})")
    except ValueError:
        raise RuntimeError("Ollama returned an invalid response when listing models.")

    if not isinstance(data, dict):
        raise RuntimeError("Ollama returned an unexpected response when listing models.")

    names = [m.get("name") for m in data.get("models", []) if isinstance(m, dict)]
    return sorted(name for name in names if name)


def resolve_model(requested: str, installed: list[str]) -> str | None:
    """Turn what the user typed into an installed model name, or None.

    Accepts the list number (as shown by /models), the exact name, or a
    name without tag ("llama3" matches "llama3:latest", the same way
    Ollama itself resolves it)."""
    requested = requested.strip()
    if not requested:
        return None

    if requested.isdigit():
        index = int(requested)
        return installed[index - 1] if 1 <= index <= len(installed) else None

    if requested in installed:
        return requested
    if ":" not in requested and f"{requested}:latest" in installed:
        return f"{requested}:latest"
    return None


def looks_like_embedding_model(name: str) -> bool:
    """Heuristic, display only: embedding models (needed by RAG) show up in
    the same list as chat models but cannot answer a chat request."""
    return "embed" in name.lower()