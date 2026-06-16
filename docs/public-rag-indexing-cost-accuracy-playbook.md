# RAG Indexing Cost, Consistency, and Accuracy Playbook (Public)

This guide is safe to share publicly.
It is written for teams using:
- Microsoft Copilot Studio
- Azure AI Search
- Azure OpenAI embeddings

It explains how to reduce indexing cost while improving answer consistency and citation accuracy.

## Public Demo Walkthrough (8-10 minutes)
Use this if you are presenting the approach to another team.

1. Start with the problem in one sentence.
- "We are paying full-price indexing repeatedly even when only a small portion of content changes."

2. Show the cost model quickly.
- Explain that indexing cost is driven by embedded tokens and model price.
- State that two levers matter most: model choice and amount of content re-embedded.

3. Explain the before/after operating pattern.
- Before: broad/full refresh behavior and expensive embedding defaults.
- After: incremental refresh + right-sized embedding model + quality gates.

4. Walk through priorities (P0 to P3).
- P0: immediate savings and control
- P1: tuning + observability
- P2: answer consistency and citation accuracy
- P3: strategic scale optimization

5. Demonstrate where quality is tested.
- Copilot Studio test pane for end-user answers
- Search Explorer for retrieval quality
- Optional agent playground and API harness for regression checks

6. Close with rollout plan.
- Week 1: baseline cost + quality
- Week 2: incremental default path
- Week 3: model/chunking A/B validation
- Week 4: production gates and scorecards

## Repo References (Safe to share)
- Main project overview: `README.md`
- Suggested baseline demo flow: `README.md` section "Suggested demo flow"
- Portal walkthrough notes: `docs/portal-walkthrough.md`
- Public playbook (this doc): `docs/public-rag-indexing-cost-accuracy-playbook.md`

## Audience
- Product owners and platform teams operating enterprise RAG
- Teams seeing high recurring indexing costs
- Teams that need consistent, evidence-backed answers

## Problem Pattern
A common high-cost pattern looks like this:
1. A broad refresh or re-index operation runs frequently.
2. Most content is re-chunked and re-embedded each run.
3. A high-cost embedding model is used by default.
4. Answer quality checks are informal, so consistency varies.

## Priority Plan

### P0: Immediate savings and risk control
Current pattern:
- Full or broad reprocessing during refresh cycles
- Expensive embedding model as default

Recommended pattern:
- Make incremental refresh the default path
- Use a smaller embedding model by default (unless evaluation proves otherwise)
- Treat full rebuild as an exception workflow

Why:
- Indexing cost is driven by embedded tokens
- Spend should scale with changed content, not full corpus size

### P1: Cost-performance tuning
Current pattern:
- High chunk overlap and noisy extracted text

Recommended pattern:
- Reduce overlap to a tested baseline
- Clean low-signal text (OCR artifacts, repetitive boilerplate)
- Validate retrieval and answer quality with a fixed evaluation set

Why:
- Duplicate/noisy text increases embedding volume without improving usefulness

### P1: Observability and governance
Current pattern:
- Aggregate cloud bill exists, but run-level attribution is weak

Recommended pattern:
- Emit run telemetry for every refresh
- Track by source/profile and publish weekly scorecards

Suggested run output fields:
- `runId`
- `documentsSeen`
- `documentsSkipped`
- `chunksEmbedded`
- `tokensEmbedded`
- `estimatedCostUsd`
- `durationMs`
- `failedItems`

Why:
- Teams cannot manage cost or quality drift without run-level visibility

### P2: Answer consistency and accuracy
Current pattern:
- Similar prompts can return variable wording, missing citations, or mixed values

Recommended pattern:
- Build a golden question set (30-50 representative questions)
- Require citation checks for numeric/policy answers
- Add contradiction checks and explicit multi-value handling
- Gate production promotion on quality thresholds

Why:
- Reliability for users means repeatable, evidence-backed answers

### P3: Strategic optimization
Current pattern:
- One broad index and enrichment profile for many domains

Recommended pattern:
- Segment by domain where needed
- Use tiered refresh cadence by content volatility
- Remove enrichment outputs that are not used in retrieval/answering

Why:
- Improves long-term maintainability, relevance, and cost predictability

## Model Cost Comparison Framework
Use the same corpus and refresh cadence when comparing embedding models.

Per-run estimate:

$$
\text{run cost} = \frac{\text{tokens embedded}}{1,000,000} \times \text{price per 1M tokens}
$$

Annual estimate:

$$
\text{annual cost} = \text{run cost} \times \text{refreshes per year}
$$

Incremental estimate at churn rate $c$:

$$
\text{incremental tokens per run} = \text{full tokens per run} \times c
$$

Interpretation:
- Smaller embedding model lowers unit cost
- Incremental refresh lowers embedded token volume
- Combining both usually creates the largest annual savings

## Where to Test Questions and Answers
Use all four layers for complete validation:

1. Copilot Studio test pane
- Validate end-user answer quality and citation behavior

2. Azure AI Search Search Explorer
- Validate retrieval quality (returned chunks and relevance)

3. Agent playground (if used)
- Validate grounding and instruction behavior before broad rollout

4. Internal app/API query test harness
- Run regression checks after indexing/model/chunking changes

## Practical Quality Gate (Recommended)
Before promoting a refresh/model/chunking change:
1. Run golden question set
2. Check citation presence for critical claims
3. Check citation relevance (does citation support answer)
4. Check contradiction rate
5. Compare against prior baseline and approve/reject

## Operating Model
- Copilot Studio: authoring and user experience
- Managed refresh service: indexing logic and guardrails
- Automation (Power Automate/Logic Apps): schedule/manual triggers
- Platform + product owners: shared scorecard for cost and quality

## Safe Publishing Checklist
Before publishing this guide publicly:
1. Remove tenant names, subscription IDs, resource group names, hostnames, and project names
2. Remove all credentials, keys, connection strings, and bearer tokens
3. Remove internal file paths or document URLs that reveal company content
4. Replace sample data with placeholders like `<search-service-name>` and `<project-name>`
5. Confirm screenshots (if any) do not expose PII or sensitive metadata

## Redaction Examples
Do this:
- `https://<search-service>.search.windows.net`
- `<embedding-deployment-name>`
- `<knowledge-index-name>`

Do not publish this:
- Real `ApplicationSecret` values
- Full SharePoint/OneDrive internal document URLs
- Real tenant/resource identifiers tied to production

---

If you adapt this playbook internally, keep a private version with environment-specific details and a public version with redacted examples only.
