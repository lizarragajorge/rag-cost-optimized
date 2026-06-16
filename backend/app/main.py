"""FastAPI entrypoint.

Mounts the API routers and serves the small static frontend.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .corpus import ensure_seeded
from .routes import corpus as corpus_routes
from .routes import index as index_routes
from .routes import query as query_routes
from .routes import scale as scale_routes
from .routes import status as status_routes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="RAG Cost-Optimized Demo",
    description=(
        "Demonstrates incremental re-indexing and embedding caching to avoid "
        "expensive full re-embeds when updating a Foundry agent's knowledge base."
    ),
    version="1.0.0",
)

app.include_router(corpus_routes.router)
app.include_router(index_routes.router)
app.include_router(query_routes.router)
app.include_router(scale_routes.router)
app.include_router(status_routes.router)


@app.on_event("startup")
def _startup() -> None:
    settings = get_settings()
    ensure_seeded()
    logging.info("Backend: %s", "azure-openai" if settings.real_embeddings_enabled else "simulated")
    logging.info("AI Search enabled: %s", settings.ai_search_enabled)
    logging.info("Foundry agent enabled: %s", settings.foundry_enabled)


# ---- Static frontend -----------------------------------------------------

def _frontend_dir() -> Path:
    settings = get_settings()
    candidate = Path(str(settings.frontend_dir))
    if candidate.is_absolute() and candidate.exists():
        return candidate
    # Relative paths are resolved against the repo root (one up from `app/`).
    here = Path(__file__).resolve().parent.parent
    return (here / candidate).resolve()


_FRONTEND = _frontend_dir()
if _FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=_FRONTEND), name="static")

    @app.get("/", include_in_schema=False)
    def root() -> FileResponse:
        return FileResponse(_FRONTEND / "index.html")
else:
    logging.warning("Frontend directory not found at %s", _FRONTEND)
