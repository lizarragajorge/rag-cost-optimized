from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import generator, scale

router = APIRouter(prefix="/api/scale", tags=["scale"])


class GenerateIn(BaseModel):
    preset: str | None = None         # "tiny" | "small" | "medium" | "large"
    doc_count: int | None = Field(None, gt=0, le=50_000)
    kb_per_doc: int | None = Field(None, gt=0, le=1024)
    clear_existing_synthetic: bool = True
    seed: int = 1234


@router.get("/presets")
def presets() -> dict:
    return generator.PRESETS


@router.post("/generate")
def generate(body: GenerateIn) -> dict:
    if body.preset:
        preset = generator.PRESETS.get(body.preset)
        if not preset:
            raise HTTPException(400, f"unknown preset '{body.preset}'")
        doc_count = preset["doc_count"]
        kb_per_doc = preset["kb_per_doc"]
    else:
        if not body.doc_count or not body.kb_per_doc:
            raise HTTPException(400, "provide either a preset or both doc_count and kb_per_doc")
        doc_count = body.doc_count
        kb_per_doc = body.kb_per_doc
    try:
        report = generator.generate_corpus(
            doc_count=doc_count,
            kb_per_doc=kb_per_doc,
            seed=body.seed,
            clear_existing_synthetic=body.clear_existing_synthetic,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "documents_written": report.documents_written,
        "bytes_written": report.bytes_written,
        "mb_written": round(report.bytes_written / (1024 * 1024), 2),
        "elapsed_ms": round(report.elapsed_ms, 1),
    }


@router.post("/remove-synthetic")
def remove() -> dict:
    return {"removed": generator.remove_synthetic()}


@router.post("/calibrate")
def calibrate() -> dict:
    return scale.calibrate().to_dict()


class ProjectIn(BaseModel):
    churn_pct: float = Field(5.0, ge=0.0, le=100.0)
    refreshes_per_year: int = Field(365, ge=1, le=8760)


@router.post("/project")
def project(body: ProjectIn) -> dict:
    cal = scale.calibrate()
    rows = scale.project(cal, churn_pct=body.churn_pct, refreshes_per_year=body.refreshes_per_year)
    return {
        "calibration": cal.to_dict(),
        "churn_pct": body.churn_pct,
        "refreshes_per_year": body.refreshes_per_year,
        "rows": [r.to_dict() for r in rows],
    }
