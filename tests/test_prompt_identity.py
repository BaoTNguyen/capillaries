"""One identifier for cross-table prompt references: prompt_id, not title.

Steps store UUIDs. agent_feedback.prompt_id was VARCHAR and accepted both, so
different callers stored different things and every query joining it picked a
side and silently matched nothing. Four sites were already fixed with comments
saying so before these ones were found; the column type is what stops a fifth.
"""
import psycopg2
import pytest

from capillaries.agent.feedback import FeedbackHandler, get_quality_prior
from capillaries.config.paths import DB_CONFIG
from capillaries.lifecycle.cascade import find_dependent_skills

# Every test here opens a Postgres connection, so it belongs behind the `db`
# marker CI deselects with `-m "not db"`. Without the mark these failed on
# every machine without a database, which is every machine but this one.
pytestmark = pytest.mark.db


TRACE = "pytest-prompt-identity"


@pytest.fixture
def a_step_prompt():
    """A prompt that is a step of some active skill, as (uuid, title)."""
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT step->>'prompt_id' FROM skills.skills, "
            "jsonb_array_elements(steps) AS step WHERE status = 'active' LIMIT 1"
        )
        row = cur.fetchone()
        if row is None:
            pytest.skip("no active skill with steps")
        uid = row[0]
        cur.execute("SELECT title FROM prompts WHERE prompt_id::text = %s", (uid,))
        title = cur.fetchone()[0]
        yield uid, title
        cur.execute("DELETE FROM skills.agent_feedback WHERE trace_id = %s", (TRACE,))
        FeedbackHandler().refresh_quality_prior()
    finally:
        conn.close()


def test_feedback_column_is_uuid_typed():
    """VARCHAR is what let both conventions coexist."""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema='skills' AND table_name='agent_feedback' "
            "AND column_name='prompt_id'"
        )
        assert cur.fetchone()[0] == "uuid"
    finally:
        conn.close()


def test_cascade_finds_dependents_by_either_reference(a_step_prompt):
    """The only caller passes a title; steps store UUIDs. Both must work."""
    uid, title = a_step_prompt
    by_uuid = {d["tag"] for d in find_dependent_skills(uid)}
    by_title = {d["tag"] for d in find_dependent_skills(title)}
    assert by_uuid, "a prompt that IS a step must report a dependent skill"
    assert by_uuid == by_title


def test_feedback_normalises_a_title_to_the_uuid(a_step_prompt):
    uid, title = a_step_prompt
    h = FeedbackHandler()
    h.submit_feedback(trace_id=TRACE, outcome="success", mode="single_prompt",
                      prompt_id=title, quality_score=0.8)
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        cur = conn.cursor()
        cur.execute("SELECT prompt_id::text FROM skills.agent_feedback WHERE trace_id = %s", (TRACE,))
        assert [r[0] for r in cur.fetchall()] == [uid]
    finally:
        conn.close()


def test_feedback_reaches_the_quality_prior(a_step_prompt):
    """submit -> matview -> get_quality_prior. Every hop joins on prompt_id."""
    uid, _ = a_step_prompt
    h = FeedbackHandler()
    h.submit_feedback(trace_id=TRACE, outcome="success", mode="single_prompt",
                      prompt_id=uid, quality_score=0.9)
    h.refresh_quality_prior()
    assert get_quality_prior(uid) is not None, "feedback never reached the prior"


def test_recorded_usage_excludes_a_prompt_from_staleness(a_step_prompt):
    """The whole point: staleness compared titles to UUIDs, so recording usage
    changed nothing and every prompt looked stale forever."""
    uid, title = a_step_prompt
    from capillaries.lifecycle.inactivate import inactivate_stale_prompts

    before = inactivate_stale_prompts(dry_run=True, max_fraction=1.0)
    FeedbackHandler().submit_feedback(trace_id=TRACE, outcome="success",
                                      mode="single_prompt", prompt_id=uid)
    after = inactivate_stale_prompts(dry_run=True, max_fraction=1.0)
    assert title in before, "prompt with no feedback should read as stale"
    assert title not in after, "recording usage must remove it from the stale set"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
