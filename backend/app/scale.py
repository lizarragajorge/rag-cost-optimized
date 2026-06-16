"""Scale calibration + cost projection.

The cost model for embedding is linear in tokens:

    cost_per_run_naive   = total_tokens × $/token
    cost_per_run_smart   = changed_tokens × $/token
    annual_savings       = (cost_per_run_naive − cost_per_run_smart) × refreshes_per_year

We measure (tokens / MB, chunks / doc, MB / doc) from the current corpus and
extrapolate to a fixed schedule of scale tiers. This avoids actually embedding
gigabytes of text just to make the point.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass

from .chunker import chunk_document
from .config import get_settings
from .corpus import list_documents


@dataclass
class Calibration:
    sample_docs: int
    sample_bytes: int
    sample_tokens: int
    sample_chunks: int
    tokens_per_mb: float
    chunks_per_mb: float
    avg_doc_kb: float
    avg_chunks_per_doc: float
    elapsed_ms: float

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("tokens_per_mb", "chunks_per_mb", "avg_doc_kb",
                  "avg_chunks_per_doc", "elapsed_ms"):
            d[k] = round(d[k], 2)
        return d


@dataclass
class ProjectionRow:
    label: str
    size_mb: float
    docs: int
    chunks: int
    tokens: int
    full_reindex_cost: float
    smart_reindex_cost_at_churn: float
    churn_pct: float
    refreshes_per_year: int
    annual_naive: float
    annual_smart: float
    annual_saved: float
    pct_saved: float

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("size_mb", "full_reindex_cost", "smart_reindex_cost_at_churn",
                  "annual_naive", "annual_smart", "annual_saved", "pct_saved"):
            d[k] = round(d[k], 4)
        return d


# A reasonable default for English prose when there's no corpus to measure
# against (≈4 chars per token → ~256 K tokens per MB).
DEFAULT_TOKENS_PER_MB = 256_000.0
DEFAULT_CHUNKS_PER_MB = DEFAULT_TOKENS_PER_MB / 300.0  # 300 tokens per chunk target


def calibrate() -> Calibration:
    """Chunk every current document (no embedding) and measure throughput."""
    start = time.perf_counter()
    docs = list_documents()
    total_bytes = 0
    total_tokens = 0
    total_chunks = 0
    for d in docs:
        total_bytes += len(d.text.encode("utf-8"))
        chunks = chunk_document(d.doc_id, d.text)
        total_chunks += len(chunks)
        total_tokens += sum(c.token_count for c in chunks)

    mb = max(total_bytes / (1024 * 1024), 1e-9)
    return Calibration(
        sample_docs=len(docs),
        sample_bytes=total_bytes,
        sample_tokens=total_tokens,
        sample_chunks=total_chunks,
        tokens_per_mb=total_tokens / mb if total_bytes else DEFAULT_TOKENS_PER_MB,
        chunks_per_mb=total_chunks / mb if total_bytes else DEFAULT_CHUNKS_PER_MB,
        avg_doc_kb=(total_bytes / 1024) / max(len(docs), 1),
        avg_chunks_per_doc=total_chunks / max(len(docs), 1),
        elapsed_ms=(time.perf_counter() - start) * 1000.0,
    )


_PROJECTION_TIERS: list[tuple[str, float]] = [
    ("100 MB", 100.0),
    ("1 GB",   1024.0),
    ("5 GB",   5 * 1024.0),
    ("50 GB",  50 * 1024.0),
    ("1 TB",   1024 * 1024.0),
]


def project(
    cal: Calibration,
    churn_pct: float = 5.0,
    refreshes_per_year: int = 365,
) -> list[ProjectionRow]:
    """Extrapolate naive vs smart costs to the standard scale tiers."""
    s = get_settings()
    price_per_token = s.price_per_mtoken_embedding / 1_000_000.0

    tokens_per_mb = cal.tokens_per_mb if cal.tokens_per_mb > 0 else DEFAULT_TOKENS_PER_MB
    chunks_per_mb = cal.chunks_per_mb if cal.chunks_per_mb > 0 else DEFAULT_CHUNKS_PER_MB
    avg_doc_bytes = (cal.avg_doc_kb * 1024) if cal.avg_doc_kb > 0 else 100 * 1024

    churn = max(0.0, min(churn_pct, 100.0)) / 100.0
    rows: list[ProjectionRow] = []
    for label, mb in _PROJECTION_TIERS:
        tokens = tokens_per_mb * mb
        chunks = chunks_per_mb * mb
        docs = int((mb * 1024 * 1024) / avg_doc_bytes) if avg_doc_bytes else 0

        full_cost = tokens * price_per_token
        smart_cost = full_cost * churn  # first-order: changed % of tokens

        annual_naive = full_cost * refreshes_per_year
        annual_smart = smart_cost * refreshes_per_year
        annual_saved = annual_naive - annual_smart
        pct_saved = 100.0 * (1.0 - churn)

        rows.append(ProjectionRow(
            label=label,
            size_mb=mb,
            docs=docs,
            chunks=int(chunks),
            tokens=int(tokens),
            full_reindex_cost=full_cost,
            smart_reindex_cost_at_churn=smart_cost,
            churn_pct=churn_pct,
            refreshes_per_year=refreshes_per_year,
            annual_naive=annual_naive,
            annual_smart=annual_smart,
            annual_saved=annual_saved,
            pct_saved=pct_saved,
        ))
    return rows
