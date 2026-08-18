"""Pin the step->prompt lookups against the real schema.

Both `agent/execute.py` and `skills/recall.py` resolve a skill step's
`prompt_id` to prompt text. Both once matched on `title` against what is
actually a UUID — which returned nothing without raising — and named a
`prompt_title` column on `prompt_variants` that has never existed.

The silent half is why this needs a test: a step that resolves to empty text
looks like a content problem, not a query bug. These assertions fail loudly
instead.

Marked `db` — the whole point is checking real column names, so there is
nothing to verify without a live schema. CI deselects it.
"""

from __future__ import annotations

import json

import pytest

psycopg2 = pytest.importorskip("psycopg2")
import psycopg2.extras  # noqa: E402

from capillaries.config.paths import DB_CONFIG  # noqa: E402

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def cur():
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            yield c


@pytest.fixture(scope="module")
def step_prompt_ids(cur):
    cur.execute(
        "SELECT steps FROM skills.skills WHERE jsonb_array_length(steps) > 0 LIMIT 1"
    )
    row = cur.fetchone()
    if not row:
        pytest.skip("no skills with steps in this database")
    steps = row["steps"] if isinstance(row["steps"], list) else json.loads(row["steps"])
    return [s["prompt_id"] for s in steps]


def test_prompt_variants_has_no_prompt_title_column(cur):
    """The column the old queries named. If it ever appears, revisit both."""
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'prompt_variants'
        """
    )
    cols = {r["column_name"] for r in cur.fetchall()}
    assert "prompt_id" in cols
    assert "prompt_title" not in cols, "schema changed — the lookups can be simplified"


def test_steps_reference_uuids_not_titles(cur, step_prompt_ids):
    """Steps store prompt UUIDs. Matching them on title resolves nothing."""
    cur.execute(
        "SELECT count(*) AS n FROM prompts WHERE prompt_id = ANY(%s::uuid[])",
        (step_prompt_ids,),
    )
    assert cur.fetchone()["n"] == len(step_prompt_ids)

    cur.execute(
        "SELECT count(*) AS n FROM prompts WHERE title = ANY(%s)", (step_prompt_ids,)
    )
    assert cur.fetchone()["n"] == 0, "steps hold titles now — both lookups need updating"


def test_recall_lookup_resolves_every_step(cur, step_prompt_ids):
    """skills/recall.py: the batch form, keyed the way the caller reads it."""
    cur.execute(
        """
        SELECT prompt_id, title, prompt_text, domain, intent, task_type, content_hash
        FROM prompts
        WHERE prompt_id = ANY(%s::uuid[])
        """,
        (step_prompt_ids,),
    )
    data = {str(r["prompt_id"]): r for r in cur.fetchall()}

    # str() matters: psycopg2 returns uuid.UUID, step["prompt_id"] is a JSON string.
    for pid in step_prompt_ids:
        assert pid in data, f"step {pid} did not resolve"
        assert data[pid]["prompt_text"], f"step {pid} resolved to empty text"


def test_variant_lookups_execute(cur, step_prompt_ids):
    """Both variant queries run. Zero rows is fine; a raise is not."""
    cur.execute(
        """
        SELECT prompt_id, prompt_text FROM prompt_variants
        WHERE prompt_id = ANY(%s::uuid[]) AND model = %s AND is_current = TRUE
        """,
        (step_prompt_ids, "any-model"),
    )
    cur.fetchall()

    cur.execute(
        """
        SELECT prompt_text FROM prompt_variants
        WHERE prompt_id = %s::uuid AND model = %s AND is_current = TRUE
        LIMIT 1
        """,
        (step_prompt_ids[0], "any-model"),
    )
    cur.fetchall()
