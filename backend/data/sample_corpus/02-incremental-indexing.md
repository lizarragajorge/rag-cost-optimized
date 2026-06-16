# Incremental Indexing Patterns

Most production knowledge bases are nearly static between refreshes. A
nightly job that re-embeds every document every night is, in the typical
case, doing 95–99% redundant work. The patterns below let you pay only for
the actual delta.

## Pattern 1: Document-level hashing

Compute a stable hash of each document's normalized text. Store
`(doc_id → hash)` in any durable store: SQL, Cosmos DB, Azure Table, Redis.

On the next indexing pass, compare the freshly computed hash against the
stored one. If they match, **skip the document entirely** — no chunking, no
embedding, no index update. Only the documents whose hash changed go through
the rest of the pipeline.

This pattern alone typically removes 90%+ of the cost for content that
changes daily but is mostly stable.

## Pattern 2: Chunk-level hashing

Even for changed documents, most chunks are usually unchanged. If you hash
each chunk's normalized text and cache `(chunk_hash → embedding_vector)`,
you can reuse the embedding for any chunk whose hash matches a previous run.

The cache backend is up to you. For a single-region deployment, Redis is
convenient. For multi-region or audit-friendly setups, Cosmos DB or a
dedicated SQL table works well. The vector itself is small (a few KB) so
storage cost is negligible compared to embedding cost.

## Pattern 3: Stable chunk boundaries

The chunk-level cache only pays off if chunk boundaries are stable across
runs. Strategies that hurt cache hit rate:

- Fixed-window chunking with overlap (one paragraph insertion shifts every
  subsequent chunk).
- Sentence-window chunking with strict sentence counts.

Strategies that help:

- Paragraph-aware chunking that respects natural breakpoints.
- Heading-aware chunking for Markdown / DOCX / HTML.
- Recursive splitters that prefer larger semantic units.

In this demo we use a simple paragraph-aware chunker: a single paragraph
edit invalidates only the chunk containing that paragraph.

## Pattern 4: Blue/green index swap

When you do need to do a large reindex (model change, schema change), build
a new index alongside the old one and atomically swap the agent's
connection. This avoids degraded results while the index rebuilds and lets
you roll back instantly.

In Azure AI Search this is two REST calls: create the new index, then update
the agent's connection to point at it.
