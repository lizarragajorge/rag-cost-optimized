"""Indexing strategies.

`naive_reindex`        — chunk + embed every chunk of every document, even
                          if nothing changed. This is the baseline cost.
`incremental_reindex`  — for each document:
                          1. If the document hash matches the last indexed
                             hash, skip the whole document.
                          2. Otherwise chunk and look up each chunk's hash
                             in the embedding cache. Only cache-miss chunks
                             pay the embedding cost.

Both strategies persist the final vectors in a local in-memory index so the
query endpoint can compare results. When AI Search is configured the
incremental path additionally pushes only the delta to AI Search.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Lock

import numpy as np

from .cache import get_cache
from .chunker import chunk_document
from .config import get_settings
from .corpus import Document, list_documents
from .cost import CostReport
from .embedder import embed_texts
from .foundry_client import push_index_delta, remove_from_index


# ---------------------------------------------------------------------------
# Tiny in-process vector index (so the demo works without AI Search).
# ---------------------------------------------------------------------------


class VectorIndex:
    def __init__(self) -> None:
        self._lock = Lock()
        self._vecs: dict[str, np.ndarray] = {}
        self._meta: dict[str, dict] = {}
        self._skipped_due_to_cap = 0

    @property
    def at_capacity(self) -> bool:
        return len(self._vecs) >= get_settings().max_index_chunks

    def upsert(self, chunk_id: str, vector: np.ndarray, meta: dict) -> None:
        with self._lock:
            cap = get_settings().max_index_chunks
            if chunk_id not in self._vecs and len(self._vecs) >= cap:
                # Already at the soft cap — keep cost accounting but skip the
                # in-memory upsert so we don't OOM on huge corpora.
                self._skipped_due_to_cap += 1
                return
            self._vecs[chunk_id] = vector
            self._meta[chunk_id] = meta

    def reset_skip_counter(self) -> None:
        with self._lock:
            self._skipped_due_to_cap = 0

    def skipped_due_to_cap(self) -> int:
        with self._lock:
            return self._skipped_due_to_cap

    def remove(self, chunk_ids: list[str]) -> None:
        with self._lock:
            for cid in chunk_ids:
                self._vecs.pop(cid, None)
                self._meta.pop(cid, None)

    def remove_doc(self, doc_id: str) -> list[str]:
        with self._lock:
            to_remove = [cid for cid, m in self._meta.items() if m.get("doc_id") == doc_id]
            for cid in to_remove:
                self._vecs.pop(cid, None)
                self._meta.pop(cid, None)
        return to_remove

    def search(self, query_vec: np.ndarray, k: int = 5) -> list[dict]:
        with self._lock:
            if not self._vecs:
                return []
            ids = list(self._vecs.keys())
            matrix = np.stack([self._vecs[i] for i in ids])
            qn = query_vec / (np.linalg.norm(query_vec) + 1e-9)
            mn = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
            scores = mn @ qn
            top = np.argsort(-scores)[:k]
            results = []
            for idx in top:
                cid = ids[idx]
                results.append(
                    {
                        "chunk_id": cid,
                        "score": float(scores[idx]),
                        "doc_id": self._meta[cid]["doc_id"],
                        "title": self._meta[cid].get("title", ""),
                        "text": self._meta[cid].get("text", ""),
                    }
                )
            return results

    def stats(self) -> dict:
        with self._lock:
            return {
                "total_chunks": len(self._vecs),
                "total_docs": len({m["doc_id"] for m in self._meta.values()}),
            }

    def save(self, path: Path) -> None:
        with self._lock:
            payload = {
                "meta": self._meta,
                "vecs": {k: v.tolist() for k, v in self._vecs.items()},
            }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def load(self, path: Path) -> None:
        if not path.exists():
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        with self._lock:
            self._meta = payload.get("meta", {})
            self._vecs = {k: np.array(v, dtype=np.float32) for k, v in payload.get("vecs", {}).items()}

    def clear(self) -> None:
        with self._lock:
            self._vecs.clear()
            self._meta.clear()


_index_instance: VectorIndex | None = None


def get_index() -> VectorIndex:
    global _index_instance
    if _index_instance is None:
        _index_instance = VectorIndex()
        _index_instance.load(get_settings().data_dir / "index.json")
    return _index_instance


def _persist() -> None:
    get_index().save(get_settings().data_dir / "index.json")


# ---------------------------------------------------------------------------
# Cumulative session savings — tracked across runs so the dashboard can show
# "total dollars avoided since startup".
# ---------------------------------------------------------------------------


_session_lock = Lock()
_session_savings = {"naive_spent": 0.0, "incremental_spent": 0.0, "saved": 0.0, "runs": 0}


def session_totals() -> dict:
    with _session_lock:
        return dict(_session_savings)


def _accumulate(report: CostReport) -> None:
    with _session_lock:
        _session_savings["runs"] += 1
        if report.strategy == "naive":
            _session_savings["naive_spent"] += report.cost_usd
        else:
            _session_savings["incremental_spent"] += report.cost_usd
            _session_savings["saved"] += report.savings_usd


def reset_session_totals() -> None:
    with _session_lock:
        _session_savings.update({"naive_spent": 0.0, "incremental_spent": 0.0, "saved": 0.0, "runs": 0})


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


# Batch embedding tunables — keep memory bounded on huge corpora.
_EMBED_BATCH_SIZE = 64
_AI_SEARCH_BATCH_SIZE = 500
# Above this many indexed chunks we skip the JSON snapshot (expensive at scale).
_PERSIST_CHUNK_LIMIT = 50_000


def _maybe_persist() -> None:
    if get_index().stats()["total_chunks"] <= _PERSIST_CHUNK_LIMIT:
        _persist()


def _flush_ai_search_batch(batch: list[dict], report: CostReport) -> None:
    if not batch:
        return
    if not get_settings().ai_search_enabled:
        return
    try:
        push_index_delta(batch)
    except Exception as e:  # noqa: BLE001
        report.notes.append(f"AI Search push failed: {e}")


def naive_reindex() -> CostReport:
    """Re-chunk and re-embed EVERY chunk of EVERY document. No cache, no diff."""
    start = time.perf_counter()
    report = CostReport(strategy="naive")
    index = get_index()
    index.clear()
    index.reset_skip_counter()
    cache = get_cache()
    settings = get_settings()

    docs = list_documents()
    report.documents_seen = len(docs)

    pending_search_batch: list[dict] = []
    total_pushed = 0

    for doc in docs:
        chunks = chunk_document(doc.doc_id, doc.text)
        report.chunks_seen += len(chunks)
        if not chunks:
            continue
        for i in range(0, len(chunks), _EMBED_BATCH_SIZE):
            batch = chunks[i : i + _EMBED_BATCH_SIZE]
            result = embed_texts([c.text for c in batch])
            report.chunks_embedded += len(batch)
            report.tokens_embedded += result.tokens
            for chunk, vector in zip(batch, result.embeddings):
                index.upsert(
                    chunk.chunk_id,
                    vector,
                    {
                        "doc_id": doc.doc_id,
                        "title": doc.title,
                        "text": chunk.text,
                        "tokens": chunk.token_count,
                    },
                )
                cache.put(chunk.hash, result.model, chunk.token_count, vector)
                pending_search_batch.append(
                    {
                        "chunk_id": chunk.chunk_id,
                        "doc_id": doc.doc_id,
                        "title": doc.title,
                        "text": chunk.text,
                        "vector": vector.tolist(),
                    }
                )
            if len(pending_search_batch) >= _AI_SEARCH_BATCH_SIZE:
                _flush_ai_search_batch(pending_search_batch, report)
                total_pushed += len(pending_search_batch)
                pending_search_batch.clear()
        cache.set_doc_state(doc.doc_id, doc.hash, [c.chunk_id for c in chunks])

    if pending_search_batch:
        _flush_ai_search_batch(pending_search_batch, report)
        total_pushed += len(pending_search_batch)

    report.tokens_would_have_embedded = report.tokens_embedded
    report.elapsed_ms = (time.perf_counter() - start) * 1000

    if settings.ai_search_enabled and total_pushed:
        report.notes.append(f"Pushed {total_pushed} docs to AI Search '{settings.azure_ai_search_index}'.")
    skipped = index.skipped_due_to_cap()
    if skipped:
        report.notes.append(
            f"In-memory index cap reached ({settings.max_index_chunks}); skipped {skipped} upserts. "
            "Cost numbers are still exact."
        )

    _maybe_persist()
    _accumulate(report)
    return report


def incremental_reindex() -> CostReport:
    """Hash-based delta: skip unchanged docs entirely; reuse cached chunk
    embeddings for chunks whose text didn't change."""
    start = time.perf_counter()
    report = CostReport(strategy="incremental")
    index = get_index()
    index.reset_skip_counter()
    cache = get_cache()
    settings = get_settings()
    model = settings.embedding_model_name

    docs = list_documents()
    report.documents_seen = len(docs)
    current_doc_ids = {d.doc_id for d in docs}

    # Handle deleted documents: drop their chunks from the index + cache state.
    for stale_doc_id in set(cache.all_doc_ids()) - current_doc_ids:
        removed_chunk_ids = index.remove_doc(stale_doc_id)
        cache.delete_doc_state(stale_doc_id)
        if settings.ai_search_enabled and removed_chunk_ids:
            try:
                remove_from_index(removed_chunk_ids)
            except Exception as e:  # noqa: BLE001
                report.notes.append(f"AI Search delete failed: {e}")
        report.notes.append(f"Removed deleted document '{stale_doc_id}'.")

    delta_for_search: list[dict] = []

    for doc in docs:
        prev = cache.get_doc_state(doc.doc_id)
        if prev and prev[0] == doc.hash:
            report.documents_skipped += 1
            # Still need to count what naive WOULD have spent.
            chunks = chunk_document(doc.doc_id, doc.text)
            naive_tokens = sum(c.token_count for c in chunks)
            report.tokens_would_have_embedded += naive_tokens
            report.chunks_seen += len(chunks)
            report.chunks_cache_hit += len(chunks)
            continue

        chunks = chunk_document(doc.doc_id, doc.text)
        report.chunks_seen += len(chunks)
        report.tokens_would_have_embedded += sum(c.token_count for c in chunks)

        # Drop any old chunks that no longer exist for this doc.
        previous_chunk_ids = set(prev[1]) if prev else set()
        new_chunk_ids = {c.chunk_id for c in chunks}
        orphaned = list(previous_chunk_ids - new_chunk_ids)
        if orphaned:
            index.remove(orphaned)
            if settings.ai_search_enabled:
                try:
                    remove_from_index(orphaned)
                except Exception as e:  # noqa: BLE001
                    report.notes.append(f"AI Search delete failed: {e}")

        # Partition into cache hits vs misses.
        to_embed: list = []
        hits: list[tuple] = []  # (chunk, cached_vector)
        for chunk in chunks:
            cached = cache.get(chunk.hash, model)
            if cached is not None:
                hits.append((chunk, cached))
                report.chunks_cache_hit += 1
            else:
                to_embed.append(chunk)

        # Embed only the misses, in bounded batches.
        for i in range(0, len(to_embed), _EMBED_BATCH_SIZE):
            batch = to_embed[i : i + _EMBED_BATCH_SIZE]
            result = embed_texts([c.text for c in batch])
            report.chunks_embedded += len(batch)
            report.tokens_embedded += result.tokens
            for chunk, vector in zip(batch, result.embeddings):
                cache.put(chunk.hash, result.model, chunk.token_count, vector)
                index.upsert(
                    chunk.chunk_id,
                    vector,
                    {
                        "doc_id": doc.doc_id,
                        "title": doc.title,
                        "text": chunk.text,
                        "tokens": chunk.token_count,
                    },
                )
                delta_for_search.append(
                    {
                        "chunk_id": chunk.chunk_id,
                        "doc_id": doc.doc_id,
                        "title": doc.title,
                        "text": chunk.text,
                        "vector": vector.tolist(),
                    }
                )
            if len(delta_for_search) >= _AI_SEARCH_BATCH_SIZE:
                _flush_ai_search_batch(delta_for_search, report)
                delta_for_search.clear()

        # For cache hits, re-upsert into the live in-memory index.
        for chunk, vector in hits:
            index.upsert(
                chunk.chunk_id,
                vector,
                {
                    "doc_id": doc.doc_id,
                    "title": doc.title,
                    "text": chunk.text,
                    "tokens": chunk.token_count,
                },
            )

        cache.set_doc_state(doc.doc_id, doc.hash, [c.chunk_id for c in chunks])

    if delta_for_search:
        _flush_ai_search_batch(delta_for_search, report)
        if settings.ai_search_enabled:
            report.notes.append(
                f"Pushed delta of {len(delta_for_search)} chunks to AI Search '{settings.azure_ai_search_index}'."
            )

    report.elapsed_ms = (time.perf_counter() - start) * 1000

    skipped = index.skipped_due_to_cap()
    if skipped:
        report.notes.append(
            f"In-memory index cap reached ({settings.max_index_chunks}); skipped {skipped} upserts. "
            "Cost numbers are still exact."
        )

    _maybe_persist()
    _accumulate(report)
    return report


def clear_everything() -> None:
    """Reset cache + vector index + session totals (corpus untouched)."""
    get_cache().clear()
    get_index().clear()
    _persist()
    reset_session_totals()
