"""The documents of the knowledge base (data/docs) and their index status (rag/Store.py).
[R1] Importing a file saves it in data/docs and runs the same indexing as /ingest:
nothing leaves the machine, chunks and embeddings are made locally."""

import threading
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from Cache.Chat import invalidate as invalidate_cache
from rag import Store
from rag.Embeddings import embed_model
from rag.Loader import SUPPORTED_EXTENSIONS, load_document
from Web.Sessions import WebSession, current

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
FORMATS = ", ".join(sorted(SUPPORTED_EXTENSIONS))

router = APIRouter()
# Two imports at once would index the same folder twice in parallel.
_indexing = threading.Lock()


def upload_name(name: str) -> str:
    """The name the file is saved under, 422 if it could reach outside data/docs or is not a document."""
    clean = Path(name).name
    if not clean or clean != name or clean.startswith("."):
        raise HTTPException(status_code=422, detail="Invalid file name.")
    if Path(clean).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=422, detail=f"Unsupported file type: use {FORMATS}.")
    return clean


async def read_upload(request: Request) -> bytes:
    content = bytearray()
    async for part in request.stream():
        content += part
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"The file is over {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    if not content:
        raise HTTPException(status_code=422, detail="The file is empty.")
    return bytes(content)


def _save_and_index(folder: Path, name: str, content: bytes) -> dict:
    with _indexing:
        folder.mkdir(parents=True, exist_ok=True)
        # Hidden while it is checked, so an indexing run never sees half a file.
        partial = folder / f".upload-{name}"
        partial.write_bytes(content)
        if not load_document(partial, source=name):
            partial.unlink()
            raise HTTPException(status_code=422, detail="SENSAI could not read any text in this file (a scanned PDF?).")
        partial.replace(folder / name)
        stats = Store.index_directory(folder)
        if not stats["failed"]:
            # The cached answers were written from the old documents.
            invalidate_cache()
    return stats


@router.get("/documents")
def documents(web: WebSession = Depends(current)):
    return {"embed_model": embed_model(), "documents": Store.document_statuses(Store.DEFAULT_DOCS_DIR)}


@router.post("/documents")
async def import_document(request: Request, name: str, web: WebSession = Depends(current)):
    file_name = upload_name(name)
    content = await read_upload(request)
    folder = Store.DEFAULT_DOCS_DIR
    stats = await run_in_threadpool(_save_and_index, folder, file_name, content)
    if stats["failed"]:
        raise HTTPException(status_code=503, detail="The file was saved, but Ollama did not answer: it is not indexed yet.")
    document = next(item for item in Store.document_statuses(folder) if item["source"] == file_name)
    return {"document": document}
