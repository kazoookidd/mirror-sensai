import re
from datetime import date

_DATE_SHAPE = re.compile(r"\d{4}-\d{2}-\d{2}")

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}

def _is_type(value, expected: str) -> bool:
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES[expected])


def _is_iso_date(value: str) -> bool:
    if not _DATE_SHAPE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True

def validate(value, schema: dict, path: str = "$") -> list[str]:
    """Return the list of violations of `schema` found in `value`
    (empty list = valid). Each message starts with the path of the
    offending field, e.g. "$.start_date: ..."."""
    expected = schema.get("type")
    if expected and not _is_type(value, expected):
        return [f"{path}: expected {expected}, got {type(value).__name__}"]

    errors = []

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']}")

    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: too short (min {schema['minLength']} characters)")
        if len(value) > schema.get("maxLength", len(value)):
            errors.append(f"{path}: too long (max {schema['maxLength']} characters)")
        if schema.get("format") == "date" and not _is_iso_date(value):
            errors.append(f"{path}: {value!r} is not a valid date (expected YYYY-MM-DD)")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} is below the minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} is above the maximum {schema['maximum']}")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}: missing required field '{name}'")
        for name, item in value.items():
            if name in properties:
                errors.extend(validate(item, properties[name], f"{path}.{name}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: unexpected field '{name}'")

    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            errors.extend(validate(item, schema["items"], f"{path}[{i}]"))

    return errors
