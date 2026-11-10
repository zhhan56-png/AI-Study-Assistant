"""Persistent vector storage helpers (BUG-02 fix).

The original app used ``chromadb.Client()`` — an in-memory client — so the
whole knowledge base disappeared whenever Streamlit was refreshed or
restarted.  This module keeps a single ``chromadb.PersistentClient`` on disk
(``data/chroma`` by default; override with the ``RAG_CHROMA_DIR`` environment
variable) and provides small helpers for loading, upserting and clearing
document chunks.

Chunk IDs are stable strings derived from the file hash and the chunk index
(``<file_hash>-0000``).  Re-uploading the same file therefore *updates* its
chunks instead of duplicating them, and the vector store stays consistent
with the session document list.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import chromadb
from chromadb.config import Settings

#: Location of the persistent ChromaDB store (``data/`` is git-ignored).
DEFAULT_CHROMA_DIR = Path(
    os.environ.get("RAG_CHROMA_DIR", str(Path(__file__).resolve().parent / "data" / "chroma"))
)


def _client_settings() -> Settings:
    """ChromaDB settings: local-only, no anonymous telemetry network calls."""
    return Settings(anonymized_telemetry=False)


def get_chroma_client(path: Optional[str] = None) -> "chromadb.api.ClientAPI":
    """Return a *persistent* ChromaDB client rooted at ``path``.

    Args:
        path: Directory where ChromaDB stores its SQLite database and HNSW
            index.  Defaults to :data:`DEFAULT_CHROMA_DIR`.

    Returns:
        A ``chromadb.PersistentClient`` (data survives process restarts).
    """
    return chromadb.PersistentClient(path=str(path or DEFAULT_CHROMA_DIR), settings=_client_settings())


def sanitize_collection_name(name: str) -> str:
    """Sanitize a collection name to meet ChromaDB's naming rules.

    ChromaDB requires 3-63 characters from ``[a-zA-Z0-9._-]``, starting and
    ending with an alphanumeric character.
    """
    sanitized = re.sub(r'[^a-zA-Z0-9._-]', '_', name)
    sanitized = re.sub(r'^[^a-zA-Z0-9]+', '', sanitized)
    sanitized = re.sub(r'[^a-zA-Z0-9]+$', '', sanitized)
    if not sanitized:
        sanitized = 'collection'
    sanitized = sanitized[:63]
    while len(sanitized) < 3:
        sanitized += 'a'
    return sanitized


def collection_name_for(embedding_model: str) -> str:
    """Collection name used for a given embedding model.

    Embeddings from different models are not comparable (and may have
    different dimensions), so each model gets its own persistent collection.
    """
    return sanitize_collection_name(f"document_collection_{embedding_model}")


def get_or_create_collection(client, embedding_model: str):
    """Open the persistent collection for ``embedding_model``, creating it if needed."""
    return client.get_or_create_collection(name=collection_name_for(embedding_model))


def chunk_id(file_hash: str, index: int) -> str:
    """Stable ID for a chunk: ``<md5-of-file>-<four-digit chunk index>``."""
    return f"{file_hash}-{index:04d}"


def load_documents(collection) -> List[Dict]:
    """Read every chunk back out of the collection.

    Returns:
        A list of ``{"id", "content", "metadata"}`` dicts sorted by
        ``(source, chunk)`` so that the order is deterministic across
        restarts (the BM25 index and the UI both rely on a stable order).
    """
    data = collection.get(include=["documents", "metadatas"])
    documents: List[Dict] = []
    for cid, content, metadata in zip(
        data.get("ids") or [], data.get("documents") or [], data.get("metadatas") or []
    ):
        documents.append(
            {
                "id": cid,
                "content": content,
                "metadata": dict(metadata or {}),
            }
        )
    documents.sort(
        key=lambda doc: (
            str(doc["metadata"].get("source", "")),
            int(doc["metadata"].get("chunk", 0)),
        )
    )
    return documents


def upsert_documents(collection, documents: List[Dict], embeddings: List[List[float]]) -> None:
    """Insert or update chunks (ids must be present in each document dict)."""
    collection.upsert(
        ids=[doc["id"] for doc in documents],
        embeddings=embeddings,
        documents=[doc["content"] for doc in documents],
        metadatas=[doc["metadata"] for doc in documents],
    )


def delete_file_chunks(collection, file_hash: str) -> None:
    """Remove all chunks that came from the file with ``file_hash``.

    Called before re-indexing a file so that re-processing replaces its old
    chunks instead of duplicating them.
    """
    try:
        collection.delete(where={"file_hash": file_hash})
    except Exception:
        # Deleting from an empty collection / a filter with no matches is
        # harmless; keep the pipeline going.
        pass


def clear_collection(client, embedding_model: str):
    """Delete and immediately recreate the collection for ``embedding_model``."""
    name = collection_name_for(embedding_model)
    try:
        client.delete_collection(name=name)
    except Exception:
        pass
    return client.get_or_create_collection(name=name)
