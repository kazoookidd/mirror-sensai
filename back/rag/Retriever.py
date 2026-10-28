import logging
import os
import numpy as np
from Memories.Compression import estimate_tokens
from rag.Embeddings import embed_query
from rag.Store import EMBEDDING_DTYPE, load_chunks

DEFAULT_MIN_SCORE = 0.70
DEFAULT_TOP_K = 3
CONTEXT_HEADER = (
    "Extraits des documents RH de l'entreprise. Appuie ta réponse sur ces extraits "
    "et cite leur source entre crochets. S'ils ne répondent pas à la question, "
    "dis-le au lieu d'inventer."
)
logger = logging.getLogger(__name__)


def _read_setting(name: str, default, cast):
    """Setting from .env, or `default` if it is missing or invalid."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return cast(raw)
    except ValueError:
        logger.warning(f"invalid {name}={raw!r}, using {default}")
        return default


def cosine_scores(matrix: np.ndarray, vector: list[float]) -> np.ndarray:
    """Cosine similarity between `vector` and each row of `matrix`."""
    query = np.asarray(vector, dtype=EMBEDDING_DTYPE)
    with np.errstate(divide="ignore", invalid="ignore"):
        return (matrix @ query) / (np.linalg.norm(matrix, axis=1) * np.linalg.norm(query))


def _best_chunks(chunks: list[dict], scores: np.ndarray, top_k: int,
                 min_score: float) -> list[dict]:
    """The `top_k` best chunks scoring at least `min_score`."""
    best = []
    for i in np.argsort(-scores)[:top_k]:
        if scores[i] >= min_score:
            best.append({**chunks[i], "score": float(scores[i])})
    return best


def retrieve(question: str, db_path: str | None = None,
             ollama_url: str | None = None) -> list[dict]:
    """Indexed chunks closest to `question`, best first."""
    min_score = _read_setting("RAG_MIN_SCORE", DEFAULT_MIN_SCORE, float)
    top_k = _read_setting("RAG_TOP_K", DEFAULT_TOP_K, int)
    chunks, matrix = load_chunks(db_path)
    if not chunks or top_k <= 0:
        return []
    vector = embed_query(question, ollama_url)
    if vector is None:
        return []
    if len(vector) != matrix.shape[1]:
        logger.warning("the index was built with another embedding model, run /ingest again")
        return []
    return _best_chunks(chunks, cosine_scores(matrix, vector), top_k, min_score)


def format_chunk(chunk: dict) -> str:
    """Chunk text preceded by its source, like [accord.pdf, p. 4]."""
    source = chunk["source"]
    if chunk["page"] is not None:
        source = f"{source}, p. {chunk['page']}"
    return f"[{source}]\n{chunk['text']}"


def documents_message(chunks: list[dict], max_tokens: int) -> dict | None:
    """System message with the chunks that fit in `max_tokens`, or None."""
    content = CONTEXT_HEADER
    added = 0
    for chunk in chunks:
        candidate = f"{content}\n\n{format_chunk(chunk)}"
        if estimate_tokens(candidate) > max_tokens:
            break
        content = candidate
        added += 1
    if not added:
        return None
    return {"role": "system", "content": content}


def rag_message(question: str, max_tokens: int, db_path: str | None = None, ollama_url: str | None = None) -> dict | None:
    """System message with the documents relevant to `question`, or None."""
    if max_tokens <= estimate_tokens(CONTEXT_HEADER):
        return None
    return documents_message(retrieve(question, db_path, ollama_url), max_tokens)
