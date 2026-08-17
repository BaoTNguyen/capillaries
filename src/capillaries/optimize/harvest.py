"""
Reward-grounded harvest: turn serving_log + arteries.rewards into golden
examples for the DSPy optimizer.

Metric precedence (STACK_READINESS §0, §5.1): episode-reward-weighted >
explicit feedback (skills.agent_feedback / classification_feedback) >
llm_judge. `llm_judge` in optimize/metrics.py is a fallback for prompts with
no episode traffic yet, never the default optimizer signal once real traffic
exists — this module is what grounds the "primary" tier of that precedence.

The join is one query: serving_log rows with a non-null episode_id joined to
arteries.rewards (reward_type='episode') on episode_id, with the served
prompt/skill resolved in the same statement (LEFT JOIN prompts / skills.skills
on served_id, keyed by served_kind). Both live in the same Postgres database
(`capillaries`), arteries owning its own schema (STACK_READINESS §1.1) — no
cross-database plumbing needed.

Adaptation from the spec: ExampleCapture.capture_external (optimize/capture.py)
has no `weight` parameter and golden_examples has no weight column — the
existing scaffold captures examples as (input, output, source, model) only.
Rather than widen that schema here, the reward signal is used two ways
instead of a stored per-row weight:
  1. Positive examples are only captured for rows that actually joined to a
     reward row (i.e. had real episode traffic) — the traffic itself is the
     filter, `capillaries_feedback`/no-reward rows are left to metrics.py's
     fallback tiers.
  2. The reward *magnitude* shows up as contrastive pairs: same normalized
     query served by different prompts/skills with a reward gap encodes the
     preference DSPy actually needs (good_output beat bad_output), which is
     a stronger training signal than a scalar weight would be with the
     current exact_match/llm_judge metrics (optimize/metrics.py) anyway.

Also: ExampleCapture is scoped to `prompts` (golden_examples.prompt_id FKs to
prompts.prompt_id) — there is no skill-level equivalent in the existing
scaffold. Rows where served_kind='skill' are counted (skills_skipped) but not
captured; wiring skill examples through skills.skills would need a parallel
capture path and is out of scope for M6.
"""

from __future__ import annotations

import re

import psycopg2
import psycopg2.extras

from capillaries.config.paths import DB_CONFIG
from capillaries.optimize.capture import ExampleCapture

JOIN_SQL = """
SELECT
    sl.id            AS serving_id,
    sl.episode_id,
    sl.query,
    sl.served_kind,
    sl.served_id,
    p.title          AS prompt_title,
    p.prompt_text    AS prompt_text,
    sk.name          AS skill_name,
    r.value          AS reward_value
FROM serving_log sl
JOIN arteries.rewards r
    ON r.episode_id = sl.episode_id
   AND r.reward_type = 'episode'
LEFT JOIN prompts p
    ON sl.served_kind = 'single_prompt'
   AND p.prompt_id::text = sl.served_id
LEFT JOIN skills.skills sk
    ON sl.served_kind = 'skill'
   AND sk.skill_id::text = sl.served_id
WHERE sl.episode_id IS NOT NULL
"""


def _normalize_query(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def harvest(
    prompt_title: str | None = None,
    min_reward_gap: float = 0.3,
    db_config: dict | None = None,
) -> dict:
    """
    Harvest golden examples from real episode traffic.

    Runs the serving_log <-> arteries.rewards join, then for each servable
    (title-resolvable) row captures an external golden example, and for
    query groups where reward diverges by >= min_reward_gap, captures a
    contrastive high/low pair.

    Args:
        prompt_title: restrict harvest to one prompt's title (matches either
            the served prompt's title or, when serving a skill, the skill's
            name). None harvests everything joinable.
        min_reward_gap: minimum reward spread within a normalized-query group
            required to emit a contrastive pair.

    Returns: counts dict — examples_captured, contrastive_pairs,
        skills_skipped, rows_considered.
    """
    config = db_config or DB_CONFIG
    capture = ExampleCapture(config)

    with psycopg2.connect(**config) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            sql = JOIN_SQL
            params: list = []
            if prompt_title:
                sql += " AND (p.title = %s OR sk.name = %s)"
                params.extend([prompt_title, prompt_title])
            try:
                cur.execute(sql, params)
                rows = [dict(r) for r in cur.fetchall()]
            except (psycopg2.errors.UndefinedTable, psycopg2.errors.InvalidSchemaName):
                # Reward-grounded harvest joins arteries.rewards, which only
                # exists when arteries set up its schema in this same database.
                # Degrade with a clear signal instead of a raw psycopg error.
                return {
                    "rows_considered": 0, "examples_captured": 0,
                    "contrastive_pairs": 0, "skills_skipped": 0,
                    "error": "arteries schema/rewards table not present in this database",
                }

    examples_captured = 0
    skills_skipped = 0
    resolvable: list[dict] = []

    for row in rows:
        if row["served_kind"] == "skill":
            skills_skipped += 1
            continue
        if not row["prompt_title"] or row["prompt_text"] is None:
            continue
        resolvable.append(row)
        try:
            capture.capture_external(
                prompt_title=row["prompt_title"],
                input_text=row["query"],
                output_text=row["prompt_text"],
            )
            examples_captured += 1
        except Exception:
            pass  # a bad/deleted prompt row shouldn't abort the whole harvest

    # Contrastive pairs: group by normalized query, compare reward extremes
    # across whichever served prompts answered that query.
    groups: dict[str, list[dict]] = {}
    for row in resolvable:
        key = _normalize_query(row["query"])
        groups.setdefault(key, []).append(row)

    contrastive_pairs = 0
    for group in groups.values():
        if len(group) < 2:
            continue
        best = max(group, key=lambda r: r["reward_value"])
        worst = min(group, key=lambda r: r["reward_value"])
        if best is worst:
            continue
        gap = best["reward_value"] - worst["reward_value"]
        if gap < min_reward_gap:
            continue
        try:
            capture.capture_contrastive(
                prompt_title=best["prompt_title"],
                input_text=best["query"],
                good_output=best["prompt_text"],
                bad_output=worst["prompt_text"],
            )
            contrastive_pairs += 1
        except Exception:
            pass

    return {
        "rows_considered": len(rows),
        "examples_captured": examples_captured,
        "contrastive_pairs": contrastive_pairs,
        "skills_skipped": skills_skipped,
    }
