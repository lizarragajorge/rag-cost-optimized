"""Optional Azure AI Search + Foundry agent integration.

Everything here no-ops gracefully when the corresponding env vars are unset
(or when the optional `azure-ai-projects` / `azure-identity` packages are not
installed), so the demo continues to run offline. When configured:

* `push_index_delta`     — uploads only the changed chunks (mergeOrUpload)
* `remove_from_index`    — deletes stale chunk ids
* `ensure_index_exists`  — creates a vector-enabled index if missing
* `ask_foundry_agent`    — runs a single-turn query against a Foundry agent
                           whose knowledge source is this AI Search index.

We use the REST APIs directly for AI Search to avoid a heavy SDK install.
For Foundry agents we use `azure-ai-projects` because the project endpoint
authenticates with Entra (no API keys).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import get_settings

log = logging.getLogger("foundry_client")


def _search_headers() -> dict:
    s = get_settings()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if s.ai_search_use_aad:
        from .azure_auth import get_bearer_token
        token = get_bearer_token("https://search.azure.com/.default")
        if not token:
            raise RuntimeError(
                "AZURE_AI_SEARCH_API_KEY is not set and DefaultAzureCredential could "
                "not acquire a token. Run `az login` or set the key."
            )
        headers["Authorization"] = f"Bearer {token}"
    else:
        headers["api-key"] = s.azure_ai_search_api_key
    return headers


def ensure_index_exists() -> bool:
    """Create the AI Search index with a vector field if it doesn't exist."""
    s = get_settings()
    if not s.ai_search_enabled:
        return False
    base = s.azure_ai_search_endpoint.rstrip("/")
    url = f"{base}/indexes/{s.azure_ai_search_index}?api-version=2024-07-01"
    with httpx.Client(timeout=30.0) as client:
        r = client.get(url, headers=_search_headers())
        if r.status_code == 200:
            return True
        if r.status_code not in (404, 403):
            r.raise_for_status()

        body = {
            "name": s.azure_ai_search_index,
            "fields": [
                {"name": "chunk_id", "type": "Edm.String", "key": True, "filterable": True},
                {"name": "doc_id", "type": "Edm.String", "filterable": True, "facetable": True},
                {"name": "title", "type": "Edm.String", "searchable": True},
                {"name": "text", "type": "Edm.String", "searchable": True},
                {
                    "name": "vector",
                    "type": "Collection(Edm.Single)",
                    "searchable": True,
                    "dimensions": s.embedding_dimensions,
                    "vectorSearchProfile": "default-profile",
                },
            ],
            "vectorSearch": {
                "profiles": [{"name": "default-profile", "algorithm": "default-hnsw"}],
                "algorithms": [{"name": "default-hnsw", "kind": "hnsw"}],
            },
        }
        r = client.put(url, headers=_search_headers(), json=body)
        r.raise_for_status()
        return True


def _safe_key(key: str) -> str:
    # AI Search keys only allow letters/digits/_/-/=; our local ids use ':' as a separator.
    return key.replace(":", "__")


def push_index_delta(docs: list[dict]) -> None:
    """Upload changed chunks using mergeOrUpload — the cheap delta operation."""
    if not docs:
        return
    s = get_settings()
    if not s.ai_search_enabled:
        return
    ensure_index_exists()
    url = (
        f"{s.azure_ai_search_endpoint.rstrip('/')}/indexes/"
        f"{s.azure_ai_search_index}/docs/index?api-version=2024-07-01"
    )
    actions = []
    for d in docs:
        doc = dict(d)
        if "chunk_id" in doc:
            doc["chunk_id"] = _safe_key(doc["chunk_id"])
        actions.append({"@search.action": "mergeOrUpload", **doc})
    # AI Search caps batches at 1000 docs / 16 MB.
    for i in range(0, len(actions), 500):
        batch = actions[i : i + 500]
        with httpx.Client(timeout=60.0) as client:
            r = client.post(url, headers=_search_headers(), json={"value": batch})
            if r.status_code >= 400:
                log.error("AI Search upload failed [%s]: %s", r.status_code, r.text[:2000])
            r.raise_for_status()


def remove_from_index(chunk_ids: list[str]) -> None:
    if not chunk_ids:
        return
    s = get_settings()
    if not s.ai_search_enabled:
        return
    url = (
        f"{s.azure_ai_search_endpoint.rstrip('/')}/indexes/"
        f"{s.azure_ai_search_index}/docs/index?api-version=2024-07-01"
    )
    actions = [{"@search.action": "delete", "chunk_id": _safe_key(cid)} for cid in chunk_ids]
    with httpx.Client(timeout=60.0) as client:
        r = client.post(url, headers=_search_headers(), json={"value": actions})
        r.raise_for_status()


# ---- Foundry agent ----------------------------------------------------------

# Cache the project client across requests. Lazily-imported so the demo still
# starts when azure-ai-projects isn't installed.
_project_client: Any | None = None
_project_client_failed: bool = False


def _get_project_client() -> Any | None:
    global _project_client, _project_client_failed
    if _project_client is not None:
        return _project_client
    if _project_client_failed:
        return None
    s = get_settings()
    if not s.foundry_enabled:
        return None
    try:
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential
    except ImportError as e:
        log.warning(
            "Foundry SDK not installed (%s). Install azure-ai-projects + "
            "azure-identity to enable real agent calls.",
            e,
        )
        _project_client_failed = True
        return None
    try:
        _project_client = AIProjectClient(
            endpoint=s.foundry_project_endpoint,
            credential=DefaultAzureCredential(exclude_interactive_browser_credential=False),
        )
        return _project_client
    except Exception as e:  # pragma: no cover - depends on Azure auth state
        log.warning("Failed to create AIProjectClient: %s", e)
        _project_client_failed = True
        return None


def ask_foundry_agent(question: str) -> dict[str, Any] | None:
    """Single-turn query against a Foundry agent. Returns None when unconfigured.

    Requires:
      * `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_AGENT_ID` set
      * `azure-ai-projects` + `azure-identity` installed
      * Local `az login` (or a managed identity) with **Azure AI Developer** on
        the AIServices account so `DefaultAzureCredential` can acquire a token

    The agent itself should be configured (in the Foundry portal or via the
    `setup_foundry_agent.py` helper) with the AI Search index this demo writes
    to as its knowledge source.
    """
    s = get_settings()
    if not s.foundry_enabled:
        return None
    client = _get_project_client()
    if client is None:
        return {
            "agent_id": s.foundry_agent_id,
            "answer": (
                "Foundry SDK is not available. Install azure-ai-projects "
                "and azure-identity, then run `az login` locally."
            ),
            "configured": False,
            "error": "sdk-unavailable",
        }

    try:
        agents = client.agents
        thread = agents.threads.create()
        agents.messages.create(thread_id=thread.id, role="user", content=question)
        run = agents.runs.create_and_process(thread_id=thread.id, agent_id=s.foundry_agent_id)
        if getattr(run, "status", None) == "failed":
            err = getattr(run, "last_error", None)
            return {
                "agent_id": s.foundry_agent_id,
                "answer": f"Agent run failed: {err}",
                "configured": True,
                "error": "run-failed",
            }
        answer_text = ""
        citations: list[dict[str, Any]] = []
        for msg in agents.messages.list(thread_id=thread.id, order="desc"):
            if getattr(msg, "role", None) != "assistant":
                continue
            for part in getattr(msg, "content", []) or []:
                text = getattr(part, "text", None)
                if text is not None:
                    answer_text = getattr(text, "value", "") or ""
                    for ann in getattr(text, "annotations", []) or []:
                        citations.append(
                            {
                                "type": getattr(ann, "type", "unknown"),
                                "text": getattr(ann, "text", ""),
                            }
                        )
                    break
            if answer_text:
                break
        return {
            "agent_id": s.foundry_agent_id,
            "answer": answer_text or "(agent returned no text)",
            "citations": citations,
            "configured": True,
            "run_id": getattr(run, "id", None),
        }
    except Exception as e:  # pragma: no cover
        log.exception("Foundry agent call failed")
        return {
            "agent_id": s.foundry_agent_id,
            "answer": f"Foundry agent call failed: {e}",
            "configured": True,
            "error": "exception",
        }
