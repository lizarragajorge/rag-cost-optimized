# Azure AI Search Tuning for Foundry Agents

When you bring your own Azure AI Search index to a Foundry agent, a few
settings make a large difference to both cost and answer quality.

## Index schema

Recommended fields for a vector-grounded agent:

- `chunk_id` (Edm.String, key) — stable id like `doc_id:ordinal`.
- `doc_id` (Edm.String, filterable, facetable) — for ACL and filtering.
- `title` (Edm.String, searchable).
- `text` (Edm.String, searchable) — the chunk body, used for hybrid search.
- `vector` (Collection(Edm.Single), vectorSearchProfile=…) — the embedding.

Add `last_modified` (Edm.DateTimeOffset) if you need to express freshness
filters in the agent's query.

## Vector profile

For most workloads, HNSW with the defaults is sufficient. Tune only when
you have measured a problem:

- Lower `m` and `efConstruction` reduce indexing cost at the price of
  recall.
- Higher `efSearch` improves recall at query time at the cost of latency.

For corpora under a few million vectors, the defaults are fine.

## Replicas, partitions, SKU

- Replicas scale query throughput and add HA.
- Partitions scale storage and indexing throughput.
- Start with one of each on Standard S1; scale partitions when you exceed
  ~25 GB of index, scale replicas when query latency suffers.

The Basic SKU is fine for prototypes but does not support vector indexes at
scale and lacks the per-replica HA guarantees required for production.

## Hybrid retrieval

Foundry agents that use AI Search benefit from **hybrid search** (vector +
keyword + semantic ranker). Hybrid retrieval reduces the cost pressure on
embeddings because a strong keyword match can carry weak embedding overlap.

In practice this means the smaller `text-embedding-3-small` is good
enough for most agents that use hybrid retrieval, even on corpora where
pure-vector recall with `small` would be marginal.

## Refresh cadence

The combination of:

1. Incremental indexing on the producer side (this demo).
2. Hybrid retrieval on the agent side.
3. Semantic reranking for the top-N candidates.

…lets most teams move from a nightly full reindex to a 5-minute
incremental refresh **at lower total cost** than the original nightly job.
That cadence is responsive enough for most knowledge-management use cases
without going to streaming change feeds.
