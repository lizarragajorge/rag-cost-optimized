# RAG Cost-Optimized Demo (Azure AI Foundry)

A small web app that demonstrates **how to slash re-indexing costs** for a Foundry
agent's knowledge base when the underlying document corpus is large and changes
frequently.

The demo runs side-by-side comparisons between:

| Strategy | What it does | Typical cost on re-runs |
| --- | --- | --- |
| **Naive full re-index** | Re-chunks and re-embeds every document on every run | $$$$ (linear with corpus size) |
| **Smart incremental re-index** | Hash-based change detection + persistent embedding cache: only new or changed chunks are re-embedded | ~$0 when nothing changed; ~delta cost otherwise |

You will see:

1. A live **cost dashboard** showing tokens embedded, cache hits, and $ saved.
2. A **document editor** so you can mutate the corpus and watch the optimized
   path skip everything that did not change.
3. A **query panel** that asks questions against the locally-indexed knowledge
   base (or, when configured, against a real Azure AI Search index attached to a
   real Foundry agent).

---

## How the optimization works

```
                       ┌─────────────────────────────────────────┐
   Document  ──hash──▶ │ Doc-level cache  (skip whole document?) │
                       └─────────────────────────────────────────┘
                                       │ miss
                                       ▼
                       ┌─────────────────────────────────────────┐
   Chunks    ──hash──▶ │ Chunk-level cache (skip per-chunk?)     │
                       └─────────────────────────────────────────┘
                                       │ miss
                                       ▼
                       ┌─────────────────────────────────────────┐
                       │ Embedding API (the only $$$ step)       │
                       └─────────────────────────────────────────┘
```

Both caches are persisted in a local SQLite DB (`backend/data/cache.db`) so they
survive restarts — the same model you would use in production with Redis,
Cosmos DB, or Azure Table Storage as the cache backend.

---

## Run it locally

```bash
docker compose up --build
```

Then open <http://localhost:8000>.

To run without Docker:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Demo script (suggested)

1. **Open the app.** Sample corpus is auto-loaded.
2. Click **"Naive Full Re-index"** — note the cost (e.g. `$0.0142`, `~71k tokens`).
3. Click **"Smart Incremental Re-index"** — first run costs the same.
4. Click **"Smart Incremental Re-index"** again — cost is **$0.00**, every
   chunk hits the cache.
5. Edit one paragraph of one document and save.
6. Click **"Naive Full Re-index"** — full cost again (`$0.0142`).
7. Click **"Smart Incremental Re-index"** — only the changed chunks of that
   one document are re-embedded (e.g. `$0.0002`, `~1k tokens`).
8. The **savings counter** at the top accumulates the cost avoided.

---

## Scaling to 5 GB and beyond (Scale Lab)

The seed corpus is intentionally tiny so the demo runs in seconds. The
**Scale Lab** card lets you show the same optimization story at realistic
enterprise scale without spending real money or waiting hours for embeddings:

| Preset | Docs × KB | Approx size |
| --- | --- | --- |
| Tiny   | 50 × 100 KB    | ~5 MB    |
| Small  | 500 × 100 KB   | ~50 MB   |
| Medium | 2,000 × 100 KB | ~200 MB  |
| Large  | 5,000 × 200 KB | ~1 GB    |

Click a preset to write a synthetic corpus to disk in seconds. Then:

1. Run **"Naive Full Re-index"** once to populate the cache.
2. Click **"Mutate ~5%"** (or 25%) to simulate daily churn.
3. Run **"Smart Incremental Re-index"** — only the changed slice is re-embedded.
   With the tiny preset and 5% churn we measure **~99.9% savings** on the
   second run.

### Projecting to 5 GB / 50 GB / 1 TB

Embedding 5 GB of text in real time costs minutes and dollars, so the lab
**calibrates** on whatever is currently in your corpus (tokens-per-MB,
chunks-per-doc, etc.) and then **projects** linearly to bigger tiers.
Use the **Churn %** and **Refreshes/year** sliders to model your scenario,
then read the projection table.

Sample output from the smoke test at 5% daily churn × 365 refreshes/year
(`text-embedding-3-small`, $0.02 / 1M tokens):

| Tier   | Docs (est.) | Tokens         | Naive / run | Smart / run | Annual saved |
| ------ | ----------- | -------------- | ----------- | ----------- | ------------ |
| 100 MB | 1,298       | 20.9 M         | $0.42       | $0.02       | $145         |
| 1 GB   | 13,296      | 214 M          | $4.29       | $0.21       | $1,486       |
| **5 GB** | **66,482** | **1.07 B**   | **$21.43**  | **$1.07**   | **$7,432**   |
| 50 GB  | 664,828     | 10.7 B         | $214.34     | $10.72      | $74,323      |
| 1 TB   | 13.6 M      | 219 B          | $4,389.72   | $219.49     | $1,522,137   |

### Safety caps

Real embedding of 1 TB would exhaust memory and budgets, so the indexer has
guardrails enabled by default:

- `MAX_INDEX_CHUNKS=25000` — the in-memory vector index caps at 25k chunks and
  surfaces a `note` when it skips beyond that. Cost accounting is unaffected.
- Embeddings are batched (64 / batch) and AI Search pushes are batched
  (500 / batch).
- The JSON snapshot of the vector index is skipped above 50k chunks to keep
  disk I/O bounded.

To run a Large preset (~1 GB) end-to-end, raise `MAX_INDEX_CHUNKS` in `.env`
and give the container enough RAM (~6 GB).

---

## Connect a real Foundry agent (optional)

By default the demo uses a **simulated embedding model** (deterministic vectors
from content hash) so it runs offline. To wire it to real Azure resources,
copy `.env.example` to `.env` and fill in:

```ini
# Real Azure OpenAI embeddings (instead of simulation)
AZURE_OPENAI_ENDPOINT=https://<your-aoai>.openai.azure.com/
AZURE_OPENAI_API_KEY=<key>
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small

# Push the optimized index to Azure AI Search so a Foundry agent can use it
AZURE_AI_SEARCH_ENDPOINT=https://<your-search>.search.windows.net
AZURE_AI_SEARCH_API_KEY=<key>
AZURE_AI_SEARCH_INDEX=rag-cost-demo

# (optional) Have the demo query a Foundry agent that has this index attached
FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com/api/projects/<project>
FOUNDRY_AGENT_ID=asst_xxx
```

With those set, every "Smart Incremental Re-index" run will push **only the
delta** to Azure AI Search via `mergeOrUpload` actions — the same pattern you'd
use in production to keep Foundry agent grounding fresh without paying to
re-embed everything every night.

---

## Provision the Azure back-end (one command)

The repo includes Bicep + `azd` config that creates a **dedicated resource
group** with the AI Foundry account, both model deployments, the AI Search
service, and a Foundry project. A post-provision hook writes every connection
string into `backend/.env` so the app picks it up automatically.

### Prerequisites
- [Azure Developer CLI (`azd`)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd)
- An Azure subscription with **Cognitive Services** + **Search** quota in your
  chosen region (`eastus2` recommended)
- Owner or Contributor + User Access Administrator at subscription scope
  (so RBAC role assignments can be made for your user)

### Provision

```bash
azd auth login
azd env new ragcost-demo
azd env set AZURE_LOCATION eastus2
# Optional: if Search reports InsufficientResourcesAvailable in your region,
# put it in a different region (the AI Foundry account stays in AZURE_LOCATION):
# azd env set RAGCOST_SEARCH_LOCATION eastus
azd provision
```

`azd provision` will:

1. Create resource group `rg-ragcost-ragcost-demo`
2. Deploy one `Microsoft.CognitiveServices/accounts` (kind=AIServices,
   `allowProjectManagement=true`, `disableLocalAuth=true`) with
   `text-embedding-3-small` (Standard 50K TPM) and `gpt-4o-mini`
   (GlobalStandard 50K TPM) deployments
3. Deploy a Foundry project `rag-cost-project`
4. Deploy `Microsoft.Search/searchServices` (Basic SKU, `disableLocalAuth=true`,
   semantic + vector)
5. Grant your user **Cognitive Services OpenAI User**, **Azure AI Developer**,
   **Search Service Contributor**, and **Search Index Data Contributor**;
   grant the Foundry project's managed identity **Search Index Data Reader**
6. Run [postprovision.ps1](infra/hooks/postprovision.ps1) /
   [postprovision.sh](infra/hooks/postprovision.sh), which writes the resulting
   endpoints (no keys) into `backend/.env`

> **Auth model.** Both the AIServices account and the AI Search service have
> `disableLocalAuth: true`, so the app uses `DefaultAzureCredential` for every
> data-plane call. Make sure you've run `az login` on the machine running the
> demo. No API keys are written to `.env`.

The local app now serves real embeddings and pushes deltas to AI Search.

### Wire the Foundry agent (optional)

For the full round-trip (edit doc → smart re-index → grounded agent answer):

```bash
cd backend
.venv\Scripts\Activate.ps1     # or `source .venv/bin/activate`
pip install -r requirements.txt
python scripts/setup_foundry_agent.py
```

This idempotent script will:

1. Create (or reuse) an Azure AI Search connection on the Foundry project
2. Create (or update) an agent named `rag-cost-demo-agent` wired to that
   connection and the `rag-cost-demo` index
3. Append `FOUNDRY_AGENT_ID=asst_xxx` to `backend/.env`

Restart the app and the query panel will route through the agent — answers
come grounded in the same index the demo just incrementally updated.

### Tear down

```bash
azd down --purge
```

This deletes the resource group and **purges** the soft-deleted AIServices
account so the name can be reused immediately.

### Cost expectations

| Item | Idle/month | Active/day (this demo) |
| --- | --- | --- |
| AIServices account (S0) | $0 (pay per token) | < $0.05 for embeddings + a few agent runs |
| AI Search (Basic) | ~$75 | (already paid) |
| Foundry project | $0 | (charged via the underlying model) |

The Basic Search SKU is the floor. Drop to free tier if you only need the
index-push code to exercise correctly (no vectors at any real volume).

---

## Project layout

```
backend/
  app/
    main.py            FastAPI app + static file serving
    config.py          Settings (env-driven)
    corpus.py          Document store (filesystem-backed)
    chunker.py         Paragraph-aware chunking
    hasher.py          Stable content hashing
    cache.py           SQLite-backed embedding cache
    embedder.py        Simulated + real Azure OpenAI embeddings
    indexer.py         Naive vs incremental indexing strategies
    cost.py            Token + $ accounting
    generator.py       Synthetic corpus generator (Scale Lab)
    scale.py           Calibration + cost projection (Scale Lab)
    foundry_client.py  AI Search push + Foundry agent SDK call
    routes/            HTTP endpoints (incl. /api/scale/*)
  scripts/
    setup_foundry_agent.py   Create the Foundry agent + Search connection
  data/sample_corpus/  Seed documents
frontend/
  index.html           Dashboard UI
  app.js               Client logic
  style.css            Styling
infra/
  main.bicep           Subscription-scope entry (creates resource group)
  resources.bicep      RG-scope resources (AIServices + Search + project)
  main.parameters.json
  hooks/               postprovision scripts (write backend/.env)
azure.yaml             azd config (infra only — no services to deploy)
docker-compose.yml
```
