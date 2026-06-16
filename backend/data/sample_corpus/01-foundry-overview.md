# Azure AI Foundry Overview

Azure AI Foundry is a unified platform for building, deploying, and operating
generative AI applications. It provides project-level governance, a model
catalog spanning Azure OpenAI, Mistral, Meta, and Hugging Face models, and a
managed Agents service for production workloads.

## Projects and resources

A Foundry **project** is the unit of collaboration. It bundles together
deployed models, datasets, indexes, connections (to Azure AI Search, Cosmos
DB, Storage, and more), evaluations, and the agents themselves. Projects live
inside an **AI Services** resource and inherit its quotas and pricing.

Resource-level RBAC controls who can create models or modify connections.
Project-level RBAC controls who can run experiments, deploy agents, and view
traces. The recommended starting point is to assign the **Azure AI User** role
at the project scope to your developers and to keep the **Azure AI Account
Owner** role limited to platform admins.

## Agents

A Foundry agent is a managed orchestrator that combines an LLM, a set of
**tools** (function calling, code interpreter, OpenAPI, MCP, browser, file
search), one or more **knowledge sources** (Azure AI Search, vector stores,
SharePoint, Fabric), and a system prompt. The Agents service handles thread
management, tool invocation, and observability.

## Knowledge sources

Knowledge sources ground the model's responses in your data. The two most
common patterns are:

1. **Azure AI Search** as a vector + keyword hybrid index. You manage the
   index and its refresh cadence; the agent issues `search` calls on every
   turn that requires grounding.
2. **File search vector stores** managed by the Agents service. You upload
   files and the service handles chunking, embedding, and retrieval — at the
   cost of less control over the embedding model and refresh strategy.

For large corpora that change frequently, **bring-your-own Azure AI Search**
gives you the most cost leverage because you control exactly when and how
embeddings are computed.

## Cost levers

The three biggest cost lines for a knowledge-grounded agent are typically:

- **Embedding generation** during indexing and re-indexing.
- **Vector storage** in AI Search (proportional to index size and replicas).
- **LLM tokens** during agent turns (prompt + completion + tool-call I/O).

This demo focuses on the first line because, for slowly-changing corpora,
embedding cost grows linearly with re-index frequency — and almost all of it
is avoidable.
