"""Create (or update) a Foundry agent on the project provisioned by `azd up`.

The agent is wired to the AI Search index this demo writes to, so the smart
re-index pipeline's output is grounded back into agent answers.

Prerequisites:
  * `azd provision` already ran (so backend/.env has FOUNDRY_PROJECT_ENDPOINT
    and AZURE_AI_SEARCH_ENDPOINT).
  * `az login` on this machine — uses DefaultAzureCredential.
  * `pip install -r backend/requirements.txt`.

Usage:
  python backend/scripts/setup_foundry_agent.py
  # writes FOUNDRY_AGENT_ID into backend/.env
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent.parent))

from app.config import get_settings  # noqa: E402


CONNECTION_NAME = "rag-cost-search"
AGENT_NAME = "rag-cost-demo-agent"
AGENT_INSTRUCTIONS = (
    "You are a concise assistant grounded in the Azure AI Search index "
    "named 'rag-cost-demo'. Always cite the doc_id of the source passages "
    "you used. If the index has no relevant passages, say so plainly."
)
ARM_API_VERSION = "2025-04-01-preview"
ARM_SCOPE = "https://management.azure.com/.default"


def _azd_env() -> dict[str, str]:
    """Pull values from `azd env get-values` to fill any gaps in the shell env."""
    try:
        out = subprocess.check_output(
            ["azd", "env", "get-values"],
            cwd=str(HERE.parent.parent.parent),
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return {}
    values: dict[str, str] = {}
    for line in out.splitlines():
        m = re.match(r'^([A-Z0-9_]+)="?(.*?)"?$', line.strip())
        if m:
            values[m.group(1)] = m.group(2)
    return values


def _parse_project_endpoint(endpoint: str) -> tuple[str, str]:
    """Return (account_name, project_name) from a Foundry project endpoint."""
    parsed = urlparse(endpoint)
    account = parsed.hostname.split(".")[0] if parsed.hostname else ""
    m = re.search(r"/projects/([^/]+)", parsed.path)
    project = m.group(1) if m else ""
    if not account or not project:
        raise RuntimeError(
            f"Could not parse account/project from endpoint: {endpoint}"
        )
    return account, project


def _parse_search_endpoint(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    return parsed.hostname.split(".")[0] if parsed.hostname else ""


def _ensure_connection(
    *,
    credential,
    subscription_id: str,
    resource_group: str,
    account: str,
    project: str,
    search_endpoint: str,
    search_resource_id: str,
) -> str:
    """PUT the AI Search connection on the project; return the connection name."""
    import httpx

    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.CognitiveServices/accounts/{account}"
        f"/projects/{project}/connections/{CONNECTION_NAME}"
        f"?api-version={ARM_API_VERSION}"
    )
    body = {
        "properties": {
            "category": "CognitiveSearch",
            "target": search_endpoint,
            "authType": "AAD",
            "isSharedToAll": True,
            "metadata": {
                "ApiType": "Azure",
                "ResourceId": search_resource_id,
            },
        }
    }
    token = credential.get_token(ARM_SCOPE).token
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    resp = httpx.put(url, json=body, headers=headers, timeout=30.0)
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Connection PUT failed ({resp.status_code}): {resp.text[:400]}"
        )
    print(f"  Connection ready: {CONNECTION_NAME}")
    return CONNECTION_NAME


def _search_resource_id(
    *, subscription_id: str, resource_group: str, search_name: str
) -> str:
    return (
        f"/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.Search/searchServices/{search_name}"
    )


def main() -> int:
    s = get_settings()
    if not s.foundry_project_endpoint:
        print(
            "ERROR: FOUNDRY_PROJECT_ENDPOINT is not set in backend/.env. Run `azd provision` first.",
            file=sys.stderr,
        )
        return 1
    if not s.ai_search_enabled:
        print(
            "ERROR: AZURE_AI_SEARCH_ENDPOINT not set in backend/.env.", file=sys.stderr
        )
        return 1

    sub_id = os.environ.get("AZURE_SUBSCRIPTION_ID", "")
    rg = os.environ.get("AZURE_RESOURCE_GROUP", "")
    if not sub_id or not rg:
        azd = _azd_env()
        sub_id = sub_id or azd.get("AZURE_SUBSCRIPTION_ID", "")
        rg = rg or azd.get("AZURE_RESOURCE_GROUP", "")
    if not sub_id or not rg:
        print(
            "ERROR: AZURE_SUBSCRIPTION_ID / AZURE_RESOURCE_GROUP unavailable from env or azd.",
            file=sys.stderr,
        )
        return 1

    try:
        from azure.identity import DefaultAzureCredential
        from azure.ai.agents import AgentsClient
        from azure.ai.agents.models import AzureAISearchTool
    except ImportError as e:
        print(
            f"ERROR: missing SDK: {e}. pip install -r backend/requirements.txt",
            file=sys.stderr,
        )
        return 1

    credential = DefaultAzureCredential()

    account, project = _parse_project_endpoint(s.foundry_project_endpoint)
    search_name = _parse_search_endpoint(s.azure_ai_search_endpoint)
    search_resource_id = _search_resource_id(
        subscription_id=sub_id, resource_group=rg, search_name=search_name
    )

    print(f"Subscription : {sub_id}")
    print(f"ResourceGroup: {rg}")
    print(f"AI account   : {account}")
    print(f"Foundry proj : {project}")
    print(f"Search svc   : {search_name}")

    conn_name = _ensure_connection(
        credential=credential,
        subscription_id=sub_id,
        resource_group=rg,
        account=account,
        project=project,
        search_endpoint=s.azure_ai_search_endpoint,
        search_resource_id=search_resource_id,
    )

    conn_id = (
        f"/subscriptions/{sub_id}/resourceGroups/{rg}"
        f"/providers/Microsoft.CognitiveServices/accounts/{account}"
        f"/projects/{project}/connections/{conn_name}"
    )

    print(f"Connecting to Foundry agents endpoint: {s.foundry_project_endpoint}")
    agents = AgentsClient(endpoint=s.foundry_project_endpoint, credential=credential)

    search_tool = AzureAISearchTool(
        index_connection_id=conn_id, index_name=s.azure_ai_search_index
    )

    agent_id = None
    try:
        for a in agents.list_agents():
            if getattr(a, "name", "") == AGENT_NAME:
                agent_id = a.id
                print(f"  Reusing existing agent: {AGENT_NAME} ({agent_id})")
                break
    except Exception as e:
        print(f"  WARNING: list_agents failed ({e}); will try to create anyway.")

    if agent_id is None:
        print(f"  Creating agent: {AGENT_NAME}")
        agent = agents.create_agent(
            model=s.azure_openai_chat_deployment,
            name=AGENT_NAME,
            instructions=AGENT_INSTRUCTIONS,
            tools=search_tool.definitions,
            tool_resources=search_tool.resources,
        )
        agent_id = agent.id
    else:
        try:
            agents.update_agent(
                agent_id=agent_id,
                model=s.azure_openai_chat_deployment,
                instructions=AGENT_INSTRUCTIONS,
                tools=search_tool.definitions,
                tool_resources=search_tool.resources,
            )
        except Exception as e:
            print(f"  WARNING: update_agent failed ({e}); existing agent left as-is.")

    print(f"\n  Agent ready: {agent_id}")

    env_file = Path(__file__).resolve().parent.parent / ".env"
    lines: list[str] = []
    found = False
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("FOUNDRY_AGENT_ID="):
                lines.append(f"FOUNDRY_AGENT_ID={agent_id}")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"FOUNDRY_AGENT_ID={agent_id}")
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  Wrote FOUNDRY_AGENT_ID={agent_id} to {env_file}")
    print("\nDone. Restart the app and ask a question — it will now route through the agent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
