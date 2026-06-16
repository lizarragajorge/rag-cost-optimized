from __future__ import annotations

from fastapi import APIRouter

from ..embedder import embed_texts
from ..foundry_client import ask_foundry_agent
from ..indexer import get_index
from ..models import QueryHit, QueryIn, QueryOut

router = APIRouter(prefix="/api/query", tags=["query"])


@router.post("", response_model=QueryOut)
def query(body: QueryIn) -> QueryOut:
    result = embed_texts([body.q])
    if not result.embeddings:
        return QueryOut(answer="(empty query)", hits=[], foundry_used=False)
    hits_raw = get_index().search(result.embeddings[0], k=body.k)
    hits = [QueryHit(**h) for h in hits_raw]

    foundry_resp = ask_foundry_agent(body.q)
    if foundry_resp:
        answer = foundry_resp["answer"]
        foundry_used = True
    else:
        if hits:
            answer = (
                "Top match (local index): "
                + hits[0].text[:400]
                + ("..." if len(hits[0].text) > 400 else "")
            )
        else:
            answer = "No matches yet — run a re-index first."
        foundry_used = False
    return QueryOut(answer=answer, hits=hits, foundry_used=foundry_used)
