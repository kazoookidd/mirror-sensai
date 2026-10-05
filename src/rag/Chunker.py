import os
import re
from dotenv import load_dotenv
from Memories.Compression import CHARS_PER_TOKEN

load_dotenv()
DEFAULT_CHUNK_TOKENS = int(os.getenv("RAG_CHUNK_TOKENS", "500"))
DEFAULT_OVERLAP_TOKENS = int(os.getenv("RAG_CHUNK_OVERLAP", "50"))
SENTENCE_END_CHARS = ".!?…"
HEADING_END_CHARS = SENTENCE_END_CHARS + ":;,"
ABBREVIATIONS = ("p", "art", "Art")
HEADING_MAX_CHARS = 80
CARRY_DIVISOR = 4
OVERLAP_SEPARATOR = "\n"
_SENTENCE_END = (
    rf"(?<=[{re.escape(SENTENCE_END_CHARS)}])"
    + r"(?<!\b[A-Z]\.)"
    + "".join(rf"(?<!\b{re.escape(abbreviation)}\.)" for abbreviation in ABBREVIATIONS)
    + r"(?<![\s(]\d\.)(?<![\s(]\d\d\.)(?<!^\d\.)(?<!^\d\d\.)"
    + r"\s+"
)
_LEVELS = [
    re.compile(f"({pattern})", re.MULTILINE)
    for pattern in (r"\n\s*\n", _SENTENCE_END, r"\n", r"\s+")
]
_SENTENCE_BOUNDARY = re.compile(_SENTENCE_END, re.MULTILINE)
_WORD_BOUNDARY = re.compile(r"\s+")

def _normalize_separator(raw: str) -> str:
    """Keep the structure of the original whitespace (paragraph break,
    line break or plain space) without its noise."""
    newlines = raw.count("\n")
    if newlines >= 2:
        return "\n\n"
    return "\n" if newlines == 1 else " "

def _pieces(text: str, level: re.Pattern) -> list[tuple[str, str]]:
    """Split text at one level, returning (separator_before, piece)
    pairs so pieces can be glued back with their original separator
    (list items keep their line breaks, paragraphs their blank line)."""
    pieces = []
    raw_separator = ""
    for i, token in enumerate(level.split(text)):
        if i % 2:
            raw_separator += token
            continue
        if token.strip():
            separator = _normalize_separator(raw_separator) if pieces else ""
            pieces.append((separator, token.strip()))
            raw_separator = ""
        else:
            raw_separator += token
    return pieces

def _is_heading(piece: str) -> bool:
    """A short single line with no closing punctuation ("4. Absence pour
    maladie", "## Article 6 : Sanctions") introduces what follows."""
    if piece.startswith("#"):
        return True
    return (len(piece) <= HEADING_MAX_CHARS and "\n" not in piece
            and piece[-1] not in HEADING_END_CHARS)

def _glue_headings(pieces: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Attach each heading to the piece it introduces (across a line
    break), so packing can never separate a title from its text."""
    glued = []
    i = 0
    while i < len(pieces):
        separator, piece = pieces[i]
        last = piece
        while (_is_heading(last) and i + 1 < len(pieces)
               and "\n" in pieces[i + 1][0]):
            next_separator, last = pieces[i + 1]
            piece = f"{piece}{next_separator}{last}"
            i += 1
        glued.append((separator, piece))
        i += 1
    return glued

def _merge(pieces: list[tuple[str, str]], max_chars: int) -> list[str]:
    """Greedily pack consecutive pieces into chunks of at most max_chars."""
    chunks = []
    current = ""
    for separator, piece in pieces:
        candidate = f"{current}{separator}{piece}" if current else piece
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks

def _split(text: str, max_chars: int, level: int = 0) -> list[str]:
    """Recursively split `text` into chunks of at most max_chars, cutting
    at the most meaningful boundary available. A piece is only cut at a
    finer level (e.g. sentences) when it does not fit at the current one
    (e.g. a paragraph longer than a chunk)."""
    if len(text) <= max_chars:
        return [text]
    if level == len(_LEVELS):
        cuts = (text[i:i + max_chars].strip() for i in range(0, len(text), max_chars))
        return [cut for cut in cuts if cut]

    pieces = _glue_headings(_pieces(text, _LEVELS[level]))
    if len(pieces) <= 1:
        return _split(text, max_chars, level + 1)

    chunks = []
    pending = []
    for separator, piece in pieces:
        if len(piece) <= max_chars:
            pending.append((separator, piece))
            continue
        packed = _merge(pending, max_chars)
        pending = []
        carry = packed.pop() if packed and len(packed[-1]) < max_chars // CARRY_DIVISOR else ""
        chunks.extend(packed)
        oversized = f"{carry}{separator}{piece}" if carry else piece
        chunks.extend(_split(oversized, max_chars, level + 1))
    chunks.extend(_merge(pending, max_chars))
    return chunks

def _tail(text: str, max_chars: int) -> str:
    """Last part of `text` (at most max_chars), starting on a sentence
    boundary if possible, otherwise on a word boundary, so the overlap
    never starts in the middle of a word. Returns "" when the whole text
    would fit: repeating an entire chunk adds nothing."""
    if max_chars <= 0 or len(text) <= max_chars:
        return ""
    candidate = text[-max_chars:]
    match = _SENTENCE_BOUNDARY.search(candidate)
    if match:
        return candidate[match.end():]
    if text[-max_chars - 1].isspace():
        return candidate.lstrip()
    match = _WORD_BOUNDARY.search(candidate)
    return candidate[match.end():] if match else ""

def chunk_text(text: str, chunk_tokens: int | None = None,
               overlap_tokens: int | None = None) -> list[str]:
    """Split one text into chunks of at most `chunk_tokens` estimated tokens (same ~4 chars/token rule as the M2 context budget),
    each one starting with the end of the previous chunk (`overlap_tokens`) so a
    fact sitting on a boundary is never lost."""
    chunk_tokens = chunk_tokens if chunk_tokens is not None else DEFAULT_CHUNK_TOKENS
    overlap_tokens = overlap_tokens if overlap_tokens is not None else DEFAULT_OVERLAP_TOKENS
    if chunk_tokens <= 0 or not 0 <= overlap_tokens < chunk_tokens:
        raise ValueError(f"Invalid chunking config: chunk_tokens={chunk_tokens}, overlap_tokens={overlap_tokens} (need 0 <= overlap < chunk size).")

    max_chars = chunk_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN
    text = text.strip()
    if not text:
        return []

    base_chunks = _split(text, max_chars - overlap_chars - len(OVERLAP_SEPARATOR) if overlap_chars else max_chars)
    chunks = [base_chunks[0]]
    for previous, current in zip(base_chunks, base_chunks[1:]):
        tail = _tail(previous, overlap_chars)
        chunks.append(f"{tail}{OVERLAP_SEPARATOR}{current}" if tail else current)
    return chunks

def chunk_pages(pages: list[dict], chunk_tokens: int | None = None,
                overlap_tokens: int | None = None) -> list[dict]:
    """Turn the pages produced by rag.Loader into chunks. Each page is
    chunked on its own so every chunk keeps an exact page number.
    Returns {"source", "page", "chunk_index", "text"} dicts, where
    chunk_index counts chunks within a source document."""
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
