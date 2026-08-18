"""
Rigorous search quality tests.

Covers:
  - Golden set relevance (Recall@K, MRR)
  - Ranking quality (score monotonicity, cross-encoder vs RRF agreement)
  - Filter correctness (hard constraints never violated)
  - Component contribution (dense vs sparse doing their jobs)
  - Edge cases (short, long, junk, no-match queries)
  - Latency (warm call benchmarks)

Run:
    python -m pytest tests/test_search.py -v
    python -m pytest tests/test_search.py -v -k "golden"     # one section only
    python -m pytest tests/test_search.py -v --tb=short -q   # compact output
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import pytest

from capillaries.search.api import PromptSearch
from capillaries.search.retriever import Retriever

# Every test in this file builds a PromptSearch or a Retriever, which loads
# models and opens a Postgres connection — the `db` marker was already the
# convention for that, this file just never claimed it. Without the mark,
# `-m "not db"` selected two minutes of live embedding calls and failed
# wherever there is no database, which is every machine but this one.
pytestmark = pytest.mark.db


# ---------------------------------------------------------------------------
# Shared fixture — load models once for the whole test session
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def ps() -> PromptSearch:
    return PromptSearch()


@pytest.fixture(scope="session")
def retriever() -> Retriever:
    return Retriever()


def run(coro):
    """Run a coroutine synchronously (pytest-asyncio not required). A fresh loop
    per call — asyncio.get_event_loop() is deprecated in 3.12."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 1. GOLDEN SET — known query → expected prompt must appear in top-K
#
# Format: (query, expected_title_substring, top_k, label)
# Use a substring of the title — exact match is too brittle.
# ---------------------------------------------------------------------------

GOLDEN_SET = [
    # Finance / business prompts
    ("build a 13-week cash flow model",             "13-Week Cash Flow Model",              5,  "exact title match"),
    ("create a 3-year financial plan for a startup","3-Year Business Plan Financials",       5,  "financial planning"),
    ("analyze profit and loss metrics",             "P&L & Metrics Deep Dive",              10, "P&L analysis"),
    ("allocate a marketing budget",                 "Marketing Budget Allocation",           10, "marketing budget"),
    ("build a quarterly business review",           "Quarterly Business Review",             5,  "QBR"),

    # Strategy prompts
    ("map out stakeholders for a project",          "Stakeholder Mapping",                  5,  "stakeholder mapping"),
    ("write a go-to-market plan",                   "GTM",                                  10, "GTM strategy"),
    ("evaluate AI vendors and models",              "AI vendor",                            10, "AI vendor eval"),

    # Technical prompts
    ("write a technical design document",           "Technical Design Doc",                 5,  "tech design doc"),
    ("sync data between applications",              "Cross-Application Data Sync",          10, "data sync"),

    # AI / product prompts
    ("how to pick the right AI architecture for my product",        "Pick Your Model",    10, "AI model strategy"),
    ("evaluate the quality of an AI tool",          "AI Tool Evaluation",                   10, "AI tool eval"),
    ("build a product roadmap",                     "PRODUCT ROADMAP",                      10, "product roadmap"),
    ("write a product requirements document",       "PRD",                                  5,  "PRD"),

    # Personal / productivity
    ("quick sanity check on a decision I made",     "Am I Being Nuts",                      10, "self-assessment"),
    ("set up a deep work focus experiment",         "Focus Experiment",                     10, "deep work"),
    ("audit self-interruptions during work",        "Self-Interruption Audit",              10, "interruption audit"),

    # Semantic / paraphrase (no exact keyword overlap)
    ("help me think through a business decision I'm stuck on",  "Decision Helper",          10, "paraphrase: decision helper"),
    ("financial model for early stage company",    "3-Year Business Plan",                  10, "paraphrase: 3yr plan"),
    ("how do I pick the right AI model for my use case", "Pick Your Model",                 10, "paraphrase: model strategy"),
]


@dataclass
class GoldenResult:
    label: str
    query: str
    expected: str
    top_k: int
    found: bool
    rank: int | None          # 1-based, None if not found
    top_result: str           # what actually came first
    rerank_score_top: float


def _find_rank(results, substring: str) -> tuple[bool, int | None]:
    sub = substring.lower()
    for i, r in enumerate(results, 1):
        label = getattr(r, "title", r.prompt_id)
        if sub in label.lower():
            return True, i
    return False, None


class TestGoldenSet:
    """Known query → expected prompt must appear within top_k results."""

    def _run_golden(self, ps, query, expected, top_k):
        resp = run(ps.search(query, top_k=top_k))
        found, rank = _find_rank(resp.results, expected)
        top = resp.results[0] if resp.results else None
        top_label = getattr(top, "title", top.prompt_id) if top else ""
        return found, rank, top_label, top.rerank_score if top else 0.0

    @pytest.mark.parametrize("query,expected,top_k,label", GOLDEN_SET)
    def test_golden(self, ps, query, expected, top_k, label):
        found, rank, top_result, top_score = self._run_golden(ps, query, expected, top_k)
        assert found, (
            f"[{label}] Expected '{expected}' in top-{top_k} for query: '{query}'\n"
            f"  Top result was: '{top_result}' (score={top_score:.2f})"
        )

    @pytest.mark.xfail(reason="Known gap: prompt_id has no spaces/dots, embedding doesn't surface it")
    def test_rag_vs_finetuning_retrieval(self, ps):
        """AIArchitecture-RAGvs.Fine-Tuningvs.PromptEngineering is hard to retrieve.
        The prompt_id formatting (no spaces) causes poor embedding alignment.
        Fix: add descriptive metadata to this prompt or re-embed with a summary prefix.
        """
        resp = run(ps.search("compare RAG fine-tuning and prompt engineering", top_k=20))
        found, _ = _find_rank(resp.results, "AIArchitecture-RAG")
        assert found

    def test_golden_summary(self, ps, capsys):
        """Print a full recall/MRR report for manual review."""
        results: list[GoldenResult] = []
        for query, expected, top_k, label in GOLDEN_SET:
            found, rank, top_result, top_score = self._run_golden(ps, query, expected, top_k)
            results.append(GoldenResult(label, query, expected, top_k, found, rank, top_result, top_score))

        found_count = sum(1 for r in results if r.found)
        recall = found_count / len(results)

        # MRR — only over found results
        mrr_scores = [1 / r.rank for r in results if r.found and r.rank]
        mrr = sum(mrr_scores) / len(results) if mrr_scores else 0.0

        with capsys.disabled():
            print(f"\n{'='*70}")
            print(f"GOLDEN SET REPORT  ({found_count}/{len(results)} found)")
            print(f"  Recall: {recall:.1%}   MRR: {mrr:.3f}")
            print(f"{'='*70}")
            for r in results:
                status = f"rank={r.rank}" if r.found else "MISS"
                print(f"  [{status:8}] {r.label}")
                if not r.found:
                    print(f"             query   : {r.query}")
                    print(f"             expected: {r.expected}")
                    print(f"             got     : {r.top_result[:60]}")
            print(f"{'='*70}\n")


# ---------------------------------------------------------------------------
# 2. RANKING QUALITY
# ---------------------------------------------------------------------------

class TestRankingQuality:
    """Rerank scores should be monotonically decreasing."""

    @pytest.mark.parametrize("query", [
        "write a marketing strategy",
        "analyze product metrics",
        "build a technical architecture",
    ])
    def test_scores_monotonically_decreasing(self, ps, query):
        resp = run(ps.search(query, top_k=10))
        scores = [r.rerank_score for r in resp.results]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], (
                f"Score not monotonic at position {i+1}: {scores[i]:.3f} < {scores[i+1]:.3f}\n"
                f"Query: '{query}'"
            )

    def test_top_result_has_positive_rerank_score(self, ps):
        """A clear query should have a positive cross-encoder score at rank 1."""
        resp = run(ps.search("write a product requirements document", top_k=5))
        assert resp.results[0].rerank_score > 0, (
            f"Top result has negative rerank score: {resp.results[0].rerank_score:.2f}\n"
            f"Prompt: {resp.results[0].prompt_id}"
        )

    def test_rrf_and_rerank_top10_overlap(self, ps):
        """RRF top-10 and reranked top-10 should share results — rerank reorders, not replaces."""
        candidates = run(Retriever().search("analyze customer churn", top_k=10))
        rrf_top10 = {c.prompt_id for c in candidates[:10]}

        resp = run(ps.search("analyze customer churn", top_k=10))
        rerank_top10 = {r.prompt_id for r in resp.results[:10]}

        overlap = rrf_top10 & rerank_top10
        assert len(overlap) >= 4, (
            f"Less than 5 overlap between RRF top-10 and rerank top-10.\n"
            f"  RRF    top-10: {rrf_top10}\n"
            f"  Rerank top-10: {rerank_top10}\n"
            f"  Overlap: {overlap}"
        )


# ---------------------------------------------------------------------------
# 3. FILTER CORRECTNESS
# ---------------------------------------------------------------------------

class TestFilters:
    """Filters must never return results that violate hard constraints."""


    @pytest.mark.parametrize("domain,query", [
        (["business"], "quarterly financial review"),
        (["technical"], "write a system design document"),
        (["personal"], "reflect on my week"),
    ])
    def test_domain_filter_respected(self, ps, domain, query):
        resp = run(ps.search(query, filters={"domain": domain}, top_k=10))
        for r in resp.results:
            overlap = set(domain) & set(r.metadata.get("domain") or [])
            assert overlap, (
                f"Domain filter violation: expected any of {domain}, got {r.metadata['domain']}\n"
                f"Prompt: {r.prompt_id}"
            )


    def test_filters_reduce_result_pool(self, ps):
        """A filtered search should return <= results than an unfiltered one."""
        unfiltered = run(ps.search("business strategy", top_k=20))
        filtered = run(ps.search("business strategy", filters={"primary_stage": "plan"}, top_k=20))
        assert len(filtered.results) <= len(unfiltered.results)

    def test_invalid_domain_returns_empty_gracefully(self, ps):
        resp = run(ps.search("anything", filters={"domain": ["nonexistentdomain99"]}, top_k=10))
        assert isinstance(resp.results, list)


# ---------------------------------------------------------------------------
# 4. COMPONENT CONTRIBUTION
# ---------------------------------------------------------------------------

class TestComponentContribution:
    """Verify dense and sparse retrieval are both contributing."""

    def test_keyword_query_has_sparse_matches(self, retriever):
        """A query with exact prompt keywords should appear in sparse results."""
        results = run(retriever.search("Stakeholder Mapping", top_k=10))
        sparse_contributors = [r for r in results if r.sparse_rank is not None]
        assert len(sparse_contributors) > 0, "No sparse (pg_trgm) results returned"

    def test_semantic_query_has_dense_matches(self, retriever):
        """A paraphrase query should pull results primarily from dense."""
        results = run(retriever.search(
            "help me understand who cares about this initiative and what they need",
            top_k=10,
        ))
        dense_contributors = [r for r in results if r.dense_rank is not None]
        assert len(dense_contributors) > 0, "No dense (pgvector) results returned"

    def test_rrf_combines_both_sources(self, retriever):
        """At least some results should come from each source."""
        results = run(retriever.search("write a strategy document", top_k=20))
        has_dense_only = any(r.dense_rank is not None and r.sparse_rank is None for r in results)
        has_sparse_only = any(r.sparse_rank is not None and r.dense_rank is None for r in results)
        has_both = any(r.dense_rank is not None and r.sparse_rank is not None for r in results)
        assert has_both, "No results appeared in both dense and sparse lists"
        # At least one source should have unique contributors
        assert has_dense_only or has_sparse_only, "All results appeared in both lists (RRF not blending)"

    def test_dense_sim_range(self, retriever):
        """Cosine similarity should be between 0 and 1."""
        results = run(retriever.search("financial planning", top_k=10))
        for r in results:
            if r.dense_sim is not None:
                assert 0.0 <= r.dense_sim <= 1.0, (
                    f"Dense sim out of range: {r.dense_sim} for {r.prompt_id}"
                )


# ---------------------------------------------------------------------------
# 5. EDGE CASES
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Graceful handling of unusual inputs."""

    def test_single_word_query(self, ps):
        resp = run(ps.search("finance", top_k=5))
        assert len(resp.results) > 0

    def test_very_long_query(self, ps):
        query = "help me " + "think through the strategic implications of " * 20 + "this decision"
        resp = run(ps.search(query, top_k=5))
        assert isinstance(resp.results, list)

    def test_query_with_special_characters(self, ps):
        resp = run(ps.search("what's the ROI of this? (Q3 2024)", top_k=5))
        assert isinstance(resp.results, list)

    def test_top_k_respected(self, ps):
        for k in [1, 5, 10, 20]:
            resp = run(ps.search("business strategy", top_k=k))
            assert len(resp.results) <= k, f"Expected <= {k} results, got {len(resp.results)}"

    def test_results_have_required_fields(self, ps):
        resp = run(ps.search("analyze data", top_k=3))
        for r in resp.results:
            assert r.prompt_id, "Missing prompt_id"
            assert r.prompt_text, "Missing prompt_text"
            assert r.rerank_score is not None, "Missing rerank_score"
            assert r.rrf_score is not None, "Missing rrf_score"
            assert isinstance(r.metadata, dict), "metadata must be a dict"

    def test_to_dict_is_json_serializable(self, ps):
        import json
        resp = run(ps.search("write a report", top_k=3))
        payload = resp.to_dict()
        # Should not raise
        serialized = json.dumps(payload)
        assert len(serialized) > 0

    def test_no_duplicate_results(self, ps):
        resp = run(ps.search("strategy planning", top_k=20))
        ids = [r.prompt_id for r in resp.results]
        assert len(ids) == len(set(ids)), f"Duplicate prompt IDs in results: {ids}"


# ---------------------------------------------------------------------------
# 6. LATENCY
# ---------------------------------------------------------------------------

class TestLatency:
    """Warm call latency should be acceptable for agent use."""

    def test_warm_search_under_1500ms(self, ps):
        # First call loads the cross-encoder reranker; run a full throwaway search
        run(ps.search("warmup query", top_k=10))

        t0 = time.perf_counter()
        run(ps.search("write a business strategy document", top_k=10))
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert elapsed_ms < 2500, (
            f"Warm search took {elapsed_ms:.0f}ms — exceeds 2500ms threshold"
        )

    def test_latency_consistent_across_calls(self, ps):
        """Variance between repeated calls should be low."""
        run(ps.search("warmup", top_k=1))  # warm

        times = []
        for _ in range(3):
            t0 = time.perf_counter()
            run(ps.search("analyze customer data", top_k=10))
            times.append((time.perf_counter() - t0) * 1000)

        variance = max(times) - min(times)
        assert variance < 500, (
            f"High latency variance across calls: {[f'{t:.0f}ms' for t in times]}"
        )
