import os
import re
from dotenv import load_dotenv
from Memories.Compression import CHARS_PER_TOKEN

load_dotenv()
DEFAULT_CHUNK_TOKENS = 500
DEFAULT_OVERLAP_TOKENS = 50
OVERLAP_SEPARATOR = "\n"
SENTENCE_END_CHARS = ".!?…"
HEADING_MAX_CHARS = 80
HEADING_END_CHARS = SENTENCE_END_CHARS + ":;,"
SMALL_CHUNK_DIVISOR = 4
_PARAGRAPH_BREAK = re.compile(r"(\n\s*\n)")
_SENTENCE_BREAK = re.compile(rf"((?<=[{re.escape(SENTENCE_END_CHARS)}])\s+)")
_LINE_BREAK = re.compile(r"(\n)")
_WORD_BREAK = re.compile(r"(\s+)")
_BREAKS = [_PARAGRAPH_BREAK, _SENTENCE_BREAK, _LINE_BREAK, _WORD_BREAK]


def _read_int_setting(name: str, default: int) -> int:
    """Integer from .env, or `default` if it is not set."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None


def _chunk_sizes(chunk_tokens: int | None, overlap_tokens: int | None) -> tuple[int, int]:
    """Chunk size and overlap, in characters."""
    if chunk_tokens is None:
        chunk_tokens = _read_int_setting("RAG_CHUNK_TOKENS", DEFAULT_CHUNK_TOKENS)
    if overlap_tokens is None:
        overlap_tokens = _read_int_setting("RAG_CHUNK_OVERLAP", DEFAULT_OVERLAP_TOKENS)
    if chunk_tokens <= 0 or not 0 <= overlap_tokens < chunk_tokens:
        raise ValueError(f"Invalid chunking config: chunk_tokens={chunk_tokens}, "f"overlap_tokens={overlap_tokens} (need 0 <= overlap < chunk size)."
        )
    return chunk_tokens * CHARS_PER_TOKEN, overlap_tokens * CHARS_PER_TOKEN


def _simplify_separator(whitespace: str) -> str:
    """Reduce whitespace to a blank line, a line break or a space."""
    line_breaks = whitespace.count("\n")
    if line_breaks >= 2:
        return "\n\n"
    if line_breaks == 1:
        return "\n"
    return " "


def _split_at(text: str, boundary: re.Pattern) -> list[tuple[str, str]]:
    """Cut `text` at `boundary`, keeping the separator before each piece."""
    parts = boundary.split(text)
    texts = parts[0::2]
    separators = [""] + parts[1::2]
    pieces = []
    whitespace = ""
    for separator, piece in zip(separators, texts):
        whitespace += separator
        if not piece.strip():
            whitespace += piece
            continue
        separator_before = ""
        if pieces:
            separator_before = _simplify_separator(whitespace)
        pieces.append((separator_before, piece.strip()))
        whitespace = ""
    return pieces


def _is_heading(piece: str) -> bool:
    """True for a markdown title or a short line without final punctuation."""
    if piece.startswith("#"):
        return True
    return (
        len(piece) <= HEADING_MAX_CHARS
        and "\n" not in piece
        and piece[-1] not in HEADING_END_CHARS
    )


def _attach_headings(pieces: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Glue each heading to the piece below it."""
    attached = []
    previous = ""
    for separator, piece in pieces:
        if attached and _is_heading(previous) and "\n" in separator:
            first_separator, text = attached[-1]
            attached[-1] = (first_separator, f"{text}{separator}{piece}")
        else:
            attached.append((separator, piece))
        previous = piece
    return attached


def _pack(pieces: list[tuple[str, str]], max_chars: int) -> list[str]:
    """Fill each chunk with as many consecutive pieces as fit."""
    chunks = []
    current = ""
    for separator, piece in pieces:
        candidate = piece
        if current:
            candidate = f"{current}{separator}{piece}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks


def _cut_every(text: str, max_chars: int) -> list[str]:
    """Cut `text` every `max_chars` characters."""
    cuts = []
    for start in range(0, len(text), max_chars):
        cut = text[start:start + max_chars].strip()
        if cut:
            cuts.append(cut)
    return cuts


def _split_text(text: str, max_chars: int, level: int = 0) -> list[str]:
    """Split `text` into chunks of at most `max_chars`, at the most natural break."""
    if len(text) <= max_chars:
        return [text]
    if level == len(_BREAKS):
        return _cut_every(text, max_chars)
    pieces = _attach_headings(_split_at(text, _BREAKS[level]))
    if len(pieces) <= 1:
        return _split_text(text, max_chars, level + 1)
    return _split_pieces(pieces, max_chars, level)


def _split_pieces(pieces: list[tuple[str, str]], max_chars: int, level: int) -> list[str]:
    """Pack the pieces that fit, split again the ones that are too long."""
    chunks = []
    fitting = []
    for separator, piece in pieces:
        if len(piece) <= max_chars:
            fitting.append((separator, piece))
            continue

        packed = _pack(fitting, max_chars)
        fitting = []
        too_long = piece
        if packed and len(packed[-1]) < max_chars // SMALL_CHUNK_DIVISOR:
            too_long = f"{packed.pop()}{separator}{piece}"
        chunks.extend(packed)
        chunks.extend(_split_text(too_long, max_chars, level + 1))

    chunks.extend(_pack(fitting, max_chars))
    return chunks


def _overlap_from(chunk: str, overlap_chars: int) -> str:
    """End of `chunk` to repeat at the start of the next one."""
    if overlap_chars <= 0 or len(chunk) <= overlap_chars:
        return ""
    end = chunk[-overlap_chars:]
    sentence_break = _SENTENCE_BREAK.search(end)
    if sentence_break:
        return end[sentence_break.end():]
    if chunk[-overlap_chars - 1].isspace():
        return end.lstrip()
    word_break = _WORD_BREAK.search(end)
    if word_break is None:
        return ""
    return end[word_break.end():]


def _add_overlap(chunks: list[str], overlap_chars: int) -> list[str]:
    """Start each chunk with the end of the previous one."""
    with_overlap = [chunks[0]]
    for previous, current in zip(chunks, chunks[1:]):
        overlap = _overlap_from(previous, overlap_chars)
        chunk = current
        if overlap:
            chunk = f"{overlap}{OVERLAP_SEPARATOR}{current}"
        with_overlap.append(chunk)
    return with_overlap


def chunk_text(text: str, chunk_tokens: int | None = None, overlap_tokens: int | None = None) -> list[str]:
    """Split `text` into overlapping chunks of at most `chunk_tokens` tokens."""
    max_chars, overlap_chars = _chunk_sizes(chunk_tokens, overlap_tokens)
    text = text.strip()
    if not text:
        return []

    room = max_chars
    if overlap_chars:
        room = max_chars - overlap_chars - len(OVERLAP_SEPARATOR)
    return _add_overlap(_split_text(text, room), overlap_chars)


def chunk_pages(pages: list[dict], chunk_tokens: int | None = None,
                overlap_tokens: int | None = None) -> list[dict]:
    """Chunk each page from rag.Loader, keeping its source and page number."""
    chunks = []
    next_index = {}
    for page in pages:
        for text in chunk_text(page["text"], chunk_tokens, overlap_tokens):
            index = next_index.get(page["source"], 0)
            next_index[page["source"]] = index + 1
            chunks.append({
                "source": page["source"],
                "page": page["page"],
                "chunk_index": index,
                "text": text,
            })
    return chunks
