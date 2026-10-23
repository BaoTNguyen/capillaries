"""CAPILLARIES-B15: an outcome outside the column's CHECK is refused at the model."""
import pytest
from pydantic import ValidationError

from capillaries.agent.api import FeedbackRequest


def test_only_the_four_outcomes_validate():
    for ok in ("success", "partial", "failure", "skipped"):
        assert FeedbackRequest(trace_id="t", outcome=ok).outcome == ok
    with pytest.raises(ValidationError):
        FeedbackRequest(trace_id="t", outcome="pass")
