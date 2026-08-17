#!/usr/bin/env python3
"""
Lightweight embedding server — OpenAI-compatible /v1/embeddings endpoint.

Serves snowflake-arctic-embed-m-v2.0 (768-dim) via sentence-transformers.
Drop-in replacement for Ollama's embedding endpoint.

Usage:
    python scripts/serve_embeddings.py                    # default port 8003
    python scripts/serve_embeddings.py --port 8003 --device cuda

Requires:
    pip install sentence-transformers fastapi uvicorn xformers einops
"""

from __future__ import annotations

import argparse
import os

import torch
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

MODEL_NAME = os.getenv("EMBED_MODEL", "Qwen/Qwen3-Embedding-0.6B")

# Longest input accepted, in tokens. Chunks run ~430 tokens at the current
# TARGET; 1024 covers the tail without paying for an 8k-token window nothing
# uses.
MAX_SEQ_LENGTH = 1024

app = FastAPI(title="Embedding Server", version="1.0.0")

model: SentenceTransformer | None = None


class EmbedRequest(BaseModel):
    input: str | list[str] = Field(..., description="Text or list of texts to embed")
    model: str = Field(default=MODEL_NAME, description="Ignored — always uses the loaded model")


class EmbedResponse(BaseModel):
    object: str = "list"
    data: list[dict]
    model: str
    usage: dict


@app.post("/v1/embeddings")
async def embed(req: EmbedRequest) -> EmbedResponse:
    texts = [req.input] if isinstance(req.input, str) else req.input
    embeddings = model.encode(texts, normalize_embeddings=True)

    data = [
        {"object": "embedding", "index": i, "embedding": vec.tolist()}
        for i, vec in enumerate(embeddings)
    ]

    total_chars = sum(len(t) for t in texts)
    return EmbedResponse(
        data=data,
        model=MODEL_NAME,
        usage={"prompt_tokens": total_chars // 4, "total_tokens": total_chars // 4},
    )


@app.get("/health")
async def health():
    """Report what is actually loaded, not what config claims.

    `dim` matters to callers: the schema pins a vector width, and a model
    serving a different one silently poisons the index.
    """
    return {
        "status": "ok" if model is not None else "not_ready",
        "model": MODEL_NAME,
        "ready": model is not None,
        "dim": model.get_sentence_embedding_dimension() if model is not None else None,
    }


class SelfCheckFailed(RuntimeError):
    """The loaded model does not produce usable embeddings."""


# Two obviously-related sentences and one unrelated one. A working embedder
# ranks the related pair well above either unrelated pair; a broken one does
# not, and until now nothing noticed.
_PROBE_A = "Build a 13-week cash flow model for an early stage startup."
_PROBE_B = "Weekly burn rate forecasting spreadsheet for a young company."
_PROBE_C = "Watercolor painting techniques for absolute beginners."

MIN_MARGIN = 0.10


def self_check(m: SentenceTransformer) -> dict:
    """Refuse to serve embeddings that are silently wrong.

    This exists because they were. The previous model
    (snowflake-arctic-embed-m-v2.0) ships custom remote code that breaks under
    transformers>=5: it returned finite, perfectly reproducible vectors whose
    geometry was meaningless. Nothing raised, nothing looked wrong, and every
    embedding in the database was garbage — measured at 1/40 on verbatim
    self-retrieval, where a working index scores ~34/40.

    Deterministic garbage is the worst failure mode available, so the server
    now proves the space is sane before it will answer a single request.
    """
    import numpy as np

    vecs = m.encode([_PROBE_A, _PROBE_B, _PROBE_C], normalize_embeddings=True)
    if not np.isfinite(vecs).all():
        raise SelfCheckFailed("embeddings contain NaN or inf")

    related = float(vecs[0] @ vecs[1])
    unrelated = max(float(vecs[0] @ vecs[2]), float(vecs[1] @ vecs[2]))
    margin = related - unrelated
    if margin < MIN_MARGIN:
        raise SelfCheckFailed(
            f"related pair ({related:.3f}) does not clear unrelated pair "
            f"({unrelated:.3f}) by {MIN_MARGIN}: margin {margin:.3f}. "
            f"The embedding space is collapsed — refusing to serve."
        )
    return {"related": round(related, 4), "unrelated": round(unrelated, 4),
            "margin": round(margin, 4)}


def main():
    global model
    parser = argparse.ArgumentParser(description="Serve embeddings via OpenAI-compatible API")
    parser.add_argument("--port", type=int, default=8003)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--device", type=str, default=None, help="'cuda', 'cpu', or auto-detect")
    args = parser.parse_args()

    device = args.device
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    print(f"Loading {MODEL_NAME} on {device}...")
    # bf16 on GPU: fp32 cost 7.8 GB for a 0.6B model and starved the reranker
    # daemon on a box that also hosts an LLM server. bf16 holds ~2.5 GB with no
    # measurable retrieval difference — but the corpus must be re-embedded
    # after changing this, so queries and documents share a dtype.
    kwargs = {"model_kwargs": {"dtype": torch.bfloat16}} if device.startswith("cuda") else {}
    loaded = SentenceTransformer(MODEL_NAME, device=device, **kwargs)
    loaded.max_seq_length = MAX_SEQ_LENGTH

    # Prove the space is sane before publishing the model to request handlers.
    # `model` stays None on failure, so /health reports not-ready rather than
    # the server answering with garbage.
    result = self_check(loaded)
    model = loaded

    print(f"Self-check passed: related {result['related']}, "
          f"unrelated {result['unrelated']}, margin {result['margin']}")
    print(f"Model ready. Embedding dim: {model.get_sentence_embedding_dimension()}")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
