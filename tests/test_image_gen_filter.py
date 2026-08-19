from capillaries.search.api import _filter_image_gen_candidates
from capillaries.search.retriever import SearchResult


def _candidate(title: str) -> SearchResult:
    return SearchResult(
        prompt_id=title,
        title=title,
        prompt_text="",
        rrf_score=0.0,
        dense_rank=None,
        sparse_rank=None,
        dense_sim=None,
        sparse_sim=None,
    )


def test_non_generating_query_excludes_image_gen_prompts():
    candidates = [_candidate("Image Gen Pricing One Pager"), _candidate("Product Packaging")]

    filtered = _filter_image_gen_candidates("Create a SaaS pricing strategy", candidates)

    assert [candidate.title for candidate in filtered] == ["Product Packaging"]


def test_image_or_video_generation_query_keeps_image_gen_prompts():
    candidates = [_candidate("Image Gen Pricing One Pager"), _candidate("Product Packaging")]

    filtered = _filter_image_gen_candidates("Generate a launch video for our SaaS product", candidates)

    assert [candidate.title for candidate in filtered] == [
        "Image Gen Pricing One Pager", "Product Packaging",
    ]


def test_non_generating_video_query_excludes_image_gen_prompts():
    candidates = [_candidate("Image Gen Pricing One Pager"), _candidate("Product Packaging")]

    filtered = _filter_image_gen_candidates("Create a video distribution strategy", candidates)

    assert [candidate.title for candidate in filtered] == ["Product Packaging"]
