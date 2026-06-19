"""Metric functions for DSPy optimization."""

from __future__ import annotations

import difflib
from typing import Callable

_CUSTOM_METRICS: dict[str, Callable] = {}


def exact_match(prediction, example, threshold: float = 0.85) -> float:
    """Normalized string similarity between predicted and expected output."""
    predicted = _normalize(prediction.output_text)
    expected = _normalize(example.output_text)
    ratio = difflib.SequenceMatcher(None, predicted, expected).ratio()
    return ratio >= threshold


def llm_judge(prediction, example, judge_model: str = "claude-haiku-4-5-20251001") -> float:
    """LLM-as-judge scoring similarity to golden output.

    Uses a cheaper model than the one being optimized to avoid circular evaluation.
    """
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=judge_model,
        max_tokens=100,
        messages=[{
            "role": "user",
            "content": (
                "Rate how well the candidate output matches the expected output on a 0-10 scale. "
                "Consider: completeness, accuracy, format adherence, and quality.\n\n"
                f"Expected output:\n{example.output_text}\n\n"
                f"Candidate output:\n{prediction.output_text}\n\n"
                "Respond with ONLY a number 0-10."
            ),
        }],
    )
    try:
        score = float(response.content[0].text.strip()) / 10.0
        return max(0.0, min(1.0, score))
    except (ValueError, IndexError):
        return 0.0


def register_custom_metric(prompt_title: str, fn: Callable) -> None:
    """Register a custom metric function for a specific prompt."""
    _CUSTOM_METRICS[prompt_title] = fn


def get_metric(metric_type: str, prompt_title: str | None = None, **kwargs) -> Callable:
    """Return the appropriate metric function."""
    if metric_type == "custom" and prompt_title and prompt_title in _CUSTOM_METRICS:
        return _CUSTOM_METRICS[prompt_title]

    if metric_type == "llm_judge":
        judge_model = kwargs.get("judge_model", "claude-haiku-4-5-20251001")
        def _judge(prediction, example):
            return llm_judge(prediction, example, judge_model=judge_model)
        return _judge

    threshold = kwargs.get("threshold", 0.85)
    def _exact(prediction, example):
        return exact_match(prediction, example, threshold=threshold)
    return _exact


def _normalize(text: str) -> str:
    """Normalize text for comparison: strip, collapse whitespace, lowercase."""
    return " ".join(text.strip().lower().split())
