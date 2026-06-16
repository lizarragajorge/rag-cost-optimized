# Portal Walkthrough — Wire a Copilot Studio agent to a cost-optimized AI Search index

Audience: **Copilot Studio authors** who want to ground their copilot in their
own documents, and want to know how to keep that knowledge fresh without paying
to re-embed everything every night.

This walkthrough is **speaker-notes style** — short numbered steps, click-paths
in **bold**, and call-outs for what to verify on each screen. It mirrors the
running demo in this repo, so attendees can follow along in the Azure portal
while the local app proves the cost numbers.

---

## What we're building (one slide)

```
 ┌──────────────────────┐   refresh job   ┌────────────────────┐    grounding
 │ Source docs          │ ──────────────▶ │  Azure AI Search   │ ◀──────────────┐
 │ (SharePoint, blob,   │  (this demo)    │  index             │                │
 │  Git, Confluence…)   │                 └────────────────────┘                │
 └──────────────────────┘                                                       │
                                                                                │
                                                              ┌─────────────────┴───────┐
                                                              │ Copilot Studio copilot  │
                                                              │   "Knowledge" tab       │
                                                              └─────────────────────────┘
```

- Copilot Studio is the **consumer**. It points its **Knowledge** at an Azure
  AI Search index.
- *Someone* still has to keep that index fresh. That "someone" is the
  re-indexing pipeline in this repo, which uses **document & chunk hashing +
  an embedding cache** to only re-embed what actually changed.
- Without this pattern, a full nightly re-embed of a 10 GB corpus costs
  ~$200/night = $73k/year. With it, ~$2/night = $730/year. **Same answers,
  ~99% less spend.**

---

## Map of what you'll click

| # | Portal | URL | Why |
| - | --- | --- | --- |
| 1 | **Azure Portal** | https://portal.azure.com | Create or inspect the AI Foundry + AI Search resources |
| 2 | **Azure AI Foundry** | https://ai.azure.com | Deploy embedding/chat models, create the agent, attach the index |
| 3 | **Azure AI Search** (inside Azure Portal) | https://portal.azure.com | Verify the index has content (Search Explorer) |
| 4 | **Microsoft Copilot Studio** | https://copilotstudio.microsoft.com | Add the AI Search index as a Knowledge source on a copilot |

> **Shortcut for live demos**: parts 1–2 are exactly what `azd provision`
> in this repo does in one command (see [the README](../README.md#provision-the-azure-back-end-one-command)).
> If you've already run that, skip to part 3.

---

## Part 1 — Provision the Azure resources (Azure Portal)

> **Goal**: end up with one **Azure AI Foundry** resource and one **Azure AI
> Search** resource in the same resource group.

### 1.1 Create the resource group

1. Azure Portal → top search bar → **"Resource groups"** → **+ Create**.
2. Subscription: pick yours. Region: **East US 2** (good model availability).
3. Name: `rg-copilot-knowledge-demo`. Click **Review + create** → **Create**.

### 1.2 Create the Azure AI Foundry resource

> This is what the portal currently calls **"Azure AI Foundry"** (formerly
> "Azure AI Hub/Project"). In ARM it's `Microsoft.CognitiveServices/accounts`
> with `kind=AIServices`.

1. Azure Portal search → **"Azure AI Foundry"** → **+ Create** → **AI Foundry**.
2. Basics:
   - Resource group: `rg-copilot-knowledge-demo`
   - Region: **East US 2**
   - Name: anything globally unique (e.g. `myorg-foundry-001`)
   - Pricing tier: **Standard S0**
3. Network: **All networks** (for the demo). Production should use Private
   Endpoint.
4. Identity: leave **System-assigned managed identity** **On**. The demo
   needs the project MI to read Search.
5. Tags → Review + create → **Create**.

   > **Speaker call-out**: tell the audience this resource is the *home* for
   > both **models** (deployments) and **agents** (the things Copilot Studio
   > or a custom app will talk to).

### 1.3 Create the Azure AI Search service

1. Azure Portal search → **"Azure AI Search"** → **+ Create**.
2. Basics:
   - Resource group: `rg-copilot-knowledge-demo`
   - Service name: anything globally unique (e.g. `myorg-search-001`)
   - Region: **East US** (Search regions don't have to match Foundry)
   - Pricing tier: **Basic** (cheapest tier that supports vector search at
     real volume; ~$75/month)
3. Scale: leave at defaults for the demo (1 replica, 1 partition).
4. Networking: **Public**.
5. **Authentication**:
   - For **production**: choose **Role-based access control** only (no API
     keys). This is what this demo uses (`disableLocalAuth=true`).
   - For a **Copilot Studio demo today**: choose **Both** (keys + RBAC). The
     Copilot Studio AI Search knowledge connector still asks for an admin
     key in most regions; see the call-out in **Part 4**.
6. Review + create → **Create**.

### 1.4 Wire RBAC (so identities can talk to each other)

Open the **AI Foundry** resource → **Access control (IAM)** → **+ Add role
assignment** and grant:

| Role | Assignee | Why |
| --- | --- | --- |
| **Cognitive Services OpenAI User** | *Your user* | So you can call the embedding & chat models from your laptop / azd |
| **Azure AI Developer** | *Your user* | So you can create / edit Foundry projects & agents |

Now open the **AI Search** resource → **Access control (IAM)** → **+ Add role
assignment** and grant:

| Role | Assignee | Why |
| --- | --- | --- |
| **Search Service Contributor** | *AI Foundry → System-assigned MI* | The agent uses the project MI to call Search; needs this to read index schema |
| **Search Index Data Reader** | *AI Foundry → System-assigned MI* | Lets the agent actually read documents from the index |
| **Search Service Contributor** + **Search Index Data Contributor** | *Your user* | So the refresh job (this demo) can create the index and push documents |

> **Demo trip-wire**: if you skip **Search Service Contributor** on the
> Foundry MI, the agent fails at query time with
> `search_access_error; Forbidden`. RBAC propagation is 60–120 s — go grab
> water before testing.

---

## Part 2 — Configure Foundry (ai.azure.com)

Open **https://ai.azure.com** and sign in.

### 2.1 Create a Foundry **project**

> A project is a workspace inside the AI Foundry resource — it owns the
> connections, prompts, evaluations, and the agents.

1. Top-right account picker → confirm the right tenant.
2. **+ New project** → pick the AI Foundry resource you created in **1.2**.
3. Name: `copilot-knowledge-project` → **Create**.

### 2.2 Deploy the two models you need

Left rail → **Models + endpoints** → **+ Deploy model**.

| Model | Deployment name | Why | Tier |
| --- | --- | --- | --- |
| `text-embedding-3-small` | `text-embedding-3-small` | Embeds your documents *and* the user's question | Standard, 50K TPM |
| `gpt-4o-mini` | `gpt-4o-mini` | The chat model the agent uses to answer | GlobalStandard, 50K TPM |

> **Speaker call-out**: embedding cost ≠ chat cost. `text-embedding-3-small`
> is **$0.02 per 1M tokens** — pennies to embed a whole knowledge base.
> The expensive thing is doing it **every night for content that didn't
> change**, which is exactly what the demo fixes.

### 2.3 Connect the Foundry project to the Search service

Left rail → **Management center** → **Connected resources** → **+ New
connection** → **Azure AI Search**.

1. Pick the search service from **1.3**.
2. Authentication: **Microsoft Entra ID** (no keys). This works because of
   the RBAC you assigned in **1.4**.
3. Name the connection `aisearch-knowledge` → **Add**.

> **Why this matters for Copilot Studio**: this connection is what lets the
> Foundry **agent** retrieve from the index. Copilot Studio itself talks to
> the index directly — but if you're using Foundry agents as a backing
> service for Copilot Studio (via Direct Line / custom skill), the agent
> needs this connection.

### 2.4 Create the agent

Left rail → **Agents** → **+ New agent**.

1. Name: `knowledge-agent`. Model: `gpt-4o-mini`.
2. **Instructions** (the system prompt): something short like
   > *"Answer using the connected knowledge base. Cite the file name in each
   > answer. If the answer isn't in the knowledge base, say you don't know."*
3. **Tools / Knowledge** → **+ Add** → **Azure AI Search**:
   - Connection: `aisearch-knowledge`
   - Index: leave blank for now — we'll create it from the refresh job in
     part 3. (Or pre-create an empty index in the portal.)
4. **Create**. Note the agent ID (looks like `asst_xxxxxxxxxxxxx`) — you'll
   need it if you wire this agent to Copilot Studio later.

---

## Part 3 — Populate (and verify) the index

> The portal can browse an index but **cannot create vector content** for
> you. That's what the refresh job does. The demo in this repo is one
> implementation of that job; in production you'd swap the corpus loader for
> SharePoint, blob storage, Confluence, etc.

### 3.1 Run the demo's smart re-index

From the repo root:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --port 8000
```

In another terminal:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/index/incremental
```

The first call creates the index `rag-cost-demo` and pushes the seed corpus
(5 markdown files → 10 chunks). The second call is **$0.00** because the
chunk hashes already match the cache — that's the point of the demo.

### 3.2 Verify the index in the portal

1. Azure Portal → your AI Search service → **Indexes** → click the index
   name (`rag-cost-demo`).
2. You should see **Document count: 10**, fields including `chunk_id`,
   `doc_id`, `title`, `text`, `vector` (1536 dims).
3. Open the **Search Explorer** tab → query string `*` → **Search**. You
   should see the chunked seed documents.

> **Speaker call-out**: now is a good time to switch back to the demo's web
> UI (`http://localhost:8000`) and edit one document. Click **Smart
> Incremental Re-index** and show that only the chunks of the edited document
> get re-embedded — cost drops to almost zero. That is the production story.

---

## Part 4 — Plug the index into Copilot Studio

Open **https://copilotstudio.microsoft.com** and sign in to the same tenant.

### 4.1 Pick or create a copilot

1. Top bar → **Create** → **New agent** → give it a name like
   `Knowledge Copilot`.
2. Skip the conversational design wizard for now — go straight to the
   **Knowledge** tab on the left rail.

### 4.2 Add the Azure AI Search index as a Knowledge source

1. **Knowledge** → **+ Add knowledge** → **Advanced** → **Azure AI Search**.
2. Fill in:
   - **Search endpoint**: `https://<your-search-service>.search.windows.net`
   - **Index name**: `rag-cost-demo`
   - **Authentication**:
     - Best path (when available in your region): **Managed identity** —
       then grant the Copilot Studio environment's MI **Search Index Data
       Reader** on the index (Azure Portal → Search → IAM).
     - Fallback: **Admin key** — copy from Azure Portal → Search → **Keys**.
       (This requires that you chose **Both** auth modes in step **1.3**.
       If you locked the service to RBAC-only, you'll need to flip
       `disableLocalAuth` to `false` temporarily or switch to managed
       identity.)
3. **Field mapping**: this is the bit that bites people.
   - **Content fields**: `text`, `title`
   - **Filename / title field**: `title`
   - **Vector field**: `vector` (dimensions: 1536)
   - **Embedding model**: pick the same one used to *write* the index. In
     this demo that's `text-embedding-3-small` on your Foundry resource —
     Copilot Studio will ask you to pick a connection to it.
4. **Add**.

> **Speaker call-out**: the field mapping has to match what the refresh job
> wrote. If you change the index schema in code, you have to come back to
> Copilot Studio and re-map. Have one chunk schema and stick to it.

### 4.3 Turn on grounding and test

1. **Overview** → **Generative AI** → set **Generative answers** to **On**
   and **Knowledge sources** to your AI Search index only (no public web).
2. **Test your copilot** panel on the right → ask
   *"How does incremental indexing reduce embedding cost?"*
3. You should get a grounded answer with citations to the file names from
   the seed corpus.

### 4.4 Publish

1. Top right → **Publish**.
2. **Channels** → enable **Teams**, **Demo website**, or whatever surface
   your audience uses.

---

## Part 5 — Bring the cost story home

After they've seen the copilot answer questions, switch tabs back to the
local demo UI (`http://localhost:8000`) and show:

| What you click | What they see | What it proves |
| --- | --- | --- |
| **Naive Full Re-index** | $0.000052, 13 s, 10 chunks embedded | Baseline: every refresh pays the full embedding bill |
| **Smart Incremental** | $0.00, 172 ms, 5/5 docs skipped | With hashing + cache: identical index, ~0 cost |
| Edit one document, then **Smart Incremental** | $0.0000X, only the changed chunks re-embed | Only the *delta* is paid for — same pattern works at 10 GB |
| **Scale Lab** card → push **Medium** preset and read the projection table | At 5% daily churn × 365 refreshes, 5 GB tier saves $7.4k/year | The number gets meaningful at production scale |

Land the close like this:

> *"Copilot Studio gave you the chat experience for free. The bill you'll
> actually see on the invoice is **embeddings × frequency**. Hash the
> documents, cache the chunks, and you can refresh the knowledge base as
> often as you want — the math stops scaling with corpus size and starts
> scaling with how much actually changed."*

---

## Appendix — Common portal-side issues

| Symptom | Where to look | Fix |
| --- | --- | --- |
| Copilot Studio "Add Knowledge → Azure AI Search" rejects the endpoint | AI Search → **Keys** | If `disableLocalAuth=true` and your tenant's Copilot Studio doesn't yet support MI for Search, flip local auth back on, or pre-create a managed identity connection in Copilot Studio admin |
| Agent in ai.azure.com returns "Forbidden" when answering | AI Search → **IAM** | Foundry MI is missing **Search Service Contributor** (not just Reader). Add it and wait 60–120 s |
| Copilot Studio returns "I don't know" for every question | Search Explorer in the portal | Index is empty. Run the refresh job (`POST /api/index/incremental`) at least once |
| Foundry portal shows 0 model deployments | ai.azure.com → **Models + endpoints** | Quotas / capacity. Use Region = East US 2 or request capacity for your preferred region |
| Re-indexing the same content keeps costing money | Demo's **Status** card — `cached_chunks` | Cache file (`backend/data/cache.db`) got wiped. In production, point the cache at Redis / Cosmos and you won't lose state between restarts |

