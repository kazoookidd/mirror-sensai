"""
[R1] Files joined to one conversation.

The same pipeline as the knowledge base (Loader, Chunker, embeddings), but the
chunks are kept apart, tied to the conversation: nobody else sees them, and
they are deleted with it. They belong to the root of the conversation, so its
branches (X2) keep them.

At each question, the chunks of the joined files are ranked by similarity and
added until the room given runs out, without the score threshold of the base:
the user joined these files on purpose. A small file therefore goes in whole
("summarize this file" works), a big one gives its closest passages.
"""

import numpy as np
from Memories.Branches import root_of
from Memories.Compression import estimate_tokens
from Memories.Database import get_connection
from rag.Chunker import chunk_pages
from rag.Embeddings import embed_documents, embed_model, embed_query
from rag.Loader import load_document
from rag.Retriever import cosine_scores, format_chunk
from rag.Store import EMBEDDING_DTYPE

NO_TEXT = "SENSAI could not read any text in this file (a scanned PDF?)."
NO_EMBEDDINGS = "Ollama did not answer: the file could not be read into the chat."
# Share of the free context the joined files may take, so the HR documents still fit.
SHARE_OF_ROOM = 0.6
CONTEXT_HEADER = (
    "--- Fichiers joints par l'utilisateur à cette discussion ---\n"
    "Leur texte est déjà ci-dessous : n'utilise aucun outil pour les lire ou les chercher. "
    "Quand la question les concerne, réponds directement à partir de ce texte et cite leur "
    "source entre crochets. Ils ne remplacent pas une action demandée (une demande de congé...)."
)

_CREATE_ATTACHMENTS = """
    CREATE TABLE IF NOT EXISTS attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER NOT NULL,
        source TEXT NOT NULL,
        size INTEGER NOT NULL,
        embed_model TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
    )
"""
_CREATE_CHUNKS = """
    CREATE TABLE IF NOT EXISTS attachment_chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        attachment_id INTEGER NOT NULL,
        page INTEGER,
        chunk_index INTEGER NOT NULL,
        text TEXT NOT NULL,
        embedding BLOB NOT NULL,
        FOREIGN KEY (attachment_id) REFERENCES attachments(id) ON DELETE CASCADE
    )
"""
_LIST = """
    SELECT a.id, a.source, a.size, a.created_at, COUNT(c.id) AS chunks
    FROM attachments a LEFT JOIN attachment_chunks c ON c.attachment_id = a.id
    WHERE a.conversation_id = ? GROUP BY a.id ORDER BY a.id
"""
_LIST_FOR_USER = """
    SELECT a.id, a.source, a.size, a.created_at, c.id AS conversation_id, c.title AS conversation_title
    FROM attachments a JOIN conversations c ON c.id = a.conversation_id
    WHERE c.user_id = ? ORDER BY a.id DESC
"""
_CHUNKS = """
    SELECT a.source, c.page, c.chunk_index, c.text, c.embedding
    FROM attachment_chunks c JOIN attachments a ON a.id = c.attachment_id
    WHERE a.conversation_id = ? AND a.embed_model = ?
    ORDER BY a.id, c.chunk_index
"""


def _connect():
    conn = get_connection()
    conn.execute(_CREATE_ATTACHMENTS)
    conn.execute(_CREATE_CHUNKS)
    return conn


def attach(conversation_id: int, path, source: str) -> dict:
    """Read, chunk and embed a file for the conversation; a file of the same name is replaced.
    ValueError if it has no readable text, ConnectionError if Ollama does not answer."""
    pages = load_document(path, source=source)
    if not pages:
        raise ValueError(NO_TEXT)
    chunks = chunk_pages(pages)
    vectors = embed_documents([chunk["text"] for chunk in chunks])
    if vectors is None:
        raise ConnectionError(NO_EMBEDDINGS)
    root = root_of(conversation_id)
    conn = _connect()
    try:
        with conn:
            conn.execute("DELETE FROM attachments WHERE conversation_id = ? AND source = ?", (root, source))
            attachment = conn.execute(
                "INSERT INTO attachments (conversation_id, source, size, embed_model) VALUES (?, ?, ?, ?)",
                (root, source, path.stat().st_size, embed_model())
            ).lastrowid
            conn.executemany(
                "INSERT INTO attachment_chunks (attachment_id, page, chunk_index, text, embedding) VALUES (?, ?, ?, ?, ?)",
                [(attachment, chunk["page"], chunk["chunk_index"], chunk["text"],
                  np.asarray(vector, dtype=EMBEDDING_DTYPE).tobytes()) for chunk, vector in zip(chunks, vectors)]
            )
    finally:
        conn.close()
    return next(item for item in list_attachments(conversation_id) if item["id"] == attachment)


def list_attachments(conversation_id: int) -> list[dict]:
    """The files joined to the conversation (or to the root of its branch), oldest first."""
    conn = _connect()
    try:
        return [dict(row) for row in conn.execute(_LIST, (root_of(conversation_id),))]
    finally:
        conn.close()


def list_user_attachments(user_id: str) -> list[dict]:
    """Every file the user joined to one of their conversations, newest first, with that conversation."""
    conn = _connect()
    try:
        return [dict(row) for row in conn.execute(_LIST_FOR_USER, (user_id,))]
    finally:
        conn.close()


def detach(user_id: str, attachment_id: int) -> bool:
    """Delete a file joined to one of the user's conversations, with its chunks; False if it is not theirs."""
    conn = _connect()
    try:
        with conn:
            deleted = conn.execute(
                "DELETE FROM attachments WHERE id = ? AND conversation_id IN (SELECT id FROM conversations WHERE user_id = ?)",
                (attachment_id, user_id)
            ).rowcount
        return deleted > 0
    finally:
        conn.close()


def has_attachments(conversation_id: int | None) -> bool:
    return conversation_id is not None and bool(list_attachments(conversation_id))


def _reembed(conn, root: int, model: str) -> None:
    """Embed again, from their stored text, the files joined under another embedding model:
    the original file is not kept, and they would otherwise drop out of the chat."""
    stale = conn.execute("SELECT id FROM attachments WHERE conversation_id = ? AND embed_model != ?", (root, model)).fetchall()
    for attachment in stale:
        rows = conn.execute("SELECT id, text FROM attachment_chunks WHERE attachment_id = ?", (attachment["id"],)).fetchall()
        vectors = embed_documents([row["text"] for row in rows])
        if vectors is None:
            return
        with conn:
            conn.executemany("UPDATE attachment_chunks SET embedding = ? WHERE id = ?",
                             [(np.asarray(vector, dtype=EMBEDDING_DTYPE).tobytes(), row["id"]) for row, vector in zip(rows, vectors)])
            conn.execute("UPDATE attachments SET embed_model = ? WHERE id = ?", (model, attachment["id"]))


def _load_chunks(conversation_id: int) -> tuple[list[dict], np.ndarray]:
    root, model = root_of(conversation_id), embed_model()
    conn = _connect()
    try:
        _reembed(conn, root, model)
        rows = conn.execute(_CHUNKS, (root, model)).fetchall()
    finally:
        conn.close()
    chunks = [{field: row[field] for field in ("source", "page", "chunk_index", "text")} for row in rows]
    vectors = [np.frombuffer(row["embedding"], dtype=EMBEDDING_DTYPE) for row in rows]
    return chunks, np.vstack(vectors) if vectors else np.empty((0, 0), dtype=EMBEDDING_DTYPE)


def attachments_message(conversation_id: int | None, question: str, max_tokens: int,
                        ollama_url: str | None = None) -> dict | None:
    """System message with the joined files, closest passages first chosen, given in file order; None if none."""
    if conversation_id is None:
        return None
    chunks, matrix = _load_chunks(conversation_id)
    if not chunks:
        return None
    vector = embed_query(question, ollama_url)
    # Without a vector (Ollama busy), the start of the files is the best guess.
    order = range(len(chunks)) if vector is None or len(vector) != matrix.shape[1] else np.argsort(-cosine_scores(matrix, vector))
    used = estimate_tokens(CONTEXT_HEADER)
    chosen = []
    for index in order:
        cost = estimate_tokens(f"\n\n{format_chunk(chunks[index])}")
        if used + cost <= max_tokens:
            chosen.append(index)
            used += cost
    if not chosen:
        return None
    passages = "\n\n".join(format_chunk(chunks[index]) for index in sorted(chosen))
    return {"role": "system", "content": f"{CONTEXT_HEADER}\n\n{passages}"}
