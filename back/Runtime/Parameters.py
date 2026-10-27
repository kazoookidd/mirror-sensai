"""
Runtime generation parameters.

The temperature: how creative (high) or deterministic (low) the answers of
the chat are. It is configured at startup (TEMPERATURE in .env or
--temperature) and can be changed at any time with /temperature.

Two more options of the model, same life cycle (SEED / NUM_PREDICT in
.env, --seed / --num-predict, then /settings):
  * seed         same seed + same question + same settings = same answer
  * num_predict  maximum length of an answer, in tokens

For every one of them None means "do not send anything": Ollama then uses
the default of the model. It is the default, so nothing changes for users
who never touch the settings.
"""

MIN_TEMPERATURE = 0.0
MAX_TEMPERATURE = 2.0

MIN_SEED = 0
MAX_SEED = 2**31 - 1
MIN_NUM_PREDICT = 1
MAX_NUM_PREDICT = 32768

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


def _parse_whole_number(value, name: str, low: int, high: int) -> tuple[int | None, str | None]:
    """Shared by seed and num_predict. Same contract as
    parse_temperature: (value, error), nothing is clamped, and a decimal
    ("2.5") is an error rather than a silent rounding."""
    if value is None:
        return None, None
    text = str(value).strip().lower()
    if text in _DEFAULT_WORDS:
        return None, None
    try:
        number = int(text)
    except ValueError:
        return None, f"'{value}' is not a whole number (expected {low} to {high})."
    if not low <= number <= high:
        return None, f"{name} {value} is out of range (expected {low} to {high})."
    return number, None


def parse_seed(value) -> tuple[int | None, str | None]:
    return _parse_whole_number(value, "seed", MIN_SEED, MAX_SEED)


def parse_num_predict(value) -> tuple[int | None, str | None]:
    return _parse_whole_number(value, "num-predict", MIN_NUM_PREDICT, MAX_NUM_PREDICT)


def describe_option(value: int | None) -> str:
    """Human-readable value of seed / num_predict."""
    return "model default" if value is None else str(value)


def generation_options(seed: int | None = None, num_predict: int | None = None) -> dict:
    """The options to send to Ollama: only the ones that are set (0 is set)."""
    options = {"seed": seed, "num_predict": num_predict}
    return {key: value for key, value in options.items() if value is not None}
