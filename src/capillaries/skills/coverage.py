"""
Score a skill by how much of it the prompt retrieval already found.

The old path gave skills their own retrieval stack: an embedding over a
one-line `routing_description`, its own threshold, its own scale. That asks six
one-line documents to compete with 1 025 richly-indexed prompts, and it forced
a comparison between two scores from two different models.

This asks a different question. A skill *is* an ordered set of prompts, so if
the reranked results for a query already contain several of one skill's steps,
that is evidence from the index that works — full prompt bodies, summaries,
chunk embeddings, lexical matching — rather than from the one that doesn't.

The decisive signal is not "how good is the skill" but "does the query span
the workflow rather than one step of it". Two observations settle that, and
both come free from the existing ranking:

    1. the top-ranked prompt is itself a step of the skill
    2. at least MIN_MATCHED_STEPS of that skill appear in the top TOP_WINDOW

When both hold, the user asked about the workflow. Measured on this corpus:
"prepare a quarterly business review with variance analysis and a board deck"
returns `metrics-narrative-prompt` first — a QBR step — with 2 of 4 QBR steps
in the top 10. "we have a production incident..." returns
`postmortem-template-prompt` first, with 3 of 4 Incident Response steps.

An earlier version scored `coverage * mean(rerank)` and compared that to the
best prompt's score. That can never fire: coverage <= 1 and the best prompt's
score is already the maximum, so the skill is dampened by construction while
its competitor is not. Comparing a dampened aggregate against a raw maximum is
the same category error as the SINGLE_THRESHOLD it replaced.

Because the signal is derived, a skill with no resolvable steps scores 0 and
can never be served — which is correct, since serving it would hand the
caller an empty `prompt_text`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import psycopg2
import psycopg2.extras

from capillaries.config import DB_CONFIG

# A single step in common with a skill is coincidence — most skills borrow a
# generic step or two. Two is the point where the query starts to look like the
# workflow rather than like one of its parts.
MIN_MATCHED_STEPS = 2

# How far down the ranking a step still counts as evidence. Beyond this the
# result is a long-tail match, not something the user is being shown.
TOP_WINDOW = 10

# Serving a skill starts a stateful, multi-step session (skills.skill_sessions,
# accumulated context, a 24h expiry). Serving a prompt hands over text the user
# discards in a second. The costs of being wrong are not symmetric, which is
# why the top-ranked prompt must itself be a step of the skill — the strictest
# cheap evidence available that the query is about this workflow.
REQUIRE_TOP_IS_STEP = True


@dataclass
class SkillCoverage:
    skill_id: str
    name: str
    tag: str
    score: float
    coverage: float
    top_is_step: bool
    matched: int
    total: int
    steps: list[dict]

    def __repr__(self) -> str:
        return (f"{self.score:.3f}  {self.name} "
                f"({self.matched}/{self.total} steps)")


def score_skills(
    ranked: list,
    db_config: dict | None = None,
) -> list[SkillCoverage]:
    """Rank skills by how well the reranked prompt results cover their steps.

    `ranked` is the reranker's output — anything with `.prompt_id` and
    `.rerank_score`. Only the prompts actually returned count, so a skill
    cannot claim credit for a step that retrieval never surfaced.
    """
    if not ranked:
        return []

    scores = {r.prompt_id: r.rerank_score for r in ranked[:TOP_WINDOW]}

    conn = psycopg2.connect(**(db_config or DB_CONFIG))
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT skill_id::text, name, tag, steps "
                "FROM skills.skills WHERE status = 'active'"
            )
            rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    out: list[SkillCoverage] = []
    for row in rows:
        steps = row["steps"] if isinstance(row["steps"], list) else json.loads(row["steps"] or "[]")
        if not steps:
            continue

        ids = {s.get("prompt_id") for s in steps}
        hits = [scores[p] for p in ids if p in scores]
        if len(hits) < MIN_MATCHED_STEPS:
            continue

        coverage = len(hits) / len(steps)
        # Score on the evidence actually shown to the user: the strength of the
        # matched steps. Coverage is reported for inspection but does not scale
        # the score — dampening the skill while its competitor runs undamped is
        # what made the previous formula unable to fire.
        out.append(SkillCoverage(
            skill_id=row["skill_id"], name=row["name"], tag=row["tag"],
            score=max(hits),
            coverage=coverage, matched=len(hits), total=len(steps),
            top_is_step=ranked[0].prompt_id in ids,
            steps=steps,
        ))

    out.sort(key=lambda s: -s.score)
    return out


def best_skill(ranked: list, db_config: dict | None = None) -> SkillCoverage | None:
    """The skill the query is about, or None if it is about a single prompt.

    No score comparison against the prompt: the winning prompt is *inside* the
    skill, so the two are not competing for the same slot. The question is only
    whether the user wants that one step or the workflow around it.
    """
    top = next((c for c in score_skills(ranked, db_config)
                if c.top_is_step or not REQUIRE_TOP_IS_STEP), None)
    return top
