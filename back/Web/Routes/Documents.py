"""The documents of the knowledge base (data/docs) and their index status (rag/Store.py)."""

from fastapi import APIRouter, Depends
from rag.Embeddings import embed_model
from rag.Store import document_statuses
from Web.Sessions import WebSession, current

router = APIRouter()


@router.get("/documents")
def documents(web: WebSession = Depends(current)):
    return {"embed_model": embed_model(), "documents": document_statuses()}
