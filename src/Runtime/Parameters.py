"""
Runtime generation parameters.

For now only the temperature: how creative (high) or deterministic (low)
the answers of the chat are. It is configured at startup (TEMPERATURE in
.env or --temperature) and can be changed at any time with /temperature.

None means "do not send anything": Ollama then uses the default of the
model (usually 0.8). It is the default, so nothing changes for users who
never touch the setting.

The structured output ([T5], /leave) always runs at temperature 0 so its
result is reproducible; this setting does not apply to it.
"""

MIN_TEMPERATURE = 0.0
MAX_TEMPERATURE = 2.0

_DEFAULT_WORDS = {"default", "auto", "none", "reset", ""}


def parse_temperature(value) -> tuple[float | None, str | None]:
    """Turn what the user (or .env) typed into a temperature.

    Returns (temperature, error). Exactly one of them is None, except for
    "use the model default" where both are None. A decimal comma is
    accepted ("0,7"). Nothing is clamped: an out-of-range value is an error,
    so the user never gets a different temperature than the one asked."""
    if value is None:
        return None, None
    text = str(value).strip().lower()
    if text in _DEFAULT_WORDS:
        return None, None

    try:
        temperature = float(text.replace(",", "."))
    except ValueError:
        return None, f"'{value}' is not a number (expected {MIN_TEMPERATURE:g} to {MAX_TEMPERATURE:g})."

    # float() accepts "nan" and "inf"; neither is a usable temperature.
    if not MIN_TEMPERATURE <= temperature <= MAX_TEMPERATURE:
        return None, (f"temperature {value} is out of range "
                      f"(expected {MIN_TEMPERATURE:g} to {MAX_TEMPERATURE:g}).")
    return temperature, None


def describe_temperature(temperature: float | None) -> str:
    """Human-readable value, for /temperature and the startup line."""
    if temperature is None:
        return "model default"
    if temperature == 0:
        return "0 (deterministic)"
    return f"{temperature:g}"
