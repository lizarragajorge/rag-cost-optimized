"""End-to-end smoke test that exercises the demo without launching uvicorn.

Runs:
1. naive_reindex      -> capture cost A
2. incremental_reindex (1st time) -> should match cost A (cold cache)
3. incremental_reindex (2nd time, no edits) -> should cost $0
4. mutate one doc, incremental_reindex -> should cost << A
5. query the index -> should return at least one hit
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `import app` when run from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import corpus, indexer
from app.cache import get_cache
from app.embedder import embed_texts
from app.generator import generate_corpus, remove_synthetic
from app.indexer import get_index
from app.scale import calibrate, project


def show(label: str, r) -> None:
    print(f"--- {label} ---")
    print(f"  strategy            : {r.strategy}")
    print(f"  docs seen / skipped : {r.documents_seen} / {r.documents_skipped}")
    print(f"  chunks seen         : {r.chunks_seen}")
    print(f"  chunks embedded     : {r.chunks_embedded}")
    print(f"  chunks cache hit    : {r.chunks_cache_hit}")
    print(f"  tokens embedded     : {r.tokens_embedded}")
    print(f"  tokens (naive eq.)  : {r.tokens_would_have_embedded}")
    print(f"  cost USD            : {r.cost_usd:.6f}")
    print(f"  saved USD           : {r.savings_usd:.6f}")
    print(f"  elapsed ms          : {r.elapsed_ms:.1f}")
    if r.notes:
        print("  notes:")
        for n in r.notes:
            print(f"    - {n}")


def main() -> int:
    # Start from a clean state.
    corpus.reset_to_seed()
    remove_synthetic()
    indexer.clear_everything()

    naive = indexer.naive_reindex()
    show("1. naive_reindex (cold)", naive)
    assert naive.tokens_embedded > 0, "naive must embed tokens"
    assert naive.chunks_embedded == naive.chunks_seen, "naive must embed every chunk"

    # Wipe cache + index so incremental run #1 is fair (cold).
    indexer.clear_everything()
    inc_cold = indexer.incremental_reindex()
    show("2. incremental_reindex (cold cache, no skips)", inc_cold)
    assert inc_cold.tokens_embedded == naive.tokens_embedded, (
        f"cold incremental must equal naive ({inc_cold.tokens_embedded} vs {naive.tokens_embedded})"
    )

    inc_warm = indexer.incremental_reindex()
    show("3. incremental_reindex (warm, no edits)", inc_warm)
    assert inc_warm.tokens_embedded == 0, "warm-cache run must embed nothing"
    assert inc_warm.documents_skipped == inc_warm.documents_seen, "every doc should be skipped"

    # Mutate one document.
    docs = corpus.list_documents()
    target = docs[0]
    edited_text = target.text + "\n\nNEW PARAGRAPH added at " + str(__import__("time").time()) + "."
    corpus.save_document(target.doc_id, edited_text)

    inc_after_edit = indexer.incremental_reindex()
    show("4. incremental_reindex (one paragraph edit)", inc_after_edit)
    assert inc_after_edit.tokens_embedded > 0, "edit must trigger at least one embedding"
    assert inc_after_edit.tokens_embedded < naive.tokens_embedded // 2
    assert inc_after_edit.documents_skipped == len(docs) - 1

    # Query the local index.
    q = "How does incremental indexing reduce cost?"
    qvec = embed_texts([q]).embeddings[0]
    hits = get_index().search(qvec, k=3)
    print("--- 5. query ---")
    print(f"  hits  : {len(hits)}")
    for h in hits[:2]:
        print(f"    [{h['score']:.3f}] {h['doc_id']} :: {h['text'][:80]}…")
    assert hits

    # ---- Scale Lab ---------------------------------------------------------
    print("\n=== SCALE LAB ===\n")
    indexer.clear_everything()
    corpus.reset_to_seed()
    remove_synthetic()

    print("Generating 'tiny' synthetic corpus (50 docs × ~100 KB)…")
    gen = generate_corpus(doc_count=50, kb_per_doc=100, seed=42)
    print(f"  wrote {gen.documents_written} docs / {gen.bytes_written / (1024*1024):.2f} MB in {gen.elapsed_ms:.0f} ms")
    assert gen.bytes_written > 4 * 1024 * 1024, "should write at least 4 MB"

    cal = calibrate()
    print(f"  calibration: {cal.sample_docs} docs, {cal.sample_tokens} tokens, "
          f"{cal.tokens_per_mb:.0f} tokens/MB, {cal.avg_chunks_per_doc:.1f} chunks/doc")
    assert cal.sample_tokens > 0
    assert cal.tokens_per_mb > 100_000  # should be ~250k for English prose

    rows = project(cal, churn_pct=5.0, refreshes_per_year=365)
    print("\n  Projection (5% daily churn, 365 refreshes/year):")
    print(f"  {'Tier':<8} {'Docs':>10} {'Tokens':>15} {'Naive/run':>12} {'Smart/run':>12} {'Annual saved':>14}")
    for r in rows:
        print(f"  {r.label:<8} {r.docs:>10,} {r.tokens:>15,} "
              f"${r.full_reindex_cost:>10,.4f}  ${r.smart_reindex_cost_at_churn:>10,.4f}  "
              f"${r.annual_saved:>12,.2f}")
    five_gb = next(r for r in rows if r.label == "5 GB")
    assert five_gb.annual_saved > 100, "5 GB at 5% churn × 365 refreshes should save real money"

    # Run a smart reindex on the synthetic corpus to prove the pipeline handles
    # 50 docs (the cap is much higher so this should just work).
    indexer.clear_everything()
    big_cold = indexer.incremental_reindex()
    show("6. incremental on synthetic corpus (cold)", big_cold)
    assert big_cold.chunks_seen > cal.sample_chunks * 0.9

    big_warm = indexer.incremental_reindex()
    show("7. incremental on synthetic corpus (warm)", big_warm)
    assert big_warm.tokens_embedded == 0

    # Clean up generated files so the repo stays small.
    removed = remove_synthetic()
    print(f"\nCleanup: removed {removed} synthetic docs.")

    print("\nALL SMOKE CHECKS PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
