import hashlib
import logging
from pathlib import Path
import numpy as np
from Memories.Database import get_connection
from rag.Chunker import chunk_pages
from rag.Embeddings import embed_documents, embed_model
from rag.Loader import list_documents, load_document

EMBEDDING_DTYPE = np.float32
DEFAULT_DOCS_DIR = Path(__file__).resolve().parents[2] / "data" / "docs"
logger = logging.getLogger(__name__)

_CREATE_DOCUMENTS = """
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        folder TEXT NOT NULL,
        source TEXT NOT NULL,
        file_hash TEXT NOT NULL,
        embed_model TEXT NOT NULL,
        indexed_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (folder, source)
    )
"""
_CREATE_CHUNKS = """
    CREATE TABLE IF NOT EXISTS chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER NOT NULL,
        page INTEGER,
        chunk_index INTEGER NOT NULL,
        text TEXT NOT NULL,
        embedding BLOB NOT NULL,
        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
    )
"""
_SELECT_KNOWN = "SELECT id, source, file_hash, embed_model FROM documents WHERE folder = ?"
_INSERT_DOCUMENT = (
    "INSERT INTO documents (folder, source, file_hash, embed_model) VALUES (?, ?, ?, ?)"
)
_INSERT_CHUNK = (
    "INSERT INTO chunks (document_id, page, chunk_index, text, embedding) VALUES (?, ?, ?, ?, ?)"
)
_DELETE_DOCUMENT = "DELETE FROM documents WHERE id = ?"
_SELECT_INDEXED = """
    SELECT d.source, d.file_hash, d.embed_model, d.indexed_at, COUNT(c.id) AS chunks
    FROM documents d LEFT JOIN chunks c ON c.document_id = d.id
    WHERE d.folder = ?
    GROUP BY d.id
"""
_SELECT_CHUNKS = """
    SELECT d.source, c.page, c.chunk_index, c.text, c.embedding
    FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE d.embed_model = ?
    ORDER BY d.folder, d.source, c.chunk_index
"""


def init_rag_db(db_path: str | None = None) -> None:
    """Create the RAG tables if they don't exist."""
    conn = get_connection(db_path)
    try:
        conn.execute(_CREATE_DOCUMENTS)
        conn.execute(_CREATE_CHUNKS)
        conn.commit()
    finally:
        conn.close()


def _file_hash(path: Path, source: str) -> str | None:
    """SHA-256 of the file, None if it cannot be read."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as e:
        logger.warning(f"cannot read {source}, skipped ({e})")
        return None


def _is_unchanged(row, file_hash: str, model: str) -> bool:
    """True if the stored version has the same hash and model."""
    if row is None:
        return False
    return row["file_hash"] == file_hash and row["embed_model"] == model


def _read_chunks(path: Path, source: str, row) -> list[dict] | None:
    """Chunks of the file, None if it has no readable text."""
    pages = load_document(path, source=source)
    if not pages:
        if row is not None:
            logger.warning(f"{source} could not be read, keeping its previous chunks")
        return None
    return chunk_pages(pages)


def _chunk_rows(document_id: int, chunks: list[dict], vectors: list[list[float]]) -> list[tuple]:
    """Rows to insert in the chunks table."""
    rows = []
    for chunk, vector in zip(chunks, vectors):
        embedding = np.asarray(vector, dtype=EMBEDDING_DTYPE).tobytes()
        rows.append((document_id, chunk["page"], chunk["chunk_index"], chunk["text"], embedding))
    return rows


def _save_document(conn, folder: Path, source: str, file_hash: str, model: str, chunks: list[dict], vectors: list[list[float]], row) -> None:
    """Replace a document and its chunks in a single transaction."""
    with conn:
        if row is not None:
            conn.execute(_DELETE_DOCUMENT, (row["id"],))
        document = (str(folder), source, file_hash, model)
        document_id = conn.execute(_INSERT_DOCUMENT, document).lastrowid
        conn.executemany(_INSERT_CHUNK, _chunk_rows(document_id, chunks, vectors))


def _index_file(conn, folder: Path, path: Path, source: str, row, model: str) -> tuple[str, int]:
    """Index one file if needed. Status: indexed, unchanged, skipped or failed."""
    file_hash = _file_hash(path, source)
    if file_hash is None:
        return "skipped", 0
    if _is_unchanged(row, file_hash, model):
        return "unchanged", 0
    chunks = _read_chunks(path, source, row)
    if chunks is None:
        return "skipped", 0
    vectors = embed_documents([chunk["text"] for chunk in chunks])
    if vectors is None:
        logger.warning(f"embedding failed on {source}, indexing stopped")
        return "failed", 0
    _save_document(conn, folder, source, file_hash, model, chunks, vectors, row)
    return "indexed", len(chunks)


def _remove_deleted(conn, known: dict, documents: list[tuple[Path, str]]) -> int:
    """Remove the documents whose file was deleted, return how many."""
    present = {source for _, source in documents}
    stale = [(row["id"],) for source, row in known.items() if source not in present]
    with conn:
        conn.executemany(_DELETE_DOCUMENT, stale)
    return len(stale)


def _index_folder(conn, folder: Path, stats: dict) -> None:
    """Index every file of `folder`, stop at the first Ollama error."""
    model = embed_model()
    documents = list_documents(folder)
    known = {row["source"]: row for row in conn.execute(_SELECT_KNOWN, (str(folder),))}
    for path, source in documents:
        status, n_chunks = _index_file(conn, folder, path, source, known.get(source), model)
        if status == "failed":
            stats["failed"] = True
            return
        if status in ("indexed", "unchanged"):
            stats[status] += 1
        stats["chunks"] += n_chunks
    stats["removed"] = _remove_deleted(conn, known, documents)


def index_directory(folder: str | Path, db_path: str | None = None) -> dict:
    """Index every document of `folder` and return the counts."""
    stats = {"indexed": 0, "unchanged": 0, "removed": 0, "chunks": 0, "failed": False}
    folder = Path(folder).resolve()
    if not folder.is_dir():
        logger.warning(f"{folder} is not a directory, nothing indexed")
        return stats
    init_rag_db(db_path)
    conn = get_connection(db_path)
    try:
        _index_folder(conn, folder, stats)
    finally:
        conn.close()
    return stats


def forget_document(folder: str | Path, source: str, db_path: str | None = None) -> None:
    """Remove a document and its chunks from the index, without waiting for a full indexing run."""
    init_rag_db(db_path)
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM documents WHERE folder = ? AND source = ?", (str(Path(folder).resolve()), source))
    finally:
        conn.close()


def rename_document(folder: str | Path, source: str, new_source: str, db_path: str | None = None) -> None:
    """Give an indexed document its new file name: same text, so its vectors are kept."""
    init_rag_db(db_path)
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("UPDATE documents SET source = ? WHERE folder = ? AND source = ?",
                         (new_source, str(Path(folder).resolve()), source))
    finally:
        conn.close()


def _document_status(path: Path, source: str, row, model: str) -> dict:
    """What the interface shows for one file: size, dates and index status."""
    if row is None:
        status = "not_indexed"
    elif _is_unchanged(row, _file_hash(path, source), model):
        status = "indexed"
    else:
        status = "outdated"
    stat = path.stat()
    return {
        "source": source,
        "size": stat.st_size,
        "modified": stat.st_mtime,
        "indexed_at": row["indexed_at"] if row else None,
        "chunks": row["chunks"] if row else 0,
        "status": status,
    }


def document_statuses(folder: str | Path = DEFAULT_DOCS_DIR, db_path: str | None = None) -> list[dict]:
    """Every file of `folder` with its status: indexed, outdated or not_indexed."""
    folder = Path(folder).resolve()
    if not folder.is_dir():
        return []
    init_rag_db(db_path)
    conn = get_connection(db_path)
    try:
        known = {row["source"]: row for row in conn.execute(_SELECT_INDEXED, (str(folder),))}
    finally:
        conn.close()
    model = embed_model()
    return [_document_status(path, source, known.get(source), model)
            for path, source in list_documents(folder)]


def _to_matrix(rows: list) -> np.ndarray:
    """Stored vectors as a float32 matrix, one row per chunk."""
    if not rows:
        return np.empty((0, 0), dtype=EMBEDDING_DTYPE)
    vectors = [np.frombuffer(row["embedding"], dtype=EMBEDDING_DTYPE) for row in rows]
    return np.vstack(vectors)


def load_chunks(db_path: str | None = None) -> tuple[list[dict], np.ndarray]:
    """Chunks embedded with the current model, and their vectors as a matrix."""
    init_rag_db(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(_SELECT_CHUNKS, (embed_model(),)).fetchall()
    finally:
        conn.close()
    fields = ("source", "page", "chunk_index", "text")
    chunks = [{field: row[field] for field in fields} for row in rows]
    return chunks, _to_matrix(rows)
