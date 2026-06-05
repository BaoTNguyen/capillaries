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

MODEL_NAME = "Snowflake/snowflake-arctic-embed-m-v2.0"

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
    return {"status": "ok", "model": MODEL_NAME, "ready": model is not None}


def _patch_snowflake_source() -> None:
    """Patch Snowflake's cached HF modeling code to fix position_ids bug.

    The model registers position_ids as a non-persistent buffer without a
    device, which produces garbage index values on CUDA with torch >=2.12.
    We patch the source to recreate position_ids on the correct device
    inside the embeddings forward method.
    """
    import glob
    pattern = os.path.expanduser(
        "~/.cache/huggingface/modules/transformers_modules/Snowflake/"
        "snowflake_hyphen_arctic_hyphen_embed_hyphen_m_hyphen_v2*/modeling_hf_alibaba_nlp_gte.py"
    )
    for path in glob.glob(pattern):
        with open(path, "r") as f:
            src = f.read()

        marker = "# _patched_position_ids"
        if marker in src:
            print(f"Snowflake source already patched: {path}")
            continue

        target = "        if position_ids is None:"
        patch = (
            f"        {marker}\n"
            "        self.position_ids = torch.arange(\n"
            "            self.position_ids.size(0), device=embeddings.device\n"
            "        )\n"
        )
        if target in src:
            src = src.replace(target, patch + target, 1)
            with open(path, "w") as f:
                f.write(src)
            # Clear bytecode cache so the patched source is used
            import shutil
            cache_dir = os.path.join(os.path.dirname(path), "__pycache__")
            if os.path.isdir(cache_dir):
                shutil.rmtree(cache_dir)
            print(f"Patched Snowflake source: {path}")
        else:
            print(f"Warning: could not find patch target in {path}")


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

    _patch_snowflake_source()
    print(f"Loading {MODEL_NAME} on {device}...")
    model = SentenceTransformer(MODEL_NAME, device=device, trust_remote_code=True)
    print(f"Model ready. Embedding dim: {model.get_sentence_embedding_dimension()}")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
