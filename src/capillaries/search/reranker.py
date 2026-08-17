"""
Cross-encoder reranker for prompt search results.

Takes the top-N candidates from the hybrid retriever and rescores each
(query, prompt_text) pair using a cross-encoder model running on GPU.
This significantly improves ranking quality over bi-encoder retrieval alone.

Model: Qwen/Qwen3-Reranker-0.6B (see MODEL_NAME)
  - 0.6B params; raw logits are sigmoid-normalized to 0-1 (NORMALIZE_SCORES)

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

from capillaries.search.retriever import SearchResult

# sentence_transformers (and torch under it) cost seconds to import, before any
# model is even loaded. Both are pulled in lazily by _load_model() so that a
# process which never scores locally — because the daemon does it — pays neither.

# --- Constants -----------------------------------------------------------

MODEL_NAME = os.getenv("RERANKER_MODEL", "Qwen/Qwen3-Reranker-0.6B")

# Qwen3-Reranker emits raw logits, not probabilities. Squash them so the score
# is a 0-1 confidence again — the length penalty below and every threshold
# downstream assume that scale.
#
# This also fixes a problem mxbai had. Measured on identical union candidates,
# top-1 score p10..p90: mxbai [+0.95, +1.00] — saturated, so no threshold could
# separate a good match from a bad one. Qwen3 raw [-3.25, +5.25], which after
# sigmoid spans [0.04, 0.99] and can actually express doubt.
NORMALIZE_SCORES = True

# 2000 chars ~ 500 tokens. Was 512 *characters*, which fed the model a quarter
# of a median chunk — a leftover from a 512-token model this file no longer
# loads. Qwen3-Reranker handles 32k positions, so this is a safety rail, not a
# model limit.
MAX_DOC_CHARS = 2_000
MAX_QUERY_CHARS = 500

# Daemon scoring. CAPILLARIES_URL points at a running `capillaries.server`;
# CAPILLARIES_NO_REMOTE is set by that server on itself so it never calls back
# into its own endpoint.
DAEMON_URL = os.getenv("CAPILLARIES_URL", "http://127.0.0.1:8000")
_daemon_up: bool | None = None  # None = not yet probed, False = probed and absent


def _remote_scores(pairs: list[tuple[str, str]]) -> list[float] | None:
    """Scores from the daemon, or None if there isn't one.

    A refused connection on loopback costs well under a millisecond, and the
    result is cached per process, so the no-daemon path stays free.
    """
    global _daemon_up
    if _daemon_up is False or os.getenv("CAPILLARIES_NO_REMOTE"):
        return None
    try:
        import httpx
        r = httpx.post(f"{DAEMON_URL}/rerank/scores",
                       json={"pairs": [list(p) for p in pairs]},
                       timeout=httpx.Timeout(30.0, connect=0.5))
        r.raise_for_status()
        scores = r.json()["scores"]
        if len(scores) != len(pairs):
            raise ValueError("daemon returned the wrong number of scores")
        _daemon_up = True
        return [float(s) for s in scores]
    except Exception:
        # any failure falls back to loading locally: retrieval must not depend
        # on a daemon being up, it just runs faster when one is
        _daemon_up = False
        try:
            # bring one up for whoever comes next — this call still scores
            # locally rather than waiting on a cold start
            from capillaries.daemon import ensure
            ensure()
        except Exception:
            pass
        return None

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
            # Auto-detect rather than defaulting to CPU. Measured on 50 real
            # pairs: 27 354 ms on CPU vs 249 ms on a 3090 — a 110x difference
            # that was silently costing ~8 s per search on a two-GPU box.
            # Set RERANKER_DEVICE explicitly to override.
            device = os.getenv("RERANKER_DEVICE") or self._autodetect_device()

        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self._model = None  # loaded on first local scoring, never if the daemon serves

    # Rough bf16 footprint of the cross-encoder plus activation headroom.
    MIN_FREE_VRAM = 3 * 1024**3

    @staticmethod
    def _autodetect_device() -> str:
        """Pick the emptiest GPU with real headroom, else CPU.

        `torch.cuda.is_available()` alone is the wrong question on a shared
        box: this machine also hosts an LLM server and the embedding server,
        and asking for the default device OOMs. Picking by free memory keeps
        the fast path when there is room and degrades to CPU instead of
        crashing when there isn't.

        Imports torch lazily so a process that never scores locally — because
        the daemon does it — pays nothing for the check.
        """
        try:
            import torch
            if not torch.cuda.is_available():
                return "cpu"
            free = [(torch.cuda.mem_get_info(i)[0], i)
                    for i in range(torch.cuda.device_count())]
            best, idx = max(free)
            return f"cuda:{idx}" if best >= Reranker.MIN_FREE_VRAM else "cpu"
        except Exception:
            return "cpu"

    @property
    def model(self):
        """The cross-encoder, loaded on first use.

        Construction used to load it eagerly, which cost ~4.4s in every process
        that merely built a PromptSearch — including hook subprocesses that then
        scored nothing locally because a daemon was available.
        """
        if self._model is None:
            from sentence_transformers import CrossEncoder
            print(f"Loading cross-encoder {self.model_name} on {self.device}...")
            self._model = CrossEncoder(self.model_name, device=self.device)
            print("Reranker ready.")
        return self._model

    def warm(self) -> None:
        """Force the load now. The daemon calls this at startup so its first
        request is not the one that pays."""
        _ = self.model

    def _predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        """Cross-encoder scores for (query, doc) pairs.

        Prefers a running capillaries daemon: model load is ~4.4s and happens in
        *every* process otherwise, because agent hooks are one subprocess per
        prompt and can never stay warm. Scoring is the only part that needs the
        model — the length penalty and result assembly below stay local, so the
        remote and local paths are numerically identical.
        """
        scores = _remote_scores(pairs)
        if scores is None:
            scores = self.model.predict(
                pairs, batch_size=self.batch_size, show_progress_bar=False,
            ).tolist()
        if NORMALIZE_SCORES:
            scores = [1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, s))))
                      for s in scores]
        return scores

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
        raw_scores = self._predict(pairs)

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
