"""Metric functions for DSPy optimization."""

from __future__ import annotations

import difflib
import os
from typing import Callable

# A candidate must beat the baseline by at least this margin before it replaces
# anything. exact_match is difflib similarity on generated prose — noisy enough
# that a hair over baseline is often measurement noise, not a real win. The gate
# is `optimized > baseline + MIN_IMPROVEMENT`, not `optimized > baseline`.
#
# Raised 0.02 -> 0.05: on a 30-example set 0.02 sits inside the noise, so the
# fence was waving through wins it could not distinguish from measurement
# scatter. Drop it back toward 0.02 once an eval set of n > 100 exists.
MIN_IMPROVEMENT = float(os.getenv("CAPILLARIES_MIN_IMPROVEMENT", "0.05"))

_CUSTOM_METRICS: dict[str, Callable] = {}


def exact_match(example, prediction, trace=None, threshold: float = 0.85) -> float:
    """Normalized string similarity between predicted and expected output.

    Signature is (example, prediction, trace=None) — the calling convention
    DSPy itself uses for both dspy.Evaluate and teleprompter bootstrapping
    (trace is populated during compile, None during plain evaluation; unused
    here since this metric doesn't need per-step introspection).
    """
    predicted = _normalize(prediction.output_text)
    expected = _normalize(example.output_text)
    ratio = difflib.SequenceMatcher(None, predicted, expected).ratio()
    return ratio >= threshold


def llm_judge(example, prediction, trace=None, judge_model: str = "claude-haiku-4-5-20251001") -> float:
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
        def _judge(example, prediction, trace=None):
            return llm_judge(example, prediction, trace=trace, judge_model=judge_model)
        return _judge

    threshold = kwargs.get("threshold", 0.85)
    def _exact(example, prediction, trace=None):
        return exact_match(example, prediction, trace=trace, threshold=threshold)
    return _exact


def _normalize(text: str) -> str:
    """Normalize text for comparison: strip, collapse whitespace, lowercase."""
    return " ".join(text.strip().lower().split())
