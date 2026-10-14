"""
[A5] Personas.

A persona is a named system prompt (a "métier" profile) that can be
selected and switched at runtime. Personas live as one JSON file each in a
directory, so adding or editing one never requires touching the code:

    personas/hr_onboarding.json
    {
        "name": "Onboarding Buddy",
        "description": "Short one-line description shown in /personas",
        "system_prompt": "You are ..."
    }

The persona id is the file name without extension (hr_onboarding).

A built-in "default" persona always exists. Its prompt comes from the
regular system prompt file (system_prompt.txt) unless a personas/default.json
is provided, in which case that file wins.
"""

import json
from pathlib import Path

DEFAULT_PERSONA_ID = "default"
DEFAULT_PERSONA_NAME = "Sensai (default)"
DEFAULT_PERSONA_DESCRIPTION = "General-purpose assistant (system_prompt.txt)."


def _load_persona_file(path: Path) -> tuple[dict | None, str | None]:
    """Parse and validate one persona file.
    Returns (persona, None) on success or (None, error_message) on failure."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:  # ValueError covers JSON + unicode errors
        return None, f"cannot be read as JSON ({e})"

    if not isinstance(data, dict):
        return None, "must contain a JSON object"

    name = data.get("name")
    system_prompt = data.get("system_prompt")
    description = data.get("description", "")

    if not isinstance(name, str) or not name.strip():
        return None, "missing or empty 'name'"
    if not isinstance(system_prompt, str) or not system_prompt.strip():
        return None, "missing or empty 'system_prompt'"
    if not isinstance(description, str):
        return None, "'description' must be a string"

    return {
        "id": path.stem,
        "name": name.strip(),
        "description": description.strip(),
        "system_prompt": system_prompt.strip(),
    }, None


def load_personas(personas_dir: str, default_prompt: str) -> tuple[dict[str, dict], list[str]]:
    """Load every persona found in `personas_dir`.

    Returns (personas, warnings):
    - personas: ordered dict {persona_id: persona}, the default persona
      first, then the others sorted by id (this order drives the numbers
      shown by /personas).
    - warnings: human-readable problems (missing directory, invalid file).
      Invalid files are skipped, never fatal.
    """
    warnings: list[str] = []
    loaded: dict[str, dict] = {}

    directory = Path(personas_dir)
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            persona, error = _load_persona_file(path)
            if error:
                warnings.append(f"persona file '{path.name}' skipped: {error}")
            else:
                loaded[persona["id"]] = persona
    else:
        warnings.append(
            f"personas directory '{personas_dir}' not found, "
            f"only the default persona is available"
        )

    default = loaded.pop(DEFAULT_PERSONA_ID, None) or {
        "id": DEFAULT_PERSONA_ID,
        "name": DEFAULT_PERSONA_NAME,
        "description": DEFAULT_PERSONA_DESCRIPTION,
        "system_prompt": default_prompt,
    }

    personas = {DEFAULT_PERSONA_ID: default}
    personas.update(loaded)
    return personas, warnings


def resolve_persona(requested: str, personas: dict[str, dict]) -> str | None:
    """Turn what the user typed into a persona id, or None if it matches
    nothing. Accepts the list number (as shown by /personas), the id, or
    the display name, case-insensitively."""
    requested = requested.strip()
    if not requested:
        return None

    ids = list(personas.keys())

    if requested.isdigit():
        index = int(requested)
        return ids[index - 1] if 1 <= index <= len(ids) else None

    wanted = requested.lower()
    for persona_id, persona in personas.items():
        if wanted == persona_id.lower() or wanted == persona["name"].lower():
            return persona_id
    return None