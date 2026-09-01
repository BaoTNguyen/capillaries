"""Per-model skill variants: the chain's shape, not any step's text.

prompt_variants already varies the TEXT of a step per model. This varies
WHICH steps run, which prompt_variants cannot express however many rows it
holds. The two compose — a variant chain still resolves each of its steps
through prompt_variants.
"""
import json

import psycopg2
import pytest

from capillaries.config.paths import DB_CONFIG
from capillaries.skills.promote import SkillPromoter
from capillaries.skills.recall import SkillRecall

# Every test here opens a Postgres connection, so it belongs behind the `db`
# marker CI deselects with `-m "not db"`. Without the mark these failed on
# every machine without a database, which is every machine but this one.
pytestmark = pytest.mark.db


MODEL = "test-model-skill-variants"


@pytest.fixture(scope="module")
def promoter():
    return SkillPromoter()


@pytest.fixture(scope="module")
def skill(promoter):
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tag FROM skills.skills "
                "WHERE jsonb_array_length(steps::jsonb) > 1 LIMIT 1"
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        pytest.skip("no multi-step skill to vary")
    return promoter.get(row[0])


@pytest.fixture
def variant(promoter, skill):
    """A shorter chain for MODEL, removed again afterwards."""
    base = skill["steps"] if isinstance(skill["steps"], list) else json.loads(skill["steps"])
    short = [
        {"prompt_id": s["prompt_id"], "step_order": i, "rationale": s.get("rationale")}
        for i, s in enumerate(base[:1], 1)
    ]
    promoter.set_variant(skill["tag"], MODEL, short, notes="pytest")
    yield base, short
    # Retiring leaves the row for comparison, which is right in production
    # and wrong for a test that runs repeatedly.
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("DELETE FROM skills.skill_variants WHERE model = %s", (MODEL,))
    finally:
        conn.close()


def _resolve(skill, model):
    return SkillRecall()._resolve_steps(
        skill["steps"], model=model, skill_id=str(skill["skill_id"])
    )


def test_variant_replaces_the_chain(skill, variant):
    base, short = variant
    assert len(_resolve(skill, MODEL)) == len(short) < len(base)


def test_model_without_a_variant_gets_the_base_chain(skill, variant):
    base, _ = variant
    assert len(_resolve(skill, "some-other-model")) == len(base)


def test_no_model_gets_the_base_chain(skill, variant):
    base, _ = variant
    assert len(_resolve(skill, None)) == len(base)


def test_variant_steps_still_resolve_prompt_text(skill, variant):
    """The two layers compose: a variant chain is not raw ids."""
    assert all(s["prompt_text"] for s in _resolve(skill, MODEL))


def test_clearing_restores_the_base_chain(promoter, skill, variant):
    base, _ = variant
    promoter.clear_variant(skill["tag"], MODEL)
    assert len(_resolve(skill, MODEL)) == len(base)


def test_only_one_current_variant_per_model(promoter, skill, variant):
    base, _ = variant
    promoter.set_variant(skill["tag"], MODEL,
                         [{"prompt_id": base[0]["prompt_id"], "step_order": 1}])
    current = [v for v in promoter.list_variants(skill["tag"]) if v["model"] == MODEL]
    assert len(current) == 1, "the unique partial index must keep exactly one live"


def test_rejects_a_chain_pointing_at_a_missing_prompt(promoter, skill):
    with pytest.raises(ValueError, match="missing or inactive"):
        promoter.set_variant(
            skill["tag"], MODEL,
            [{"prompt_id": "00000000-0000-0000-0000-000000000000", "step_order": 1}],
        )


def test_rejects_an_empty_chain(promoter, skill):
    with pytest.raises(ValueError):
        promoter.set_variant(skill["tag"], MODEL, [])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
