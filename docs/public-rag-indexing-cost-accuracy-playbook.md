# RAG Indexing Cost, Consistency, and Accuracy Guidance

This document provides implementation guidance for teams building retrieval-augmented generation (RAG) solutions with:
- Microsoft Copilot Studio
- Azure AI Search
- Azure OpenAI embeddings

The focus is reducing indexing cost while improving answer consistency, citation quality, and operational maintainability.

## Scope

Use this guide when your solution has one or more of the following symptoms:
- recurring high indexing costs
- frequent re-index cycles with low net content change
- variable answers for similar prompts
- weak attribution between indexing runs and cost spikes

## Reference Architecture

1. Content sources (SharePoint, blob, files, etc.)
2. Ingestion and refresh pipeline
3. Chunking and embedding stage
4. Azure AI Search index for retrieval
5. Copilot Studio configured to ground responses on the index

Recommended operating split:
- Copilot Studio handles authoring and conversation experience
- Azure AI Search handles indexing and grounding configuration close to the knowledge source
- Teams validate answer quality in Copilot Studio against a fixed question set after changes

## Observed Gaps in Common Implementations

The following patterns frequently appear in enterprise RAG implementations and often lead to higher cost or lower answer quality.

1. Broad refresh behavior instead of true incremental reuse
- A refresh pipeline may reprocess large portions of the corpus even when only a small percentage changed.

2. Larger embedding model selected by default
- A higher-cost embedding model is sometimes used without first validating whether a smaller model meets retrieval needs.

3. High chunk overlap
- Overlap settings can increase duplicated tokens and inflate embedding cost.

4. Low-signal extracted text is embedded
- OCR artifacts, repeated file markers, or boilerplate content may be embedded even though they add little retrieval value.

5. Formal answer-quality gates are missing
- Solutions often rely on non-standardized testing workflows instead of fixed question sets, citation checks, and contradiction review.

These gaps are not specific to any one product, tenant, or implementation. They are recurring patterns that can be addressed through model right-sizing, chunk tuning, content cleanup, and repeatable validation.

## Priority Improvement Plan

### P0: Immediate savings and control

Current pattern:
- broad/full reprocessing during refresh cycles
- expensive embedding model selected by default

Recommended pattern:
- use incremental refresh as the default path
- use a smaller embedding model by default unless evaluation proves otherwise
- reserve full rebuild for schema/model migration events

Implementation notes:
```json
{
  "embedding": {
    "deploymentId": "text-embedding-3-small",
    "dimensions": 1536
  },
  "refreshMode": "incremental"
}
```

Why this is first:
- largest reduction in recurring cost
- fastest time-to-value for most environments

### P1: Cost-performance tuning

Current pattern:
- high chunk overlap
- low-signal extracted text included in embeddings

Recommended pattern:
- reduce overlap to an evaluated baseline
- remove noisy OCR and boilerplate before embedding
- validate retrieval quality with a fixed evaluation set

Implementation notes:
```json
{
  "textSplitMode": "pages",
  "maximumPageLength": 2500,
  "pageOverlapLength": 300
}
```

```text
cleanText -> chunk -> embed -> index
```

Why this matters:
- reduces duplicated embedding tokens
- improves retrieval precision and citation quality

## Best Practices for Low-Signal Extracted Text

Low-signal extracted text should be removed before chunking and embedding whenever possible.

Common low-signal patterns:
- repeated image or attachment file markers
- boilerplate headers and footers repeated on every page
- OCR artifacts and scanning noise
- duplicate whitespace blocks and broken line wraps
- page numbers and navigation fragments that do not help retrieval

Recommended practices:
1. clean text before chunking, not after embedding
2. remove repeated file-marker lines and obvious extraction artifacts
3. normalize whitespace and line breaks before hashing and chunking
4. preserve meaningful labels, tables, and section names if they are useful for retrieval
5. validate cleanup rules against a fixed question set before rollout

Example cleanup flow:

```text
extract -> cleanText -> chunk -> embed -> index
```

Example cleanup rules:

```text
- remove repeated image*.png style lines
- collapse duplicate blank lines
- remove repeated document headers/footers
- keep semantic headings and policy labels
```

Validation guidance:
- compare token volume before and after cleanup
- verify that citations still point to the expected documents
- verify that answer quality does not regress for key business questions

### P2: Answer consistency and accuracy

Current pattern:
- similar prompts may return inconsistent wording or conflicting values
- citation quality is not always validated before promotion

Recommended pattern:
- maintain a golden question set
- require citation checks for numeric/policy claims
- enforce conflict-aware response behavior
- gate promotion on quality thresholds

Implementation notes:
```json
{
  "qualityGate": {
    "citationPassRate": ">= 95%",
    "contradictionRate": "<= 2%"
  }
}
```

Why this matters:
- improves user trust and answer reliability
- reduces escalation due to contradictory responses

## Best Practices for Answer-Quality Gates

Answer-quality gates should be applied before promoting indexing, chunking, or model changes.

Recommended gate categories:
1. answer correctness
2. citation presence
3. citation relevance
4. contradiction handling
5. consistency across repeated prompts

Recommended minimum thresholds:

```json
{
  "citationPassRate": ">= 95%",
  "contradictionRate": "<= 2%",
  "criticalQuestionPassRate": ">= 95%"
}
```

Recommended workflow:
1. maintain a golden question set in source control
2. run the same questions after every material change
3. score the results against the gate categories
4. block promotion if thresholds are not met
5. add newly discovered failure cases back into the golden question set

Manual execution path:
1. open the Copilot Studio test pane
2. run the golden questions one by one
3. record pass/fail in a shared tracker
4. compare against the previous baseline

Recommended tracker fields:
- question id
- answer correct
- citation present
- citation relevant
- contradiction handled
- notes

## Cost Estimation Model

Per-run estimate:

$$
\text{run cost} = \frac{\text{tokens embedded}}{1{,}000{,}000} \times \text{price per 1M tokens}
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
- model selection controls unit cost
- incremental refresh controls embedded volume
- combining both usually yields the largest annual savings

## Validation Workflow

Validate both retrieval and answer behavior across these layers:

1. Copilot Studio test pane
- validate final user-facing answer quality and citations

2. Azure AI Search Search Explorer
- validate retrieval quality and returned chunks

3. Agent playground (if used)
- validate grounding behavior and instruction changes

4. Internal API test harness
- run regression checks after indexing/model/chunking changes

## Golden Question Sets

Golden question sets are a fixed list of business-relevant prompts used to validate answer quality after indexing, chunking, or model changes.

Recommended storage:
- keep the file in source control
- use JSON or CSV
- keep schema stable across releases

Recommended minimum fields:
- `id`
- `question`
- `mustCite`
- `expectedSources`
- `expectedAnswerContains`
- `notes`

Example artifact:
- `docs/golden-questions.example.json`

Recommended manual workflow:
1. store the golden questions in a versioned file
2. make the indexing, chunking, or model change
3. open Copilot Studio test pane
4. run the same questions manually
5. record pass/fail for correctness, citations, and contradiction handling

## Quality Gate Checklist

Before promoting refresh/model/chunking changes:
1. run golden question set
2. verify citation presence for critical claims
3. verify citation relevance
4. measure contradiction rate
5. compare against prior baseline and approve/reject

## Public Sharing Safety Checklist

Before publishing externally:
1. remove tenant names, subscription IDs, resource names, and hostnames
2. remove credentials, keys, connection strings, and tokens
3. remove internal document URLs and private file paths
4. replace environment values with placeholders
5. verify screenshots do not expose sensitive metadata

Example safe placeholders:
- `https://<search-service>.search.windows.net`
- `<embedding-deployment-name>`
- `<knowledge-index-name>`
