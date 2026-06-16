from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .. import corpus
from ..chunker import chunk_document, count_tokens
from ..config import get_settings
from ..models import DocumentIn, DocumentOut

router = APIRouter(prefix="/api/corpus", tags=["corpus"])


def _to_out(doc: corpus.Document, *, with_chunk_stats: bool = True) -> DocumentOut:
    if with_chunk_stats:
        chunks = chunk_document(doc.doc_id, doc.text)
        chunk_count = len(chunks)
        token_count = sum(c.token_count for c in chunks)
    else:
        chunk_count = 0
        token_count = count_tokens(doc.text)
    return DocumentOut(
        doc_id=doc.doc_id,
        title=doc.title,
        text=doc.text,
        hash=doc.hash,
        token_count=token_count,
        chunk_count=chunk_count,
    )


@router.get("")
def list_all(
    limit: int = Query(default=50, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
) -> dict:
    settings = get_settings()
    capped = min(limit, settings.max_docs_in_listing)
    total = corpus.count_documents()
    docs = corpus.list_documents(limit=capped, skip=skip)
    # Skip per-chunk stats when paging through many docs (it's slow at scale).
    with_stats = total <= 200
    return {
        "total": total,
        "skip": skip,
        "limit": capped,
        "with_stats": with_stats,
        "items": [_to_out(d, with_chunk_stats=with_stats).model_dump() for d in docs],
    }


@router.get("/{doc_id}", response_model=DocumentOut)
def get_one(doc_id: str) -> DocumentOut:
    doc = corpus.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    return _to_out(doc)


@router.put("/{doc_id}", response_model=DocumentOut)
def upsert(doc_id: str, body: DocumentIn) -> DocumentOut:
    if body.doc_id != doc_id:
        raise HTTPException(status_code=400, detail="doc_id mismatch")
    doc = corpus.save_document(doc_id, body.text)
    return _to_out(doc)


@router.delete("/{doc_id}")
def delete(doc_id: str) -> dict:
    ok = corpus.delete_document(doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="document not found")
    return {"deleted": doc_id}


@router.post("/reset")
def reset() -> dict:
    corpus.reset_to_seed()
    return {"status": "ok", "count": corpus.count_documents()}


@router.post("/mutate-random")
def mutate_random(percent: float = Query(default=5.0, ge=0.1, le=100.0)) -> dict:
    """Edit roughly `percent` % of documents at random to simulate churn.

    Useful for showcasing incremental indexing on the generated synthetic
    corpus — re-run "Smart Incremental Re-index" after this to see the
    delta cost vs a full reindex.
    """
    import random
    import time as _t

    docs = corpus.list_documents()
    if not docs:
        return {"mutated": 0, "of": 0}
    n = max(1, int(round(len(docs) * percent / 100.0)))
    picked = random.sample(docs, k=n)
    stamp = _t.time()
    for d in picked:
        new_text = d.text + f"\n\nUPDATED at {stamp:.0f}: see attached change log."
        corpus.save_document(d.doc_id, new_text)
    return {"mutated": n, "of": len(docs), "percent": percent}
