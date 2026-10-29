import logging
import os
import requests

DEFAULT_EMBED_MODEL = "bge-m3"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
# Written for nomic-embed-text, kept for bge-m3: they widen its gap between the right passage
# and an off-topic question (docs/benchmarks/embedding_models.md).
DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "
BATCH_SIZE = 32
TIMEOUT_SECONDS = 120
logger = logging.getLogger(__name__)


def embed_model() -> str:
    """Embedding model set in .env (RAG_EMBED_MODEL)."""
    model = os.getenv("RAG_EMBED_MODEL", "").strip()
    if not model:
        return DEFAULT_EMBED_MODEL
    return model


def _ollama_url() -> str:
    """Ollama URL set in .env (OLLAMA_BASE_URL)."""
    url = os.getenv("OLLAMA_BASE_URL", "").strip()
    if not url:
        return DEFAULT_OLLAMA_URL
    return url


def _post_embed(base_url: str, model: str, batch: list[str]):
    """Send one /api/embed request, None if it fails."""
    try:
        body = {"model": model, "input": batch}
        response = requests.post(f"{base_url}/api/embed", json=body, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
    except requests.exceptions.ConnectionError:
        logger.warning(f"cannot connect to Ollama at {base_url}, is it running? (ollama serve)")
        return None
    except requests.exceptions.HTTPError as e:
        logger.warning(f"embedding model {model!r} unavailable (ollama pull {model}?) ({e})")
        return None
    except (requests.exceptions.RequestException, ValueError) as e:
        logger.warning(f"embedding request failed ({e})")
        return None
    return payload


def _embed_batch(base_url: str, model: str, batch: list[str]) -> list[list[float]] | None:
    """One vector per text of `batch`, None if Ollama fails."""
    payload = _post_embed(base_url, model, batch)
    if not isinstance(payload, dict):
        return None
    embeddings = payload.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != len(batch):
        logger.warning(f"unexpected answer from Ollama for {model!r}")
        return None
    return embeddings


def _embed(texts: list[str], prefix: str, base_url: str | None = None) -> list[list[float]] | None:
    """Embed `texts` by batches, None if a batch fails."""
    if not base_url:
        base_url = _ollama_url()
    model = embed_model()
    vectors = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = [prefix + text for text in texts[start:start + BATCH_SIZE]]
        embeddings = _embed_batch(base_url, model, batch)
        if embeddings is None:
            return None
        vectors.extend(embeddings)
    return vectors


def embed_documents(texts: list[str]) -> list[list[float]] | None:
    """Vectors of document chunks."""
    return _embed(texts, DOCUMENT_PREFIX)


def embed_query(text: str, base_url: str | None = None) -> list[float] | None:
    """Vector of a user question."""
    vectors = _embed([text], QUERY_PREFIX, base_url)
    if not vectors:
        return None
    return vectors[0]
