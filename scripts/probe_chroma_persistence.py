"""BUG-02 探针：验证向量库是否真正持久化。

输出三组证据：
1. 旧的 ``chromadb.Client()``：``is_persistent=False``、没有 ``persist_directory``；
2. 新的 ``rag_store.get_chroma_client()``：``is_persistent=True``，且磁盘上有 ``chroma.sqlite3``；
3. 写入后重新打开（模拟进程重启），数据仍在。

用法：
    python scripts/probe_chroma_persistence.py
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

# 允许从仓库根目录直接运行本脚本
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chromadb  # noqa: E402
from chromadb.config import Settings  # noqa: E402

from rag_store import (  # noqa: E402
    chunk_id,
    get_chroma_client,
    get_or_create_collection,
    load_documents,
    upsert_documents,
)


def _settings() -> Settings:
    return Settings(anonymized_telemetry=False)


def probe_in_memory_client() -> bool:
    """旧实现：内存 client，settings.is_persistent 为 False。"""
    client = chromadb.Client(_settings())
    settings = client.get_settings()
    is_persistent = getattr(settings, "is_persistent", None)
    persist_directory = getattr(settings, "persist_directory", None)
    print(
        f"[old] chromadb.Client(): type={type(client).__name__} "
        f"is_persistent={is_persistent} persist_directory={persist_directory}"
    )
    return is_persistent is False


def probe_persistent_client(work_dir: str) -> bool:
    """新实现：PersistentClient，写入磁盘并可跨进程重新打开。"""
    path = os.path.join(work_dir, "chroma")
    client = get_chroma_client(path)
    settings = client.get_settings()
    print(
        f"[new] PersistentClient: is_persistent={settings.is_persistent} "
        f"persist_directory={settings.persist_directory}"
    )

    collection = get_or_create_collection(client, "probe-model:latest")
    documents = [
        {
            "id": chunk_id("hashA", 0),
            "content": "chunk 0: BM25",
            "metadata": {"source": "a.txt", "chunk": 0, "file_hash": "hashA"},
        },
        {
            "id": chunk_id("hashA", 1),
            "content": "chunk 1: RRF",
            "metadata": {"source": "a.txt", "chunk": 1, "file_hash": "hashA"},
        },
    ]
    upsert_documents(collection, documents, [[1.0, 0.0], [0.0, 1.0]])
    print(f"[new] first run: count={collection.count()}")

    sqlite_path = os.path.join(path, "chroma.sqlite3")
    has_sqlite = os.path.exists(sqlite_path)
    print(f"[new] on-disk chroma.sqlite3 exists: {has_sqlite}")

    # 释放对象，模拟进程退出后重新打开
    del collection, client

    reopened_client = get_chroma_client(path)
    reopened = get_or_create_collection(reopened_client, "probe-model:latest")
    loaded = load_documents(reopened)
    print(f"[new] after reopen (simulated restart): count={reopened.count()} docs={[d['content'] for d in loaded]}")
    return has_sqlite and reopened.count() == 2


def main() -> int:
    work_dir = tempfile.mkdtemp(prefix="chroma-probe-")
    try:
        old_ok = probe_in_memory_client()
        new_ok = probe_persistent_client(work_dir)
        ok = old_ok and new_ok
        print(f"RESULT: {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
