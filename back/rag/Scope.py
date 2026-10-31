"""
[R2] Metadata filter of the HR documents: search only some documents (by name) or some types.
The same rules for /scope in the CLI and the web interface.
"""

from rag.Loader import SUPPORTED_EXTENSIONS

TYPES = tuple(sorted(extension.lstrip(".") for extension in SUPPORTED_EXTENSIONS))


def make_scope(sources: list[str], types: list[str], known: list[str]) -> tuple[dict | None, str | None]:
    """The scope for these documents and types (None: every document), or an error naming what is unknown."""
    unknown = [name for name in sources if name not in known]
    if unknown:
        return None, f"unknown document: {', '.join(unknown)}."
    types = [kind.lower().lstrip(".") for kind in types]
    wrong = [kind for kind in types if kind not in TYPES]
    if wrong:
        return None, f"unknown type: {', '.join(wrong)} (expected: {', '.join(TYPES)})."
    if not sources and not types:
        return None, None
    return {"sources": list(dict.fromkeys(sources)), "types": list(dict.fromkeys(types))}, None


def parse_scope(words: list[str], known: list[str]) -> tuple[dict | None, str | None]:
    """/scope a.md b.md pdf: the words that are a type (pdf, md, txt) filter by type, the others are names."""
    types = [word for word in words if word.lower().lstrip(".") in TYPES and word not in known]
    return make_scope([word for word in words if word not in types], types, known)


def describe_scope(scope: dict | None) -> str:
    if not scope:
        return "every HR document"
    parts = list(scope["sources"]) + [f"every .{kind} file" for kind in scope["types"]]
    return ", ".join(parts)
