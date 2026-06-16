"""Paragraph-aware chunking.

We try to keep each chunk close to a target token budget without splitting in
the middle of a paragraph — that way small edits to one paragraph only
invalidate the chunk that contains it, not its neighbours.
"""

from __future__ import annotations

from dataclasses import dataclass

import tiktoken

from .config import get_settings
from .hasher import content_hash

# cl100k_base is the tokenizer family used by text-embedding-3-*.
_ENC = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_ENC.encode(text))


@dataclass
class Chunk:
    chunk_id: str          # deterministic: f"{doc_id}:{ordinal}"
    doc_id: str
    ordinal: int
    text: str
    token_count: int
    hash: str


def _paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in text.replace("\r\n", "\n").split("\n\n")]
    return [p for p in parts if p]


def chunk_document(doc_id: str, text: str) -> list[Chunk]:
    """Group paragraphs into chunks that fit the target token budget."""
    settings = get_settings()
    target = settings.chunk_target_tokens

    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_tokens = 0
    ordinal = 0

    def flush() -> None:
        nonlocal buffer, buffer_tokens, ordinal
        if not buffer:
            return
        text_block = "\n\n".join(buffer)
        # Use the joined-text token count so it matches what's actually sent
        # to the embedding API (and what `naive_equivalent` accounts for).
        chunks.append(
            Chunk(
                chunk_id=f"{doc_id}:{ordinal}",
                doc_id=doc_id,
                ordinal=ordinal,
                text=text_block,
                token_count=count_tokens(text_block),
                hash=content_hash(text_block),
            )
        )
        ordinal += 1
        buffer = []
        buffer_tokens = 0

    for paragraph in _paragraphs(text):
        ptokens = count_tokens(paragraph)
        # A single paragraph larger than the target becomes its own chunk.
        if ptokens >= target:
            flush()
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}:{ordinal}",
                    doc_id=doc_id,
                    ordinal=ordinal,
                    text=paragraph,
                    token_count=ptokens,
                    hash=content_hash(paragraph),
                )
            )
            ordinal += 1
            continue

        if buffer_tokens + ptokens > target:
            flush()
        buffer.append(paragraph)
        buffer_tokens += ptokens

    flush()
    return chunks
