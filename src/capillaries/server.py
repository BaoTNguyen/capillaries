"""
Prompt search HTTP service.

Runs as a persistent local service. All agents on the same machine share
one model load (cross-encoder on GPU, embedding server).

Start:
    uvicorn capillaries.server:app --host 127.0.0.1 --port 8000 --reload

Or via the CLI helper:
    python -m capillaries.server

Endpoints:
    POST /search          - hybrid semantic search, returns ranked results
    GET  /prompts/{id}    - fetch a single prompt by ID
    GET  /health          - liveness check
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from capillaries.config import DB_CONFIG
from capillaries.search.api import PromptSearch
from capillaries.agent.api import router as agent_router


# --- App lifecycle -------------------------------------------------------

_search: PromptSearch | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load models once on startup, release on shutdown."""
    global _search
    # This process *is* the daemon: stop its own reranker from calling the
    # /rerank/scores endpoint that it serves.
    os.environ["CAPILLARIES_NO_REMOTE"] = "1"
    print("Loading PromptSearch (cross-encoder + retriever)...")
    _search = PromptSearch()
    # the model loads lazily now, so pull it in here rather than making the
    # first request pay for it — arriving warm is the point of the daemon
    _search.reranker.warm()
    print("Service ready.")
    yield
    _search = None


app = FastAPI(
    title="Capillaries",
    description="Semantic prompt and skill retrieval for AI agents. Start with POST /agent/route to find the best prompt for your situation.",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(agent_router)


def get_search() -> PromptSearch:
    if _search is None:
        raise RuntimeError("PromptSearch not initialised")
    return _search


# --- Request / response schemas -----------------------------------------

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural language search query")
    filters: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional metadata filters. Supported keys: "
            "domain (list[str]), intent (list[str]), task_type (list[str]), "
            "complexity_min (int), complexity_max (int), "
            "status (str, default 'active')"
        ),
        examples=[{"domain": ["business"]}],
    )
    top_k: int = Field(default=10, ge=1, le=50, description="Number of results to return")

    model_config = {"json_schema_extra": {
        "examples": [{
            "query": "write a go-to-market strategy",
            "filters": {"domain": ["business", "strategy"]},
            "top_k": 5,
        }]
    }}


# --- Endpoints -----------------------------------------------------------

@app.get("/health")
async def health():
    """Liveness check. Returns ready=true when models are loaded."""
    return {"status": "ok", "ready": _search is not None}


@app.get("/agent/discover")
async def discover():
    """Self-describing endpoint for agent discovery."""
    from capillaries.agent.catalog import get_discover_response
    return get_discover_response()


@app.post("/search")
async def search(req: SearchRequest):
    """
    Search for prompts matching a natural language query.

    Returns results ranked by cross-encoder score, with RRF, dense, and
    sparse similarity scores included for transparency.
    """
    payload = await get_search().search_json(
        req.query,
        filters=req.filters,
        top_k=req.top_k,
    )
    return JSONResponse(content=payload)


class RerankRequest(BaseModel):
    pairs: list[list[str]] = Field(
        ..., description="[query, document] pairs to score with the cross-encoder"
    )


@app.post("/rerank/scores")
async def rerank_scores(req: RerankRequest):
    """Raw cross-encoder scores for [query, document] pairs.

    This exists for agent hooks. A hook is one short-lived subprocess per
    prompt submission, so it can never keep a model warm and pays ~4.4s of
    load on every single call — and N parallel hooks pay it N times over,
    each with its own ~2.9GB copy. Borrowing this process's already-loaded
    model turns that into a sub-millisecond loopback round trip.

    Only scoring is remote. Callers keep their own ranking, length penalties
    and filtering, so remote and local results are numerically identical.
    """
    if not req.pairs:
        return {"scores": []}
    rr = get_search().reranker
    scores = rr.model.predict(
        [(p[0], p[1]) for p in req.pairs],
        batch_size=rr.batch_size,
        show_progress_bar=False,
    )
    return {"scores": [float(x) for x in scores.tolist()]}


@app.get("/prompts/{title:path}")
async def get_prompt(title: str):
    """
    Fetch a single prompt by ID.

    Prompt IDs match the filename without extension, e.g.:
        /prompts/Marketing Consultant - Campaign Strategy
    """
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT title, prompt_text, intent, task_type, domain,
                   complexity_level,
                   status, notes, original_link,
                   last_evaluated, last_updated, embedding_version
            FROM prompts
            WHERE title = %s
            """,
            [title],
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Prompt '{title}' not found")

    # Serialize datetime/date fields to ISO strings for JSON
    data = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            data[k] = v.isoformat()
        else:
            data[k] = v

    return JSONResponse(content=data)


# --- CLI entry point -----------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "capillaries.server:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info",
    )
