"""Skills are processed like prompts where it affects what gets served.

Each test here pins one asymmetry that used to exist: taxonomy applied as a
score bonus instead of eligibility, a routing document of one short summary,
a coverage window fixed at a size tuned for five skills.
"""
import psycopg2
import psycopg2.extras
import pytest

from capillaries.config.paths import DB_CONFIG
from capillaries.skills.coverage import TOP_WINDOW, top_window
from capillaries.skills.promote import _modality, _routing_text
from capillaries.skills.recall import SkillRecall

# Every test here opens a Postgres connection, so it belongs behind the `db`
# marker CI deselects with `-m "not db"`. Without the mark these failed on
# every machine without a database, which is every machine but this one.
pytestmark = pytest.mark.db


QUERY = "post-mortem after a production outage"


@pytest.fixture(scope="module")
def recall():
    return SkillRecall()


def test_taxonomy_is_eligibility_not_a_bonus(recall):
    """A nonexistent domain must return nothing, not everything slightly demoted."""
    assert recall.candidates(QUERY, {"domain": ["cooking"]}) == []


def test_matching_domain_still_returns(recall):
    hits = recall.candidates(QUERY, {"domain": ["technical"]})
    assert hits, "a real domain must not filter everything out"
    assert all("technical" in c.metadata["domain"] for c in hits)


def test_both_channels_filter_not_just_lexical(recall):
    """The semantic channel had no taxonomy clause at all, so an excluded
    skill could still arrive with a dense_rank."""
    for c in recall.candidates(QUERY, {"domain": ["cooking"]}):
        assert c.dense_rank is None, "semantic channel ignored the filter"


def test_modality_excludes_text_only_skills(recall):
    """skills.skills had no modality column, so an image request narrowed
    prompts and left every text skill eligible."""
    assert recall.candidates(QUERY, {"modality": "image"}) == []


def test_filter_sql_parameterises_values():
    """The old boost fragments repr()-interpolated caller values into SQL."""
    where, params = SkillRecall._filter_sql({"domain": ["a'b"], "modality": "image"})
    assert "a'b" not in where
    assert ["a'b"] in params


def test_routing_text_pulls_in_step_content():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT name, summary, steps, routing_text FROM skills.skills "
                "WHERE jsonb_array_length(steps::jsonb) > 0 LIMIT 1"
            )
            row = cur.fetchone()
            if row is None:
                pytest.skip("no skills with steps")
            composed = _routing_text(cur, row["name"], row["summary"], row["steps"])
            assert len(composed) > len(row["summary"]), "no step content was added"
            assert row["summary"] in composed, "summary must survive composition"
            assert _modality(cur, row["steps"]) in {"text", "image", "video", "mixed"}
    finally:
        conn.close()


def test_coverage_window_grows_with_the_corpus():
    assert top_window(5) == TOP_WINDOW, "small corpus keeps the tuned default"
    assert top_window(100) > TOP_WINDOW, "gate must not tighten as skills are added"
    assert top_window(10_000) <= 50, "capped so it never swallows the ranking"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
