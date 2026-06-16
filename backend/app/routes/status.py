from __future__ import annotations

from fastapi import APIRouter

from ..cache import get_cache
from ..config import get_settings
from ..indexer import get_index, session_totals
from ..models import StatusOut

router = APIRouter(prefix="/api/status", tags=["status"])


def _redact_host(url: str) -> str:
    """Show only the host portion so the UI can render it without leaking paths."""
    if not url:
        return ""
    try:
        from urllib.parse import urlparse
        u = urlparse(url)
        return f"{u.scheme}://{u.netloc}" if u.scheme and u.netloc else url
    except Exception:
        return url


@router.get("", response_model=StatusOut)
def status() -> StatusOut:
    s = get_settings()
    return StatusOut(
        backend="azure-openai" if s.real_embeddings_enabled else "simulated",
        real_embeddings=s.real_embeddings_enabled,
        ai_search=s.ai_search_enabled,
        foundry=s.foundry_enabled,
        foundry_agent_configured=bool(s.foundry_agent_id),
        embedding_model=s.embedding_model_name,
        chat_model=s.azure_openai_chat_deployment,
        price_per_mtoken_usd=s.price_per_mtoken_embedding,
        azure_openai_endpoint=_redact_host(s.azure_openai_endpoint),
        azure_ai_search_endpoint=_redact_host(s.azure_ai_search_endpoint),
        azure_ai_search_index=s.azure_ai_search_index if s.ai_search_enabled else "",
        foundry_project_endpoint=_redact_host(s.foundry_project_endpoint),
        index_stats=get_index().stats(),
        cache_stats=get_cache().stats(),
        session_totals=session_totals(),
    )
