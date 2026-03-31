"""
Skill promotion: persist a validated chain from eval/search into skills.skills.

Usage:
    from prompt_flow.skills.promote import SkillPromoter

    promoter = SkillPromoter()
    skill = promoter.promote(
        chain=chain,              # Chain object from eval_report
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

from prompt_flow.config import DB_CONFIG


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
            "stage":       str,
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
        chain: Any,                        # Chain from eval_report._generate_candidates
        name: str,
        routing_description: str,
        slug: str | None = None,
        input_contract: dict | None = None,
        output_contract: dict | None = None,
        created_by: str = "manual",
    ) -> PromotedSkill:
        """
        Persist a Chain as a new skill (status: draft).

        Args:
            chain:               Chain object from eval_report.
            name:                Human-readable skill name.
            routing_description: One-line description used for routing/recall.
            slug:                URL-safe key (auto-derived from name if omitted).
            input_contract:      What the skill expects (JSONB). Defaults to {}.
            output_contract:     What the skill produces (JSONB). Defaults to {}.
            created_by:          'manual' or 'orchestrator'.

        Returns:
            PromotedSkill with skill_id, slug, and version.
        """
        slug = slug or _slugify(name)
        input_contract = input_contract or {}
        output_contract = output_contract or {}

        steps_json, taxonomy, complexity = self._build_steps(chain)

        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Resolve version — increment if slug already exists
                version = self._next_version(cur, slug)

                cur.execute(
                    """
                    INSERT INTO skills.skills (
                        skill_id, name, slug, routing_description,
                        steps, input_contract, output_contract,
                        domain, intent, task_type, complexity_level,
                        version, status, created_by
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s,
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
                        json.dumps(input_contract),
                        json.dumps(output_contract),
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

    def activate(self, skill_id: str) -> None:
        """Promote a draft skill to active."""
        self._set_status(skill_id, "active")

    def deprecate(self, skill_id: str) -> None:
        """Deprecate an active skill."""
        self._set_status(skill_id, "deprecated")

    # ── Internals ─────────────────────────────────────────────────────────

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

        for order, (stage, result) in enumerate(chain.steps, 1):
            steps_json.append({
                "prompt_id":   result.prompt_id,
                "stage":       stage,
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
                    "SELECT prompt_id, content_hash FROM prompts WHERE prompt_id = ANY(%s)",
                    (prompt_ids,),
                )
                return {row[0]: row[1] for row in cur.fetchall()}

    def _next_version(self, cur, slug: str) -> int:
        """Return 1 for a new slug, or max(version)+1 for an existing one."""
        cur.execute(
            "SELECT COALESCE(MAX(version), 0) FROM skills.skills WHERE slug = %s",
            (slug,),
        )
        return cur.fetchone()[0] + 1

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
