# Azure AI Search and Copilot Studio Configuration Guide

This document describes how to configure Azure AI Search, Azure AI Foundry, and Copilot Studio for a RAG solution that supports lower indexing cost and consistent answer quality.

## Prerequisites

- Azure subscription with required quotas for Azure AI Search and Azure AI Foundry
- Permissions to create resources and assign RBAC roles
- Azure Developer CLI (`azd`) or Azure Portal access

## Target Architecture

1. Azure AI Foundry resource and project
2. Azure OpenAI model deployments
3. Azure AI Search service and index
4. Azure AI Search indexing configuration and content refresh path
5. Copilot Studio configured to use the index as a knowledge source

## 1. Provision Azure Resources

### 1.1 Create a resource group

Create a resource group in your preferred region.

### 1.2 Create Azure AI Foundry resource

Configure:
- kind: AIServices
- pricing tier: Standard S0
- managed identity: enabled

### 1.3 Create Azure AI Search service

Configure:
- pricing tier: Basic or higher for production vector workloads
- authentication:
  - RBAC-only for strict production controls, or
  - both RBAC and keys if required by specific connectors/tools

## 2. Assign Required Access

### 2.1 Roles on Azure AI Foundry

Assign to operator identity:
- Cognitive Services OpenAI User
- Azure AI Developer

### 2.2 Roles on Azure AI Search

Assign to Foundry managed identity:
- Search Service Contributor
- Search Index Data Reader

Assign to ingestion operator/service principal:
- Search Service Contributor
- Search Index Data Contributor

Notes:
- RBAC propagation can take several minutes
- Missing Search Service Contributor can cause forbidden errors during grounded queries

## 3. Configure Foundry Project

In Azure AI Foundry:

1. Create a project.
2. Deploy models:
   - `text-embedding-3-small`
   - `gpt-4o-mini` (or chosen chat model)
3. Add an Azure AI Search connection using Microsoft Entra ID.
4. Create agent and attach the Azure AI Search knowledge tool.

## 4. Populate and Verify Azure AI Search Index

Use your indexing path to write chunks and vectors into the target index.

Example local run pattern:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --port 8000
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/index/incremental
```

Verify in Azure AI Search:

1. Open the index definition and confirm fields are present (ID, text, vector, metadata).
2. Use Search Explorer to validate retrieval with sample queries.
3. Validate that repeated incremental runs do not re-embed unchanged content.

## 5. Configure Copilot Studio Knowledge Source

In Copilot Studio:

1. Open the target copilot and navigate to Knowledge.
2. Add Azure AI Search as a knowledge source.
3. Provide:
   - search endpoint
   - index name
   - authentication method (managed identity or key-based as required)
4. Configure field mapping to match index schema:
   - content fields
   - title/filename fields
   - vector field and dimensions

Important:
- Keep field mapping synchronized with index schema changes.
- If schema changes, update Copilot Studio mapping before validation.

## 6. Validation Workflow

### 6.1 Retrieval validation

Use Search Explorer to confirm relevant chunks are returned.

### 6.2 Answer validation

Use Copilot Studio test pane to validate:
- citation presence
- citation relevance
- answer consistency for repeated prompts

### 6.3 Regression validation

Run a golden question set after indexing/model/chunking changes.

### 6.4 Manual validation workflow

For a simple first implementation:

1. Keep a golden question set in source control as JSON or CSV.
2. Make the indexing, chunking, or model change.
3. Open the Copilot Studio test pane.
4. Run the same questions manually.
5. Record pass/fail for:
   - answer correctness
   - citation presence
   - citation relevance
   - contradiction handling

## 7. Cost and Quality Optimization Recommendations

1. Use smaller embedding model by default unless quality evaluation requires a larger model.
2. Use incremental refresh instead of broad/full re-index.
3. Tune chunk overlap to reduce duplicate token embedding.
4. Remove low-signal extraction artifacts before embedding.
5. Validate every significant change against the same golden question set.

### 7.1 Low-signal text cleanup

Apply cleanup before chunking and embedding.

Examples:
- repeated image or attachment markers
- duplicated headers and footers
- OCR artifacts and repeated whitespace

Recommended sequence:

```text
extract -> cleanText -> chunk -> embed -> index
```

### 7.2 Answer-quality gates

Use a fixed question set to validate changes.

Recommended checks:
- answer correctness
- citation presence
- citation relevance
- contradiction handling

Recommended first implementation:
1. keep the golden questions in JSON or CSV in source control
2. run them manually in Copilot Studio test pane after changes
3. record pass/fail in a shared tracker

## 8. Troubleshooting

### Symptom: grounded answers fail with forbidden errors

Check:
- Foundry managed identity role assignments on Search
- RBAC propagation delay

### Symptom: Copilot responses show no grounded results

Check:
- index contains data
- field mappings match index schema
- knowledge source points to correct index

### Symptom: repeated runs remain expensive

Check:
- incremental path is actually being used
- chunk/document hash reuse is functioning
- overlap/noise settings are not inflating token volume

## 9. Public Documentation Safety

When sharing externally, remove:
- tenant and subscription identifiers
- hostnames and resource names from production
- credentials, keys, tokens, and internal URLs
