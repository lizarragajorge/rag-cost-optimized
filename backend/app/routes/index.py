from __future__ import annotations

from fastapi import APIRouter

from .. import indexer

router = APIRouter(prefix="/api/index", tags=["index"])


@router.post("/naive")
def naive() -> dict:
    return indexer.naive_reindex().to_dict()


@router.post("/incremental")
def incremental() -> dict:
    return indexer.incremental_reindex().to_dict()


@router.post("/clear")
def clear() -> dict:
    indexer.clear_everything()
    return {"status": "cleared"}
