"""
Prompt search HTTP service.

Runs as a persistent local service. All agents on the same machine share
one model load (cross-encoder on GPU, embedding server).

Start:
    uvicorn prompt_flow.server:app --host 127.0.0.1 --port 8000 --reload

Or via the CLI helper:
    python -m prompt_flow.server

Endpoints:
    POST /search          - hybrid semantic search, returns ranked results
    GET  /prompts/{id}    - fetch a single prompt by ID
    GET  /health          - liveness check
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from prompt_flow.config import DB_CONFIG
from prompt_flow.search.api import PromptSearch
from prompt_flow.agent.api import router as agent_router


# --- App lifecycle -------------------------------------------------------

_search: PromptSearch | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load models once on startup, release on shutdown."""
    global _search
    print("Loading PromptSearch (cross-encoder + retriever)...")
    _search = PromptSearch()
    print("Service ready.")
    yield
    _search = None


app = FastAPI(
    title="Prompt Flow",
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
    from prompt_flow.agent.catalog import get_discover_response
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
                   status, models_tested, notes, original_link,
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
        "prompt_flow.server:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info",
    )
