"""Tests for the text passed to the cross-encoder."""

from capillaries.search.reranker import MAX_DOC_CHARS, _rerank_document
from capillaries.search.retriever import SearchResult


def _candidate(prompt_text="Build the model."):
    return SearchResult(
        prompt_id="prompt-1",
        title="13-Week Cash Flow Model",
        prompt_text=prompt_text,
        rrf_score=0.0,
        dense_rank=1,
        sparse_rank=None,
        dense_sim=0.9,
        sparse_sim=None,
        metadata={
            "summary": "Build a rolling cash forecast for a SaaS company.",
            "domain": ["finance"],
            "intent": ["build"],
            "task_type": ["financial-model"],
        },
    )


def test_rerank_document_includes_interpretable_candidate_fields():
    document = _rerank_document(_candidate())

    assert document.startswith("Title: 13-Week Cash Flow Model")
    assert "Summary: Build a rolling cash forecast for a SaaS company." in document
    assert "Domain: finance" in document
    assert "Intent: build" in document
    assert "Task type: financial-model" in document
    assert document.endswith("Prompt:\nBuild the model.")


def test_rerank_document_stays_within_the_existing_budget():
    document = _rerank_document(_candidate("x" * (MAX_DOC_CHARS * 2)))

    assert len(document) == MAX_DOC_CHARS
    assert "Title: 13-Week Cash Flow Model" in document


def test_rerank_document_uses_the_matched_chunk_without_prefix_truncation():
    candidate = _candidate()
    candidate.matched_chunk_id = "chunk-1"
    candidate.matched_chunk_text = "Weekly receipts, disbursements, and runway."

    document = _rerank_document(candidate)

    assert document.endswith("Prompt:\nWeekly receipts, disbursements, and runway.")
    assert "Build the model." not in document
