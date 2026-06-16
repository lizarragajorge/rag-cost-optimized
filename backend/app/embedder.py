"""Embedding generation.

Two backends, chosen automatically from the environment:

* **simulated** (default) — deterministic pseudo-embeddings from the content
  hash. Free, offline, and good enough to show the cost-optimization story
  without an Azure dependency.
* **azure-openai** — real embeddings when AZURE_OPENAI_* env vars are set.

Both report the same metadata so the cost model and cache work identically.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import httpx
import numpy as np

from .chunker import Chunk, count_tokens
from .config import get_settings


@dataclass
class EmbeddingResult:
    embeddings: list[np.ndarray]
    tokens: int
    model: str
    backend: str  # "simulated" | "azure-openai"


def _simulated(texts: list[str], dims: int, model: str) -> EmbeddingResult:
    """Deterministic embeddings from sha256(text) — never call the real API."""
    vectors: list[np.ndarray] = []
    total_tokens = 0
    for text in texts:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # Seed numpy from the first 4 bytes for reproducibility.
        seed = int.from_bytes(h[:4], "big")
        rng = np.random.default_rng(seed)
        vec = rng.standard_normal(dims).astype(np.float32)
        # L2-normalize so cosine similarity = dot product.
        vec /= np.linalg.norm(vec) + 1e-9
        vectors.append(vec)
        total_tokens += count_tokens(text)
    return EmbeddingResult(
        embeddings=vectors, tokens=total_tokens, model=model, backend="simulated"
    )


def _azure_openai(texts: list[str]) -> EmbeddingResult:
    settings = get_settings()
    url = (
        f"{settings.azure_openai_endpoint.rstrip('/')}/openai/deployments/"
        f"{settings.azure_openai_embedding_deployment}/embeddings"
        f"?api-version={settings.azure_openai_api_version}"
    )
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if settings.azure_openai_use_aad:
        from .azure_auth import get_bearer_token
        token = get_bearer_token("https://cognitiveservices.azure.com/.default")
        if not token:
            raise RuntimeError(
                "Azure OpenAI API key is not set and DefaultAzureCredential could "
                "not acquire a token. Run `az login` or set AZURE_OPENAI_API_KEY."
            )
        headers["Authorization"] = f"Bearer {token}"
    else:
        headers["api-key"] = settings.azure_openai_api_key
    payload = {"input": texts}
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    vectors = [
        np.array(item["embedding"], dtype=np.float32) for item in data["data"]
    ]
    tokens = data.get("usage", {}).get("prompt_tokens") or sum(count_tokens(t) for t in texts)
    return EmbeddingResult(
        embeddings=vectors,
        tokens=tokens,
        model=settings.azure_openai_embedding_deployment,
        backend="azure-openai",
    )


def embed_texts(texts: list[str]) -> EmbeddingResult:
    """Embed a batch of texts using whichever backend is configured."""
    settings = get_settings()
    if not texts:
        return EmbeddingResult(
            embeddings=[],
            tokens=0,
            model=settings.embedding_model_name,
            backend="simulated" if not settings.real_embeddings_enabled else "azure-openai",
        )
    if settings.real_embeddings_enabled:
        return _azure_openai(texts)
    return _simulated(texts, settings.embedding_dimensions, settings.embedding_model_name)


def embed_chunks(chunks: list[Chunk]) -> EmbeddingResult:
    return embed_texts([c.text for c in chunks])
