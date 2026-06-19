"""
Cross-encoder reranker for prompt search results.

Takes the top-N candidates from the hybrid retriever and rescores each
(query, prompt_text) pair using a cross-encoder model running on GPU.
This significantly improves ranking quality over bi-encoder retrieval alone.

Model: cross-encoder/ms-marco-MiniLM-L-6-v2
  - 22M parameters, fast on GPU (~50ms for 50 pairs on a 3090)
  - Trained on MS MARCO passage ranking
  - Outputs a relevance logit — higher = more relevant

Usage:
    from capillaries.search.reranker import Reranker
    from capillaries.search.retriever import Retriever

    retriever = Retriever()
    reranker = Reranker()  # loads model once, reuse across calls

    candidates = await retriever.search(query, top_k=50)
    results = reranker.rerank(query, candidates, top_k=10)
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Any

import torch
from sentence_transformers import CrossEncoder

from capillaries.search.retriever import SearchResult

# --- Constants -----------------------------------------------------------

MODEL_NAME = "mixedbread-ai/mxbai-rerank-base-v2"

MAX_DOC_CHARS = 512
MAX_QUERY_CHARS = 500

LENGTH_THRESHOLD = 2_200
LENGTH_PENALTY_STRENGTH = 0.02
LENGTH_PENALTY_CURVE = 0.5


# --- Reranked result contract --------------------------------------------

@dataclass
class RankedResult:
    prompt_id: str                # UUID
    title: str                    # human-readable name
    prompt_text: str
    rerank_score: float           # cross-encoder logit (higher = more relevant)
    rrf_score: float              # original RRF score from retriever
    dense_rank: int | None
    sparse_rank: int | None
    dense_sim: float | None
    sparse_sim: float | None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "prompt_id": self.prompt_id,
            "title": self.title,
            "prompt_text": self.prompt_text,
            "scores": {
                "rerank": round(self.rerank_score, 4),
                "rrf": round(self.rrf_score, 4),
                "dense_sim": round(self.dense_sim, 4) if self.dense_sim is not None else None,
                "sparse_sim": round(self.sparse_sim, 4) if self.sparse_sim is not None else None,
            },
            "retrieval": {
                "dense_rank": self.dense_rank,
                "sparse_rank": self.sparse_rank,
            },
            "metadata": self.metadata,
        }


# --- Reranker ------------------------------------------------------------

class Reranker:
    """
    Cross-encoder reranker.

    Loads the model once on construction and keeps it in memory.
    Designed to be instantiated once and reused across many search calls.

    Args:
        model_name: HuggingFace model ID. Defaults to ms-marco-MiniLM-L-6-v2.
        device:     'cuda', 'cpu', or None (auto-detect GPU if available).
        batch_size: Pairs per forward pass. 16 is safe for 1.5B on a 3090.
    """

    def __init__(
        self,
        model_name: str = MODEL_NAME,
        device: str | None = None,
        batch_size: int = 16,
    ) -> None:
        if device is None:
            device = os.getenv("RERANKER_DEVICE", "cpu")

        print(f"Loading cross-encoder {model_name} on {device}...")
        self.model = CrossEncoder(model_name, device=device)
        self.device = device
        self.batch_size = batch_size
        print("Reranker ready.")

    def rerank(
        self,
        query: str,
        candidates: list[SearchResult],
        top_k: int = 10,
    ) -> list[RankedResult]:
        """
        Rerank candidates using the cross-encoder.

        Args:
            query:      The original search query.
            candidates: Results from Retriever.search() (usually top-50).
            top_k:      How many results to return after reranking.

        Returns:
            List of RankedResult sorted by rerank_score descending.
        """
        if not candidates:
            return []

        q = query[:MAX_QUERY_CHARS]
        pairs = [(q, c.prompt_text[:MAX_DOC_CHARS]) for c in candidates]

        raw_scores: list[float] = self.model.predict(
            pairs,
            batch_size=self.batch_size,
            show_progress_bar=False,
        ).tolist()

        ranked = []
        for c, raw in zip(candidates, raw_scores):
            excess = max(0.0, (len(c.prompt_text) - LENGTH_THRESHOLD) / LENGTH_THRESHOLD)
            penalty = LENGTH_PENALTY_STRENGTH * (excess ** LENGTH_PENALTY_CURVE)
            adjusted = raw - penalty

            ranked.append(
                RankedResult(
                    prompt_id=c.prompt_id,
                    title=c.title,
                    prompt_text=c.prompt_text,
                    rerank_score=adjusted,
                    rrf_score=c.rrf_score,
                    dense_rank=c.dense_rank,
                    sparse_rank=c.sparse_rank,
                    dense_sim=c.dense_sim,
                    sparse_sim=c.sparse_sim,
                    metadata=c.metadata,
                )
            )

        ranked.sort(key=lambda r: (r.rerank_score, r.rrf_score), reverse=True)
        return ranked[:top_k]
