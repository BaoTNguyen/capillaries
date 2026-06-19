"""
Skill promotion: persist a validated chain from eval/search into skills.skills.

Usage:
    from capillaries.skills.promote import SkillPromoter

    promoter = SkillPromoter()
    skill = promoter.promote(
        chain=chain,              # Chain object from search.eval
        name="GTM Strategy Builder",
        routing_description="Builds a go-to-market strategy document for a new product or market segment",
    )
    print(skill.skill_id, skill.slug)
"""

from __future__ import annotations

import re
import json
import uuid
from dataclasses import dataclass
from typing import Any

import psycopg2
import psycopg2.extras

from capillaries.config import DB_CONFIG


@dataclass
class PromotedSkill:
    skill_id: str
    name: str
    slug: str
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

    Taxonomy (domain, intent, task_type) and complexity_level are derived
    automatically from the union of the chain's steps unless overridden.
    """

    def __init__(self, db_config: dict | None = None) -> None:
        self._db_config = db_config or DB_CONFIG

    # ── Public API ────────────────────────────────────────────────────────

    def promote(
        self,
        chain: Any,                        # Chain from search.eval._generate_candidates
        name: str,
        routing_description: str,
        slug: str | None = None,
        created_by: str = "manual",
    ) -> PromotedSkill:
        """
        Persist a Chain as a new skill (status: draft).

        Args:
            chain:               Chain object from search.eval.
            name:                Human-readable skill name.
            routing_description: One-line description used for routing/recall.
            slug:                URL-safe key (auto-derived from name if omitted).
            created_by:          'manual' or 'orchestrator'.

        Returns:
            PromotedSkill with skill_id, slug, and version.
        """
        slug = slug or _slugify(name)

        steps_json, taxonomy, complexity = self._build_steps(chain)

        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Resolve version — increment if slug already exists
                version = self._next_version(cur, slug)

                cur.execute(
                    """
                    INSERT INTO skills.skills (
                        skill_id, name, slug, routing_description,
                        steps,
                        domain, intent, task_type, complexity_level,
                        version, status, created_by
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s,
                        %s, %s, %s, %s,
                        %s, 'draft', %s
                    )
                    RETURNING skill_id, slug, version, status
                    """,
                    (
                        str(uuid.uuid4()),
                        name,
                        slug,
                        routing_description,
                        json.dumps(steps_json),
                        taxonomy["domain"],
                        taxonomy["intent"],
                        taxonomy["task_type"],
                        complexity,
                        version,
                        created_by,
                    ),
                )
                row = cur.fetchone()

        return PromotedSkill(
            skill_id=str(row["skill_id"]),
            name=name,
            slug=row["slug"],
            version=row["version"],
            status=row["status"],
        )

    def list_skills(self, status: str | None = None) -> list[dict]:
        """Return skills, optionally filtered by status."""
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if status:
                    cur.execute(
                        "SELECT skill_id, name, slug, version, status, routing_description, "
                        "total_runs, success_rate, created_at "
                        "FROM skills.skills WHERE status = %s ORDER BY created_at DESC",
                        (status,),
                    )
                else:
                    cur.execute(
                        "SELECT skill_id, name, slug, version, status, routing_description, "
                        "total_runs, success_rate, created_at "
                        "FROM skills.skills ORDER BY created_at DESC"
                    )
                return [dict(r) for r in cur.fetchall()]

    def create(
        self,
        name: str,
        routing_description: str,
        steps: list[dict] | None = None,
        slug: str | None = None,
        domain: list[str] | None = None,
        intent: list[str] | None = None,
        task_type: list[str] | None = None,
        complexity_level: int | None = None,
        created_by: str = "manual",
    ) -> PromotedSkill:
        """
        Create a skill from scratch without a Chain object.

        Steps are plain dicts: {prompt_id, step_order, rationale}.
        pinned_hash is fetched automatically for any prompt_id that exists
        in public.prompts; left null for custom/external prompt references.

        Args:
            name:                Human-readable skill name.
            routing_description: One-line description used for routing/recall.
            steps:               Ordered list of step dicts. Empty skill if omitted.
            slug:                Auto-derived from name if omitted.
            domain/intent/task_type: Taxonomy arrays. Auto-derived from steps if omitted.
            complexity_level:    1-5. Auto-derived (max of steps) if omitted.
        """
        slug = slug or _slugify(name)

        steps = steps or []
        steps_json, auto_taxonomy, auto_complexity = self._build_steps_from_dicts(steps)

        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                version = self._next_version(cur, slug)
                cur.execute(
                    """
                    INSERT INTO skills.skills (
                        skill_id, name, slug, routing_description,
                        steps,
                        domain, intent, task_type, complexity_level,
                        version, status, created_by
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s,
                        %s, %s, %s, %s,
                        %s, 'draft', %s
                    )
                    RETURNING skill_id, slug, version, status
                    """,
                    (
                        str(uuid.uuid4()), name, slug, routing_description,
                        json.dumps(steps_json),
                        domain or auto_taxonomy["domain"],
                        intent or auto_taxonomy["intent"],
                        task_type or auto_taxonomy["task_type"],
                        complexity_level or auto_complexity,
                        version, created_by,
                    ),
                )
                row = cur.fetchone()

        return PromotedSkill(
            skill_id=str(row["skill_id"]),
            name=name,
            slug=row["slug"],
            version=row["version"],
            status=row["status"],
        )

    def get(self, slug_or_id: str) -> dict | None:
        """
        Fetch a skill's full record by slug (latest version) or skill_id.
        Returns None if not found.
        """
        import re as _re
        _uuid_pattern = _re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", _re.I
        )
        is_uuid = bool(_uuid_pattern.match(slug_or_id))

        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if is_uuid:
                    cur.execute(
                        "SELECT * FROM skills.skills WHERE skill_id = %s",
                        (slug_or_id,),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM skills.skills WHERE slug = %s "
                        "ORDER BY version DESC LIMIT 1",
                        (slug_or_id,),
                    )
                row = cur.fetchone()
                return dict(row) if row else None

    def update_metadata(
        self,
        slug_or_id: str,
        name: str | None = None,
        routing_description: str | None = None,
        domain: list[str] | None = None,
        intent: list[str] | None = None,
        task_type: list[str] | None = None,
        complexity_level: int | None = None,
        changelog: str | None = None,
    ) -> None:
        """
        Update a skill's metadata fields in place.
        Only provided (non-None) fields are changed.
        """
        updates: list[str] = []
        params: list[Any] = []

        for field_name, value in [
            ("name", name),
            ("routing_description", routing_description),
            ("domain", domain),
            ("intent", intent),
            ("task_type", task_type),
            ("complexity_level", complexity_level),
            ("changelog", changelog),
        ]:
            if value is not None:
                updates.append(f"{field_name} = %s")
                params.append(value)

        if not updates:
            return

        # Resolve to skill_id
        skill = self.get(slug_or_id)
        if not skill:
            raise ValueError(f"Skill not found: {slug_or_id}")

        params.append(str(skill["skill_id"]))
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE skills.skills SET {', '.join(updates)} WHERE skill_id = %s",
                    params,
                )

    def set_steps(self, slug_or_id: str, steps: list[dict]) -> None:
        """
        Replace all steps for a skill.

        Each step dict: {prompt_id, step_order, rationale (optional)}.
        pinned_hash is fetched automatically from public.prompts.
        Step order is re-assigned from the list position if step_order is omitted.
        """
        steps_json, _, _ = self._build_steps_from_dicts(steps)
        skill = self.get(slug_or_id)
        if not skill:
            raise ValueError(f"Skill not found: {slug_or_id}")

        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE skills.skills SET steps = %s WHERE skill_id = %s",
                    (json.dumps(steps_json), str(skill["skill_id"])),
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
    ) -> tuple[list[dict], dict, int | None]:
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
        complexities: list[int] = []

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
        complexity = max(complexities) if complexities else None
        return steps_json, taxonomy, complexity

    def _build_steps(self, chain: Any) -> tuple[list[dict], dict, int | None]:
        """
        Convert a Chain into the JSONB steps list, derive taxonomy and complexity.

        Fetches content_hash for each prompt from the DB so pinned_hash is accurate.
        """
        prompt_ids = [r.prompt_id for _, r in chain.steps]
        hashes = self._fetch_content_hashes(prompt_ids)

        steps_json: list[dict] = []
        domains: set[str] = set()
        intents: set[str] = set()
        task_types: set[str] = set()
        complexities: list[int] = []

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
            if meta.get("complexity_level"):
                complexities.append(meta["complexity_level"])

        taxonomy = {
            "domain":     sorted(domains),
            "intent":     sorted(intents),
            "task_type":  sorted(task_types),
        }
        complexity = max(complexities) if complexities else None
        return steps_json, taxonomy, complexity

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

    def _next_version(self, cur, slug: str) -> int:
        """Return 1 for a new slug, or max(version)+1 for an existing one."""
        cur.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM skills.skills WHERE slug = %s",
            (slug,),
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


# ── Helpers ───────────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    """'GTM Strategy Builder' → 'gtm-strategy-builder'"""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug
