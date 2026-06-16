"""SQLite-backed embedding cache.

Stores: chunk_hash -> (embedding_bytes, token_count, model).
A document-level table also remembers the last full-document hash so we can
short-circuit unchanged documents before chunking them.

In production this would be Redis, Cosmos DB, or an Azure Table — the
interface is identical.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import numpy as np

from .config import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunk_cache (
    hash       TEXT PRIMARY KEY,
    model      TEXT NOT NULL,
    tokens     INTEGER NOT NULL,
    embedding  BLOB NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS doc_state (
    doc_id     TEXT PRIMARY KEY,
    hash       TEXT NOT NULL,
    chunk_ids  TEXT NOT NULL,  -- JSON list of chunk ids currently indexed
    updated_at REAL NOT NULL
);
"""


class EmbeddingCache:
    def __init__(self, path: Path | None = None) -> None:
        settings = get_settings()
        self.path = path or (settings.data_dir / "cache.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ---- chunk-level cache ---------------------------------------------------

    def get(self, hash_: str, model: str) -> np.ndarray | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT embedding FROM chunk_cache WHERE hash = ? AND model = ?",
                (hash_, model),
            ).fetchone()
        if row is None:
            return None
        return np.frombuffer(row[0], dtype=np.float32)

    def put(self, hash_: str, model: str, tokens: int, embedding: np.ndarray) -> None:
        import time

        blob = embedding.astype(np.float32).tobytes()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO chunk_cache (hash, model, tokens, embedding, created_at) VALUES (?, ?, ?, ?, ?)",
                (hash_, model, tokens, blob, time.time()),
            )
            self._conn.commit()

    def stats(self) -> dict:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) FROM chunk_cache").fetchone()[0]
            tokens = self._conn.execute("SELECT COALESCE(SUM(tokens),0) FROM chunk_cache").fetchone()[0]
        return {"cached_chunks": total, "cached_tokens": tokens}

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM chunk_cache")
            self._conn.execute("DELETE FROM doc_state")
            self._conn.commit()

    # ---- document state ------------------------------------------------------

    def get_doc_state(self, doc_id: str) -> tuple[str, list[str]] | None:
        import json

        with self._lock:
            row = self._conn.execute(
                "SELECT hash, chunk_ids FROM doc_state WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
        if row is None:
            return None
        return row[0], json.loads(row[1])

    def set_doc_state(self, doc_id: str, doc_hash: str, chunk_ids: list[str]) -> None:
        import json
        import time

        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO doc_state (doc_id, hash, chunk_ids, updated_at) VALUES (?, ?, ?, ?)",
                (doc_id, doc_hash, json.dumps(chunk_ids), time.time()),
            )
            self._conn.commit()

    def delete_doc_state(self, doc_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM doc_state WHERE doc_id = ?", (doc_id,))
            self._conn.commit()

    def all_doc_ids(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute("SELECT doc_id FROM doc_state").fetchall()
        return [r[0] for r in rows]


_cache_instance: EmbeddingCache | None = None


def get_cache() -> EmbeddingCache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = EmbeddingCache()
    return _cache_instance
