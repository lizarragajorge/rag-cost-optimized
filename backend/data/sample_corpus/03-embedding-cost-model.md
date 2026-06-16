# Embedding Cost Model

Embedding spend has three components: **tokens × price × frequency**.

## Tokens

Embedding APIs are billed per input token. For Azure OpenAI:

- `text-embedding-3-small` — 1536 dimensions, low cost.
- `text-embedding-3-large` — 3072 dimensions, ~6× the per-token cost.

For most retrieval workloads, `text-embedding-3-small` is the right
default. Switch to `large` only after measuring that the smaller model
actually misses relevant chunks for your domain.

The number of tokens per document is fairly predictable: roughly 4
characters per token for English prose, less for code, less for
non-Latin scripts. The total embedding bill for one full indexing pass is:

```
tokens_per_pass = sum(tokens(chunk) for chunk in all_chunks)
cost_per_pass   = tokens_per_pass × price_per_token
```

## Frequency

The trap most teams fall into is treating indexing as a daily or hourly
batch job that always processes the full corpus. With a 10 GB corpus at
~250 tokens per chunk and `text-embedding-3-small` at $0.02 per million
tokens, a full nightly reindex costs:

- ~40M chunks × 250 tokens = 10B tokens
- 10B / 1M × $0.02 = **$200 per night**
- $73,000 per year, almost entirely for re-embedding text that did not
  change.

With the incremental pattern, you pay only for the chunks that actually
changed. For a corpus with ~1% daily churn, that's ~$2/night, or **$730 per
year** — a 99% reduction.

## Storage is not the bottleneck

Vector storage in Azure AI Search is priced per replica per partition. For
the same 10 GB corpus, a single Standard S1 replica costs ~$250/month, or
$3,000/year. That's significant but it's a fixed cost — adding more
re-indexing passes does not change it.

The takeaway: **optimize the frequency of embedding calls, not the storage
footprint** unless your index is in the multi-hundred-GB range.

## Query-time cost

Query embeddings are also billed, but the per-call cost is tiny (one
embedding per user question). The dominant cost on the query side is the
LLM completion tokens consumed by the agent's response, not the embedding
of the question. Unless you have millions of queries per day, query-time
embeddings are not worth optimizing.
