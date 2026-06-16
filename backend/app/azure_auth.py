"""Shared DefaultAzureCredential + bearer-token helper.

Used by `embedder` (Azure OpenAI data plane) and `foundry_client` (AI Search
data plane) when their respective API keys are not set — i.e. when the
target tenant has `disableLocalAuth=true` and we must authenticate with Entra.
"""

from __future__ import annotations

import time
from threading import Lock
from typing import Any

_credential: Any | None = None
_credential_failed: bool = False
_token_cache: dict[str, tuple[str, float]] = {}
_lock = Lock()


def _get_credential() -> Any | None:
    global _credential, _credential_failed
    if _credential is not None or _credential_failed:
        return _credential
    try:
        from azure.identity import DefaultAzureCredential
        _credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)
        return _credential
    except Exception:
        _credential_failed = True
        return None


def get_bearer_token(scope: str) -> str | None:
    """Fetch (and cache) an AAD access token for the given scope."""
    now = time.time()
    with _lock:
        cached = _token_cache.get(scope)
        if cached and cached[1] - 60 > now:
            return cached[0]
    cred = _get_credential()
    if cred is None:
        return None
    try:
        tok = cred.get_token(scope)
    except Exception:
        return None
    with _lock:
        _token_cache[scope] = (tok.token, tok.expires_on)
    return tok.token
