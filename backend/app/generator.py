"""Synthetic corpus generator.

Produces realistic-looking technical prose so the indexing pipeline can be
exercised on hundreds of MB of data without bundling a real dataset. The
generated text is deterministic per seed so re-running with the same seed
recreates an identical corpus (good for showing 100% cache hits).

For demos we cap practical generation at ~1 GB. Anything larger is reported
via the **projection** path (`app/scale.py`) rather than actually written to
disk.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from pathlib import Path

from .config import get_settings
from .corpus import _working_dir, ensure_seeded

# A small vocabulary of templated paragraphs about a fictional cloud product.
# Each {placeholder} gets a value from VOCAB below at generation time.

_PARAGRAPH_TEMPLATES = [
    "In the {component} subsystem the {role} pipeline handles {action} using {technique}. "
    "Typical {metric} sits at {value} {unit}, which {direction} when the {parameter} is increased. "
    "For workloads in the {scale} tier we recommend you {advice}.",

    "When operating {component} at scale, the {role} layer becomes the dominant {bottleneck}. "
    "The {team} owns this surface and has documented several patterns for {action}: "
    "{technique}, {technique2}, and a fallback to {technique3} for {edge_case}.",

    "Most {role} incidents trace back to {bottleneck} during {action}. The remediation playbook "
    "calls for {advice}, followed by a review of the {component} {metric}. If {metric} stays "
    "above {value} {unit} for more than {scale}, escalate to the {team}.",

    "The {component} module exposes a {role} API that returns {metric} per {parameter}. "
    "Consumers should batch by {scale} to amortize the overhead of {technique}; the "
    "{team} guidance is to never exceed {value} {unit} per call.",

    "{technique} is the cheapest path for {action} when the {component} is in its steady state. "
    "Switch to {technique2} only after measuring {metric} > {value} {unit}. The {team} keeps a "
    "dashboard with these thresholds; alerts fire when {parameter} drifts {direction}.",
]

VOCAB = {
    "component": ["billing", "ingest", "retrieval", "scheduler", "router", "cache",
                  "embedding", "audit", "policy", "telemetry", "rate-limit", "agent-runtime",
                  "knowledge-source", "tool-broker", "session-store", "evaluation"],
    "role": ["control-plane", "data-plane", "background", "edge", "orchestrator",
             "follower", "leader", "proxy"],
    "action": ["indexing", "compaction", "snapshotting", "replication", "fan-out",
               "fan-in", "shard rebalancing", "leader election", "checkpointing",
               "delta computation", "vector upsert", "metadata reconciliation"],
    "technique": ["hash-based deduplication", "delta encoding", "Bloom-filter pruning",
                  "consistent hashing", "log-structured merging", "Merkle-tree diffing",
                  "two-phase commit", "optimistic locking", "back-pressure", "windowed batching"],
    "technique2": ["streaming reads", "snapshot isolation", "vectorized scans",
                   "speculative prefetch", "tiered caching"],
    "technique3": ["full re-scan", "manual reconciliation", "operator intervention"],
    "edge_case": ["cold-start traffic", "regional failover", "tenant onboarding",
                  "schema migration", "model upgrade", "secret rotation"],
    "metric": ["p99 latency", "queue depth", "cache hit rate", "embedding cost per MB",
               "tokens per second", "throughput", "error rate", "tail latency",
               "indexing lag", "vector recall"],
    "value": ["50", "120", "250", "500", "1000", "2500", "5000"],
    "unit": ["ms", "tokens/s", "requests/s", "MB", "dollars per day", "percent", "events/min"],
    "direction": ["degrades linearly", "improves sub-linearly", "regresses sharply",
                  "stabilizes", "plateaus", "spikes intermittently"],
    "parameter": ["concurrency", "batch size", "replica count", "chunk size",
                  "refresh interval", "embedding dimension", "partition count"],
    "scale": ["small (under 1 GB)", "medium (1-100 GB)", "large (100-1000 GB)",
              "very large (over 1 TB)", "single-tenant", "multi-tenant"],
    "advice": ["enable incremental indexing", "increase replicas", "shard by tenant id",
               "raise the chunk target", "switch to hybrid retrieval", "co-locate consumers",
               "pre-warm the cache", "schedule re-index off-peak"],
    "bottleneck": ["I/O wait", "GC pressure", "network egress", "CPU saturation",
                   "embedding API throttling", "lock contention"],
    "team": ["Platform team", "Foundation team", "AI Infra team", "SRE team",
             "Data team", "Search team", "Agents team"],
}


@dataclass
class GenerationReport:
    documents_written: int
    bytes_written: int
    elapsed_ms: float


def _render_paragraph(rng: random.Random) -> str:
    template = rng.choice(_PARAGRAPH_TEMPLATES)
    out = template
    # Replace each placeholder; handle the duplicated {technique}{technique2}{technique3} keys.
    while "{" in out:
        start = out.index("{")
        end = out.index("}", start)
        key = out[start + 1:end]
        # Strip trailing digits to allow {technique2} -> use "technique"
        base = key.rstrip("0123456789")
        pool = VOCAB.get(base, [base])
        out = out[:start] + rng.choice(pool) + out[end + 1:]
    return out


def _render_document(rng: random.Random, paragraphs: int, doc_index: int) -> str:
    title = f"# Synthetic Operations Note {doc_index:06d}"
    sections: list[str] = [title]
    for s in range(1 + paragraphs // 5):
        sections.append(f"## Section {s + 1}: {rng.choice(VOCAB['component']).title()} "
                        f"and {rng.choice(VOCAB['action']).title()}")
        for _ in range(5):
            sections.append(_render_paragraph(rng))
    # Trim to roughly the requested paragraph count.
    return "\n\n".join(sections[:2 + paragraphs])


def estimate_paragraphs_for_size(target_kb_per_doc: int) -> int:
    """A rendered paragraph is ~280 characters; back into a paragraph count."""
    chars_per_paragraph = 280
    return max(3, (target_kb_per_doc * 1024) // chars_per_paragraph)


def generate_corpus(
    doc_count: int,
    kb_per_doc: int,
    *,
    seed: int = 1234,
    name_prefix: str = "synthetic",
    clear_existing_synthetic: bool = True,
) -> GenerationReport:
    """Generate `doc_count` documents of roughly `kb_per_doc` each.

    Safety caps: doc_count <= 50_000, kb_per_doc <= 1024. Larger requests are
    rejected with ValueError — use the projection endpoint for >1 GB scenarios.
    """
    if doc_count <= 0 or kb_per_doc <= 0:
        raise ValueError("doc_count and kb_per_doc must be positive")
    if doc_count > 50_000:
        raise ValueError("doc_count exceeds 50,000 — use the projection endpoint for larger scenarios")
    if kb_per_doc > 1024:
        raise ValueError("kb_per_doc exceeds 1024 — use the projection endpoint for larger scenarios")

    ensure_seeded()
    wd: Path = _working_dir()
    wd.mkdir(parents=True, exist_ok=True)

    if clear_existing_synthetic:
        for stale in wd.glob(f"{name_prefix}-*.md"):
            stale.unlink()

    paragraphs = estimate_paragraphs_for_size(kb_per_doc)
    start = time.perf_counter()
    total_bytes = 0
    for i in range(doc_count):
        # One RNG per document so a single doc regeneration is deterministic.
        rng = random.Random(seed + i)
        text = _render_document(rng, paragraphs, i)
        p = wd / f"{name_prefix}-{i:06d}.md"
        p.write_text(text, encoding="utf-8")
        total_bytes += len(text.encode("utf-8"))

    return GenerationReport(
        documents_written=doc_count,
        bytes_written=total_bytes,
        elapsed_ms=(time.perf_counter() - start) * 1000.0,
    )


def remove_synthetic(name_prefix: str = "synthetic") -> int:
    """Delete all generated documents matching the prefix."""
    wd = _working_dir()
    if not wd.exists():
        return 0
    count = 0
    for p in wd.glob(f"{name_prefix}-*.md"):
        p.unlink()
        count += 1
    return count


# Preset bundles for the UI.
PRESETS: dict[str, dict] = {
    "tiny":   {"doc_count": 50,    "kb_per_doc": 100,  "label": "Tiny",   "approx_size": "~5 MB"},
    "small":  {"doc_count": 500,   "kb_per_doc": 100,  "label": "Small",  "approx_size": "~50 MB"},
    "medium": {"doc_count": 2000,  "kb_per_doc": 100,  "label": "Medium", "approx_size": "~200 MB"},
    "large":  {"doc_count": 5000,  "kb_per_doc": 200,  "label": "Large",  "approx_size": "~1 GB"},
}
