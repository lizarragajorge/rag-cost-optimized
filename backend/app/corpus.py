"""Document store.

For demo simplicity, documents live on disk under a "working" copy of the
sample corpus so the user can mutate them through the UI without touching the
seed files.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import get_settings
from .hasher import content_hash

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "sample_corpus"


@dataclass
class Document:
    doc_id: str
    title: str
    text: str

    @property
    def hash(self) -> str:
        return content_hash(self.text)


def _working_dir() -> Path:
    return get_settings().data_dir / "working_corpus"


def ensure_seeded() -> None:
    """First run: copy the seed corpus into the writable working directory."""
    wd = _working_dir()
    if wd.exists() and any(wd.iterdir()):
        return
    wd.mkdir(parents=True, exist_ok=True)
    if SEED_DIR.exists():
        for p in SEED_DIR.glob("*.md"):
            shutil.copy2(p, wd / p.name)


def _path_for(doc_id: str) -> Path:
    safe = doc_id.replace("/", "_").replace("\\", "_")
    return _working_dir() / f"{safe}.md"


def list_documents(limit: int | None = None, skip: int = 0) -> list[Document]:
    ensure_seeded()
    paths = sorted(_working_dir().glob("*.md"))
    if skip:
        paths = paths[skip:]
    if limit is not None:
        paths = paths[:limit]
    docs: list[Document] = []
    for p in paths:
        text = p.read_text(encoding="utf-8")
        title = _extract_title(text) or p.stem
        docs.append(Document(doc_id=p.stem, title=title, text=text))
    return docs


def count_documents() -> int:
    ensure_seeded()
    return sum(1 for _ in _working_dir().glob("*.md"))


def get_document(doc_id: str) -> Document | None:
    p = _path_for(doc_id)
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8")
    return Document(doc_id=doc_id, title=_extract_title(text) or doc_id, text=text)


def save_document(doc_id: str, text: str) -> Document:
    ensure_seeded()
    p = _path_for(doc_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return Document(doc_id=doc_id, title=_extract_title(text) or doc_id, text=text)


def delete_document(doc_id: str) -> bool:
    p = _path_for(doc_id)
    if not p.exists():
        return False
    p.unlink()
    return True


def reset_to_seed() -> None:
    wd = _working_dir()
    if wd.exists():
        shutil.rmtree(wd)
    ensure_seeded()


def _extract_title(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
        if line:
            return line[:80]
    return None
