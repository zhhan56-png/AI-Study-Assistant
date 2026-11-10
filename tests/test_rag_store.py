"""Tests for the persistent ChromaDB storage layer (BUG-02 fix)."""

import os

# chromadb 默认会发匿名遥测；离线环境先关掉，避免告警/超时。
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import re

import pytest

from rag_store import (
    chunk_id,
    clear_collection,
    collection_name_for,
    delete_file_chunks,
    get_chroma_client,
    get_or_create_collection,
    load_documents,
    sanitize_collection_name,
    upsert_documents,
)


def _make_doc(cid: str, source: str, chunk: int, file_hash: str, summary: str = "summary") -> dict:
    return {
        "id": cid,
        "content": f"chunk {chunk} of {source}",
        "metadata": {
            "source": source,
            "chunk": chunk,
            "summary": summary,
            "preview": "preview",
            "file_hash": file_hash,
        },
    }


def _embeddings(count: int) -> list:
    return [[float(i), 1.0, 0.0, 0.0] for i in range(count)]


@pytest.fixture()
def collection(tmp_path):
    client = get_chroma_client(str(tmp_path / "chroma"))
    return get_or_create_collection(client, "test-embed:latest")


def test_sanitize_collection_name():
    name = sanitize_collection_name("document_collection_llama3.1:latest")
    assert name == "document_collection_llama3.1_latest"
    assert len(sanitize_collection_name("a" * 100)) == 63
    assert len(sanitize_collection_name("")) >= 3
    assert sanitize_collection_name("--模型--") == "collection"
    assert re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]", sanitize_collection_name("--模型--"))


def test_chunk_id_is_stable_and_sortable():
    assert chunk_id("abc123", 0) == "abc123-0000"
    assert chunk_id("abc123", 12) == "abc123-0012"
    assert chunk_id("abc123", 0) < chunk_id("abc123", 12)


def test_collection_name_for_includes_model():
    assert "llama3.1" in collection_name_for("llama3.1:latest")


def test_survives_client_reopen(tmp_path):
    path = str(tmp_path / "chroma")
    client = get_chroma_client(path)
    col = get_or_create_collection(client, "m1")
    docs = [_make_doc(chunk_id("hashA", 0), "a.txt", 0, "hashA")]
    upsert_documents(col, docs, _embeddings(1))

    # 模拟重启：完全新建一个 client（不共享内存对象）
    client2 = get_chroma_client(path)
    col2 = get_or_create_collection(client2, "m1")
    loaded = load_documents(col2)
    assert len(loaded) == 1
    assert loaded[0]["content"] == docs[0]["content"]
    assert loaded[0]["id"] == "hashA-0000"


def test_batches_accumulate(collection):
    batch1 = [_make_doc(chunk_id("hashA", i), "a.txt", i, "hashA") for i in range(2)]
    batch2 = [_make_doc(chunk_id("hashB", i), "b.txt", i, "hashB") for i in range(3)]
    upsert_documents(collection, batch1, _embeddings(len(batch1)))
    upsert_documents(collection, batch2, _embeddings(len(batch2)))
    assert len(load_documents(collection)) == 5


def test_load_documents_sorted_by_source_then_chunk(collection):
    docs = [
        _make_doc(chunk_id("hB", 1), "b.txt", 1, "hB"),
        _make_doc(chunk_id("hA", 1), "a.txt", 1, "hA"),
        _make_doc(chunk_id("hA", 0), "a.txt", 0, "hA"),
    ]
    upsert_documents(collection, docs, _embeddings(len(docs)))
    loaded = load_documents(collection)
    assert [(d["metadata"]["source"], d["metadata"]["chunk"]) for d in loaded] == [
        ("a.txt", 0),
        ("a.txt", 1),
        ("b.txt", 1),
    ]


def test_upsert_same_id_updates_instead_of_duplicating(collection):
    doc = _make_doc(chunk_id("hA", 0), "a.txt", 0, "hA")
    upsert_documents(collection, [doc], _embeddings(1))
    doc2 = dict(doc)
    doc2["content"] = "updated content"
    upsert_documents(collection, [doc2], _embeddings(1))

    loaded = load_documents(collection)
    assert len(loaded) == 1
    assert loaded[0]["content"] == "updated content"


def test_delete_file_chunks_removes_only_that_file(collection):
    docs = [
        _make_doc(chunk_id("hA", 0), "a.txt", 0, "hA"),
        _make_doc(chunk_id("hA", 1), "a.txt", 1, "hA"),
        _make_doc(chunk_id("hB", 0), "b.txt", 0, "hB"),
    ]
    upsert_documents(collection, docs, _embeddings(len(docs)))

    delete_file_chunks(collection, "hA")
    loaded = load_documents(collection)
    assert [d["metadata"]["file_hash"] for d in loaded] == ["hB"]


def test_clear_collection_removes_everything(tmp_path):
    path = str(tmp_path / "chroma")
    client = get_chroma_client(path)
    col = get_or_create_collection(client, "test-embed:latest")
    upsert_documents(col, [_make_doc(chunk_id("hA", 0), "a.txt", 0, "hA")], _embeddings(1))
    assert len(load_documents(col)) == 1

    clear_collection(client, "test-embed:latest")
    reopened = get_or_create_collection(client, "test-embed:latest")
    assert load_documents(reopened) == []
