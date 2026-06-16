"""Environment-driven settings.

Anything Azure-related is optional — when missing we fall back to the offline
simulated embedding model so the demo can run anywhere.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve paths relative to the backend root (parent of the `app/` package)
# so the app behaves identically regardless of the caller's cwd.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _default_data_dir() -> Path:
    return _BACKEND_ROOT / "data"


def _default_frontend_dir() -> Path:
    return (_BACKEND_ROOT.parent / "frontend").resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Storage
    data_dir: Path = Field(default_factory=_default_data_dir)
    frontend_dir: Path = Field(default_factory=_default_frontend_dir)

    # Pricing model
    price_per_mtoken_embedding: float = 0.02
    embedding_model_name: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Azure OpenAI (real embeddings)
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_embedding_deployment: str = "text-embedding-3-small"
    azure_openai_chat_deployment: str = "gpt-4o-mini"

    # Azure AI Search (knowledge source for Foundry agents)
    azure_ai_search_endpoint: str = ""
    azure_ai_search_api_key: str = ""
    azure_ai_search_index: str = "rag-cost-demo"

    # Foundry agent. The project endpoint comes from `azd provision`;
    # the agent ID is created in the portal (or via setup_foundry_agent.py)
    # and pasted in by the user.
    foundry_project_endpoint: str = ""
    foundry_agent_id: str = ""

    # Chunking
    chunk_target_tokens: int = 300
    chunk_overlap_tokens: int = 40

    # Scale safety: at this many chunks the in-memory vector index stops
    # accepting upserts. The cache + cost accounting still run normally, so
    # benchmark numbers stay correct — only similarity search is capped.
    max_index_chunks: int = 25_000

    # Document listing pagination (UI safety for large corpora).
    max_docs_in_listing: int = 200

    @property
    def real_embeddings_enabled(self) -> bool:
        # Endpoint alone is enough — when the API key is empty we fall back to
        # DefaultAzureCredential (required when the tenant disables local auth).
        return bool(self.azure_openai_endpoint)

    @property
    def ai_search_enabled(self) -> bool:
        return bool(self.azure_ai_search_endpoint)

    @property
    def azure_openai_use_aad(self) -> bool:
        return bool(self.azure_openai_endpoint) and not self.azure_openai_api_key

    @property
    def ai_search_use_aad(self) -> bool:
        return bool(self.azure_ai_search_endpoint) and not self.azure_ai_search_api_key

    @property
    def foundry_enabled(self) -> bool:
        return bool(self.foundry_project_endpoint and self.foundry_agent_id)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
