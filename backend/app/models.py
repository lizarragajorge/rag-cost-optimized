"""Pydantic schemas for the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentIn(BaseModel):
    doc_id: str = Field(..., min_length=1, pattern=r"^[a-zA-Z0-9_\-]+$")
    text: str


class DocumentOut(BaseModel):
    doc_id: str
    title: str
    text: str
    hash: str
    token_count: int
    chunk_count: int


class QueryIn(BaseModel):
    q: str = Field(..., min_length=1)
    k: int = Field(default=5, ge=1, le=20)


class QueryHit(BaseModel):
    chunk_id: str
    doc_id: str
    title: str
    text: str
    score: float


class QueryOut(BaseModel):
    answer: str
    hits: list[QueryHit]
    foundry_used: bool


class StatusOut(BaseModel):
    backend: str
    real_embeddings: bool
    ai_search: bool
    foundry: bool
    foundry_agent_configured: bool
    embedding_model: str
    chat_model: str
    price_per_mtoken_usd: float
    azure_openai_endpoint: str
    azure_ai_search_endpoint: str
    azure_ai_search_index: str
    foundry_project_endpoint: str
    index_stats: dict
    cache_stats: dict
    session_totals: dict
