"""
Skill promotion: persist a validated chain from eval/search into skills.skills.

Usage:
    from capillaries.skills.promote import SkillPromoter

    promoter = SkillPromoter()
    skill = promoter.promote(
        chain=chain,              # Chain object from search.eval
        name="GTM Strategy Builder",
        summary="Builds a go-to-market strategy document for a new product or market segment",
    )
    print(skill.skill_id, skill.tag)
"""

from __future__ import annotations

import re
import json
import hashlib
import uuid
from dataclasses import dataclass
from typing import Any, Callable

import psycopg2
import psycopg2.extras

from capillaries.config import DB_CONFIG
from capillaries import spine


@dataclass
class PromotedSkill:
    skill_id: str
    name: str
    tag: str
    version: int
    status: str


class SkillPromoter:
    """
    Persists a chain as a skill in skills.skills.

    Steps JSONB format stored per step:
        {
            "prompt_id":   str,
            "step_order":  int,
            "rationale":   str | null,
            "pinned_hash": str          # content_hash at promotion time
        }

    Taxonomy (domain, intent, task_type) is derived automatically from the
    union of the chain's steps unless overridden.
    """

    def __init__(self, db_config: dict | None = None) -> None:
        self._db_config = db_config or DB_CONFIG

    # ── Public API ────────────────────────────────────────────────────────

    def promote(
        self,
        chain: Any,                        # Chain from search.eval._generate_candidates
        name: str,
        summary: str,
        tag: str | None = None,
        created_by: str = "manual",
    ) -> PromotedSkill:
        """
        Persist a Chain as a new skill (status: draft).

        Args:
            chain:               Chain object from search.eval.
            name:                Human-readable skill name.
            summary: One-line description used for routing/recall.
            tag:                URL-safe key (auto-derived from name if omitted).
            created_by:          'manual' or 'orchestrator'.

        Returns:
            PromotedSkill with skill_id, tag, and version.
        """
        tag = tag or _tagify(name)

        steps_json, taxonomy = self._build_steps(chain)
        content_hash = _content_hash(summary, steps_json)

        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Resolve version — increment if tag already exists
                version = self._next_version(cur, tag)

                cur.execute(
                    f"""
                    INSERT INTO skills.skills (
                        skill_id, name, tag, summary,
                        steps,
                        domain, intent, task_type,
                        version, status, created_by,
                        content_hash, search_tsv
                    ) VALUES (
                        %(skill_id)s, %(name)s, %(tag)s, %(summary)s,
                        %(steps)s,
                        %(domain)s, %(intent)s, %(task_type)s,
                        %(version)s, 'draft', %(created_by)s,
                        %(content_hash)s, {_SEARCH_TSV_SQL}
                    )
                    RETURNING skill_id, tag, version, status
                    """,
                    {
                        "skill_id": str(uuid.uuid4()),
                        "name": name,
                        "tag": tag,
                        "summary": summary,
                        "steps": json.dumps(steps_json),
                        "domain": taxonomy["domain"],
                        "intent": taxonomy["intent"],
                        "task_type": taxonomy["task_type"],
                        "version": version,
                        "created_by": created_by,
                        "content_hash": content_hash,
                    },
                )
                row = cur.fetchone()

        return PromotedSkill(
            skill_id=str(row["skill_id"]),
            name=name,
            tag=row["tag"],
            version=row["version"],
            status=row["status"],
        )

    def list_skills(self, status: str | None = None) -> list[dict]:
        """Return skills, optionally filtered by status."""
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if status:
                    cur.execute(
                        "SELECT skill_id, name, tag, version, status, summary, "
                        "total_runs, success_rate, created_at "
                        "FROM skills.skills WHERE status = %s ORDER BY created_at DESC",
                        (status,),
                    )
                else:
                    cur.execute(
                        "SELECT skill_id, name, tag, version, status, summary, "
                        "total_runs, success_rate, created_at "
                        "FROM skills.skills ORDER BY created_at DESC"
                    )
                return [dict(r) for r in cur.fetchall()]

    def create(
        self,
        name: str,
        summary: str,
        steps: list[dict] | None = None,
        tag: str | None = None,
        domain: list[str] | None = None,
        intent: list[str] | None = None,
        task_type: list[str] | None = None,
        created_by: str = "manual",
        source: str = "private",
    ) -> PromotedSkill:
        """
        Create a skill from scratch without a Chain object.

        Steps are plain dicts: {prompt_id, step_order, rationale}.
        pinned_hash is fetched automatically for any prompt_id that exists
        in public.prompts; left null for custom/external prompt references.

        Args:
            name:                Human-readable skill name.
            summary: One-line description used for routing/recall.
            steps:               Ordered list of step dicts. Empty skill if omitted.
            tag:                Auto-derived from name if omitted.
            domain/intent/task_type: Taxonomy arrays. Auto-derived from steps if omitted.
            source:              'private' (default) or 'public', same convention as prompts.source.
        """
        tag = tag or _tagify(name)

        steps = steps or []
        steps_json, auto_taxonomy = self._build_steps_from_dicts(steps)
        content_hash = _content_hash(summary, steps_json)
        domain = domain or auto_taxonomy["domain"]
        intent = intent or auto_taxonomy["intent"]
        task_type = task_type or auto_taxonomy["task_type"]

        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                version = self._next_version(cur, tag)
                cur.execute(
                    f"""
                    INSERT INTO skills.skills (
                        skill_id, name, tag, summary,
                        steps,
                        domain, intent, task_type,
                        version, status, created_by,
                        content_hash, source, search_tsv
                    ) VALUES (
                        %(skill_id)s, %(name)s, %(tag)s, %(summary)s,
                        %(steps)s,
                        %(domain)s, %(intent)s, %(task_type)s,
                        %(version)s, 'draft', %(created_by)s,
                        %(content_hash)s, %(source)s, {_SEARCH_TSV_SQL}
                    )
                    RETURNING skill_id, tag, version, status
                    """,
                    {
                        "skill_id": str(uuid.uuid4()), "name": name, "tag": tag, "summary": summary,
                        "steps": json.dumps(steps_json),
                        "domain": domain, "intent": intent, "task_type": task_type,
                        "version": version, "created_by": created_by,
                        "content_hash": content_hash, "source": source,
                    },
                )
                row = cur.fetchone()

        return PromotedSkill(
            skill_id=str(row["skill_id"]),
            name=name,
            tag=row["tag"],
            version=row["version"],
            status=row["status"],
        )

    def get(self, tag_or_id: str) -> dict | None:
        """
        Fetch a skill's full record by tag (latest version) or skill_id.
        Returns None if not found.
        """
        import re as _re
        _uuid_pattern = _re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", _re.I
        )
        is_uuid = bool(_uuid_pattern.match(tag_or_id))

        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if is_uuid:
                    cur.execute(
                        "SELECT * FROM skills.skills WHERE skill_id = %s",
                        (tag_or_id,),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM skills.skills WHERE tag = %s "
                        "ORDER BY version DESC LIMIT 1",
                        (tag_or_id,),
                    )
                row = cur.fetchone()
                return dict(row) if row else None

    def update_metadata(
        self,
        tag_or_id: str,
        name: str | None = None,
        summary: str | None = None,
        domain: list[str] | None = None,
        intent: list[str] | None = None,
        task_type: list[str] | None = None,
        changelog: str | None = None,
        last_evaluated: str | None = None,
        notes: str | None = None,
    ) -> None:
        """
        Update a skill's metadata fields in place.
        Only provided (non-None) fields are changed.

        last_evaluated: ISO date string ('YYYY-MM-DD') marking when a human
        last confirmed this skill still works — independent of `version`,
        which only counts re-promotions, not review events.
        """
        updates: list[str] = []
        params: list[Any] = []

        for field_name, value in [
            ("name", name),
            ("summary", summary),
            ("domain", domain),
            ("intent", intent),
            ("task_type", task_type),
            ("changelog", changelog),
            ("last_evaluated", last_evaluated),
            ("notes", notes),
        ]:
            if value is not None:
                updates.append(f"{field_name} = %s")
                params.append(value)

        if not updates:
            return

        # Resolve to skill_id
        skill = self.get(tag_or_id)
        if not skill:
            raise ValueError(f"Skill not found: {tag_or_id}")

        # content_hash tracks summary + steps, same as
        # prompts.content_hash tracks prompt_text — recompute whenever either
        # could have changed, so it stays a true drift signal, not stale.
        new_summary = summary if summary is not None else skill["summary"]
        content_hash = _content_hash(new_summary, skill["steps"])
        updates.append("content_hash = %s")
        params.append(content_hash)

        # routing_embedding is derived from the summary, so a summary edit
        # invalidates it. embed.py's incremental pass looks for NULL, which is
        # the only way it will ever revisit this row.
        if summary is not None and summary != skill["summary"]:
            updates.append("routing_embedding = NULL")

        # search_tsv depends on name/summary/taxonomy — recompute from the
        # resolved (post-update) values whenever any of them could have
        # changed, same reasoning as content_hash above.
        updates.append(
            "search_tsv = setweight(to_tsvector('english', %s), 'A') || "
            "setweight(to_tsvector('english', %s), 'B') || "
            "to_tsvector('english', "
            "COALESCE(array_to_string(%s::varchar[], ' '), '') || ' ' || "
            "COALESCE(array_to_string(%s::varchar[], ' '), '') || ' ' || "
            "COALESCE(array_to_string(%s::varchar[], ' '), ''))"
        )
        params.extend([
            name if name is not None else skill["name"],
            new_summary,
            domain if domain is not None else skill["domain"],
            intent if intent is not None else skill["intent"],
            task_type if task_type is not None else skill["task_type"],
        ])

        updates.append("last_updated = CURRENT_TIMESTAMP")

        params.append(str(skill["skill_id"]))
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE skills.skills SET {', '.join(updates)} WHERE skill_id = %s",
                    params,
                )

    def set_steps(self, tag_or_id: str, steps: list[dict]) -> None:
        """
        Replace all steps for a skill.

        Each step dict: {prompt_id, step_order, rationale (optional)}.
        pinned_hash is fetched automatically from public.prompts.
        Step order is re-assigned from the list position if step_order is omitted.
        """
        steps_json, _ = self._build_steps_from_dicts(steps)
        skill = self.get(tag_or_id)
        if not skill:
            raise ValueError(f"Skill not found: {tag_or_id}")

        content_hash = _content_hash(skill["summary"], steps_json)
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE skills.skills SET steps = %s, content_hash = %s, "
                    "last_updated = CURRENT_TIMESTAMP WHERE skill_id = %s",
                    (json.dumps(steps_json), content_hash, str(skill["skill_id"])),
                )

    def activate(self, skill_id: str) -> None:
        """Promote a draft skill to active."""
        self._set_status(skill_id, "active")

    def inactivate(self, skill_id: str) -> None:
        """Move an active skill to inactive."""
        self._set_status(skill_id, "inactive")

    # ── Internals ─────────────────────────────────────────────────────────

    def _build_steps_from_dicts(
        self, steps: list[dict]
    ) -> tuple[list[dict], dict]:
        """
        Build the JSONB steps list from plain dicts and derive taxonomy.
        Fetches pinned_hash from DB for any prompt_id that exists there.
        """
        prompt_ids = [s["prompt_id"] for s in steps if "prompt_id" in s]
        hashes = self._fetch_content_hashes(prompt_ids)

        steps_json: list[dict] = []
        domains: set[str] = set()
        intents: set[str] = set()
        task_types: set[str] = set()

        for i, step in enumerate(steps, 1):
            pid = step.get("prompt_id", "")
            steps_json.append({
                "prompt_id":   pid,
                "step_order":  step.get("step_order", i),
                "rationale":   step.get("rationale"),
                "pinned_hash": hashes.get(pid),
            })

        taxonomy = {"domain": sorted(domains), "intent": sorted(intents),
                    "task_type": sorted(task_types)}
        return steps_json, taxonomy

    def _build_steps(self, chain: Any) -> tuple[list[dict], dict]:
        """
        Convert a Chain into the JSONB steps list and derive taxonomy.

        Fetches content_hash for each prompt from the DB so pinned_hash is accurate.
        """
        prompt_ids = [r.prompt_id for _, r in chain.steps]
        hashes = self._fetch_content_hashes(prompt_ids)

        steps_json: list[dict] = []
        domains: set[str] = set()
        intents: set[str] = set()
        task_types: set[str] = set()

        for order, (_label, result) in enumerate(chain.steps, 1):
            steps_json.append({
                "prompt_id":   result.prompt_id,
                "step_order":  order,
                "rationale":   None,
                "pinned_hash": hashes.get(result.prompt_id),
            })
            meta = result.metadata
            domains.update(meta.get("domain") or [])
            intents.update(meta.get("intent") or [])
            task_types.update(meta.get("task_type") or [])

        taxonomy = {
            "domain":     sorted(domains),
            "intent":     sorted(intents),
            "task_type":  sorted(task_types),
        }
        return steps_json, taxonomy

    def _fetch_content_hashes(self, prompt_ids: list[str]) -> dict[str, str]:
        """Return {prompt_id: content_hash} for the given ids."""
        if not prompt_ids:
            return {}
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT title, content_hash FROM prompts WHERE title = ANY(%s)",
                    (prompt_ids,),
                )
                return {row[0]: row[1] for row in cur.fetchall()}

    def _next_version(self, cur, tag: str) -> int:
        """Return 1 for a new tag, or max(version)+1 for an existing one."""
        cur.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM skills.skills WHERE tag = %s",
            (tag,),
        )
        row = cur.fetchone()
        # Works with both regular cursor (tuple) and RealDictCursor (dict)
        val = row["v"] if isinstance(row, dict) else row[0]
        return val + 1

    def _set_status(self, skill_id: str, status: str) -> None:
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE skills.skills SET status = %s WHERE skill_id = %s",
                    (status, skill_id),
                )


# ── A/B promotion gate (STACK_READINESS §5.3) ──────────────────────────────
#
# Evaluate a candidate prompt text against the current canonical text over the
# golden_examples table, and promote only on a strict win. Never promotes
# blind: a prompt with no examples cannot be evaluated, so it cannot be
# promoted. Examples arrive via `cap optimize capture` — the automatic
# harvester was deleted, so this gate is currently fed by hand.


class _StaticPrediction:
    """Wraps a fixed text as a metric-fn "prediction" — ab_gate scores prompt
    *text* directly against golden outputs rather than running a live LM
    generation per candidate (that's dspy_optimize.PromptOptimizer's job);
    this keeps promotion checks cheap and metric-pluggable."""

    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class _Example:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


def _load_prompt_row(cur, prompt_title: str) -> dict | None:
    cur.execute(
        "SELECT prompt_id, prompt_text FROM prompts WHERE title = %s",
        (prompt_title,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _load_golden_examples(cur, prompt_id: str) -> list[dict]:
    cur.execute(
        """
        SELECT input_text, output_text
        FROM golden_examples
        WHERE prompt_id = %s AND NOT is_negative
        ORDER BY created_at
        """,
        (prompt_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def _score_text(text: str, examples: list[dict], metric_fn: Callable) -> float:
    scores = []
    for ex in examples:
        pred = _StaticPrediction(text)
        example = _Example(ex["output_text"])
        try:
            scores.append(float(metric_fn(pred, example)))
        except Exception:
            scores.append(0.0)
    return sum(scores) / max(len(scores), 1)


def ab_gate(
    prompt_title: str,
    candidate_text: str,
    metric: Callable | None = None,
    examples: list[dict] | None = None,
    db_config: dict | None = None,
) -> dict:
    """
    Evaluate `candidate_text` against the canonical prompt text for
    `prompt_title` over golden examples, and promote on a strict
    win only.

    Args:
        prompt_title: title of the prompt in `prompts`.
        candidate_text: the proposed replacement prompt text.
        metric: metric_fn(prediction, example) -> float, as in
            optimize/metrics.py. Defaults to optimize.metrics.exact_match.
        examples: override the stored examples (mainly for tests). Each
            dict needs at least {"output_text": str}. When omitted, loads
            golden_examples for this prompt from the DB.

    Returns:
        {"promoted": bool, "prompt_title", "baseline_score", "candidate_score",
         "reason" (when not promoted)}.

    Never promotes blind: no examples for this title -> not promoted.
    Every version is kept (prompt_variants keeps prior rows, only flips
    is_current — see dspy_optimize.PromptOptimizer._write_variant); a
    rejected candidate never touches the canonical text.
    """
    from capillaries.optimize.dspy_optimize import PromptOptimizer
    from capillaries.optimize.fences import assert_fences_unchanged
    from capillaries.optimize.metrics import MIN_IMPROVEMENT, get_metric

    config = db_config or DB_CONFIG
    metric_fn = metric or get_metric("exact_match")

    with psycopg2.connect(**config) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            prompt_row = _load_prompt_row(cur, prompt_title)
            if prompt_row is None:
                return {"promoted": False, "prompt_title": prompt_title, "reason": "prompt not found"}

            if examples is None:
                examples = _load_golden_examples(cur, str(prompt_row["prompt_id"]))

    if not examples:
        return {"promoted": False, "prompt_title": prompt_title, "reason": "no traffic"}

    canonical_text = prompt_row["prompt_text"]
    baseline_score = _score_text(canonical_text, examples, metric_fn)
    candidate_score = _score_text(candidate_text, examples, metric_fn)

    result = {
        "promoted": False,
        "prompt_title": prompt_title,
        "baseline_score": baseline_score,
        "candidate_score": candidate_score,
    }

    if candidate_score < baseline_score + MIN_IMPROVEMENT:
        result["reason"] = "candidate did not beat baseline by margin"
        spine.emit("skill.rejected", prompt_title=prompt_title,
                   baseline_score=baseline_score, candidate_score=candidate_score,
                   reason=result["reason"])
        return result

    try:
        assert_fences_unchanged(canonical_text, candidate_text)
    except ValueError as e:
        result["reason"] = f"fence violation: {e}"
        spine.emit("skill.rejected", prompt_title=prompt_title,
                   baseline_score=baseline_score, candidate_score=candidate_score,
                   reason=result["reason"])
        return result

    optimizer = PromptOptimizer(config)
    prompt_id = str(prompt_row["prompt_id"])
    optimizer._write_variant(prompt_id, "ab_gate", candidate_text, "ab_gate",
                              None, candidate_score, canonical_text)
    optimizer._update_canonical(prompt_id, candidate_text, canonical_text)

    result["promoted"] = True
    spine.emit("skill.promoted", prompt_title=prompt_title,
               baseline_score=baseline_score, candidate_score=candidate_score)
    return result


# ── Helpers ───────────────────────────────────────────────────────────────

# Same shape as prompts.search_tsv (obsidian_sync/ingest.py): name (A) +
# summary (B) + taxonomy (unweighted). Expects named params name/summary/
# domain/intent/task_type — the last three are varchar[] arrays.
_SEARCH_TSV_SQL = """
    setweight(to_tsvector('english', %(name)s), 'A') ||
    setweight(to_tsvector('english', %(summary)s), 'B') ||
    to_tsvector('english',
        COALESCE(array_to_string(%(domain)s::varchar[], ' '), '') || ' ' ||
        COALESCE(array_to_string(%(intent)s::varchar[], ' '), '') || ' ' ||
        COALESCE(array_to_string(%(task_type)s::varchar[], ' '), '')
    )
"""


def _content_hash(summary: str, steps: list[dict]) -> str:
    """Same shape as obsidian_sync/ingest.py's generate_content_hash for
    prompts: sha256 of the content that actually defines the skill's
    behavior, truncated to 16 hex chars."""
    canonical = summary + json.dumps(steps, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _tagify(name: str) -> str:
    """'GTM Strategy Builder' → 'gtm-strategy-builder'"""
    tag = name.lower().strip()
    tag = re.sub(r"[^\w\s-]", "", tag)
    tag = re.sub(r"[\s_]+", "-", tag)
    tag = re.sub(r"-+", "-", tag).strip("-")
    return tag
