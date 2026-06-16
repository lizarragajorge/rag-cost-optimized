# Operational Checklist for Cost-Aware RAG

A short, opinionated checklist for keeping the indexing bill of a Foundry
agent's knowledge base under control as the corpus grows.

## Before you index

- Pick `text-embedding-3-small` as the default. Only upgrade after a
  measurable recall problem on your domain.
- Pick paragraph- or heading-aware chunking. Avoid fixed-window chunking
  with overlap unless you have a specific reason.
- Define a stable `chunk_id` scheme (`doc_id:ordinal`) so cache lookups
  work across runs.

## During indexing

- Hash documents and chunks. Persist both hashes in a durable cache.
- Re-embed only chunks whose hash is not in the cache.
- For the AI Search upload step, use `mergeOrUpload` so unchanged fields
  are not re-written. This keeps indexing throughput high and avoids
  unnecessary churn on the inverted index.
- Batch uploads (500 docs per call is a safe default).

## After indexing

- Emit a run summary with: documents seen, documents skipped, chunks
  embedded, tokens embedded, dollars spent, dollars avoided. This is the
  single most useful piece of telemetry for catching regressions.
- Alert when the embedded-token count for a run exceeds the moving average
  by more than 3×. That usually means something changed every document
  (e.g. a header rewrite) and your cache is now useless.

## Once a quarter

- Review the cache hit rate trend. If it has dropped, look for chunking
  instability: a new chunker version, a new normalization step, or a
  template change that touched every file.
- Reconsider the embedding model. If you have moved to hybrid retrieval
  and your `small` recall is solid, there is no upside to switching to
  `large`. If you have not moved to hybrid retrieval yet, do that before
  considering an upgrade.

## Anti-patterns to avoid

- Re-indexing the full corpus "just to be safe" after every change.
- Storing the embedding cache in the same database as your application
  data without an eviction policy — embedding vectors are small but they
  add up over years.
- Using the file search vector store for a corpus you also need to ground
  other tools or downstream pipelines on. Manage your own AI Search index
  in that case.
