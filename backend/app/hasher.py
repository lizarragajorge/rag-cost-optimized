"""Stable content hashing utilities.

We use SHA-256 of normalized text so that whitespace-only diffs don't trigger
re-embedding. The hash is the cache key for both documents and chunks.
"""

from __future__ import annotations

import hashlib
import re

_WHITESPACE_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Collapse runs of whitespace and trim, so trivial formatting changes
    don't invalidate the cache."""
    return _WHITESPACE_RE.sub(" ", text).strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()
