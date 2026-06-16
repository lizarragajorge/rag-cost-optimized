"""Token + dollar accounting.

A single source of truth for what an indexing operation cost, so the dashboard
and the API report consistent numbers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .config import get_settings


@dataclass
class CostReport:
    strategy: str                # "naive" | "incremental"
    documents_seen: int = 0
    documents_skipped: int = 0   # whole-doc cache hits
    chunks_seen: int = 0
    chunks_embedded: int = 0     # cache misses
    chunks_cache_hit: int = 0
    tokens_embedded: int = 0
    tokens_would_have_embedded: int = 0  # what naive would have done
    elapsed_ms: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        rate = get_settings().price_per_mtoken_embedding
        return (self.tokens_embedded / 1_000_000.0) * rate

    @property
    def naive_equivalent_usd(self) -> float:
        rate = get_settings().price_per_mtoken_embedding
        return (self.tokens_would_have_embedded / 1_000_000.0) * rate

    @property
    def savings_usd(self) -> float:
        return max(0.0, self.naive_equivalent_usd - self.cost_usd)

    @property
    def savings_pct(self) -> float:
        if self.tokens_would_have_embedded == 0:
            return 0.0
        return 100.0 * (1.0 - self.tokens_embedded / self.tokens_would_have_embedded)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["cost_usd"] = round(self.cost_usd, 6)
        d["naive_equivalent_usd"] = round(self.naive_equivalent_usd, 6)
        d["savings_usd"] = round(self.savings_usd, 6)
        d["savings_pct"] = round(self.savings_pct, 2)
        return d
