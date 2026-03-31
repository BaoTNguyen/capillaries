#!/usr/bin/env python3
"""
Database setup for the skills schema.

Creates the skills schema inside the existing prompt_flow database.
Safe to re-run — all statements use IF NOT EXISTS.

Usage:
    python -m prompt_flow.db.setup_skills
    python src/prompt_flow/db/setup_skills.py
"""

import psycopg2
from prompt_flow.config.paths import DB_CONFIG


def create_skills_schema(cursor) -> None:
    cursor.execute("CREATE SCHEMA IF NOT EXISTS skills;")


def create_skills_table(cursor) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skills.skills (
            skill_id    UUID    PRIMARY KEY DEFAULT gen_random_uuid(),

            -- Identity
            name        VARCHAR NOT NULL,
            slug        VARCHAR UNIQUE NOT NULL,  -- stable key across versions
                                                  -- e.g. 'gtm-strategy-builder'

            -- What this skill does, in one line.
            -- Used by the orchestrator to match a request to a skill.
            routing_description TEXT NOT NULL,

            -- The ordered prompts that make up this skill.
            -- [{prompt_id, stage, step_order, rationale, pinned_hash}]
            -- pinned_hash records the prompt's content_hash at validation time.
            -- Skills always run on current prompt content — drift is not a blocker.
            -- Use pinned_hash to correlate quality changes with prompt edits
            -- during periodic review, not as a gate on skill execution.
            steps       JSONB NOT NULL DEFAULT '[]',

            -- What the skill expects as input and produces as output.
            input_contract  JSONB NOT NULL DEFAULT '{}',
            output_contract JSONB NOT NULL DEFAULT '{}',

            -- Classification (mirrors prompt taxonomy for routing)
            domain          VARCHAR[] DEFAULT '{}',
            intent          VARCHAR[] DEFAULT '{}',
            task_type       VARCHAR[] DEFAULT '{}',
            complexity_level INTEGER CHECK (complexity_level BETWEEN 1 AND 5),

            -- Versioning: never update a skill — create a new version and link back.
            version         INTEGER NOT NULL DEFAULT 1,
            parent_skill_id UUID REFERENCES skills.skills(skill_id),
            changelog       TEXT,  -- what changed in this version

            -- Quality (updated by aggregating skill_runs)
            success_rate    FLOAT,
            total_runs      INTEGER DEFAULT 0,
            last_run_at     TIMESTAMP,

            -- Lifecycle
            status      VARCHAR NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft', 'active', 'deprecated', 'archived')),

            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by  VARCHAR DEFAULT 'manual',  -- 'manual' | 'orchestrator'

            UNIQUE (slug, version)
        );
    """)


def create_skill_runs_table(cursor) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skills.skill_runs (
            run_id      UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
            skill_id    UUID    NOT NULL REFERENCES skills.skills(skill_id),
            skill_version INTEGER NOT NULL,  -- denormalized so history survives archival

            -- Outcome
            status      VARCHAR CHECK (status IN ('success', 'partial', 'failure', 'aborted')),
            score       FLOAT CHECK (score BETWEEN 0 AND 1),
            notes       TEXT,

            -- Snapshot of which prompt versions ran.
            -- [{prompt_id, content_hash}]
            -- If a skill's output quality drops, diff these against
            -- steps[].pinned_hash to see which prompts changed and when.
            -- Informational only — does not affect whether the skill runs.
            step_hashes JSONB DEFAULT '[]',

            started_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            duration_ms INTEGER
        );
    """)


def create_indexes(cursor) -> None:
    indexes = [
        # Active skill lookup by slug — the most common query pattern
        """CREATE INDEX IF NOT EXISTS idx_skills_slug_active
           ON skills.skills (slug, version DESC)
           WHERE status = 'active';""",

        # Taxonomy filtering for routing
        "CREATE INDEX IF NOT EXISTS idx_skills_domain    ON skills.skills USING GIN (domain);",
        "CREATE INDEX IF NOT EXISTS idx_skills_intent    ON skills.skills USING GIN (intent);",
        "CREATE INDEX IF NOT EXISTS idx_skills_task_type ON skills.skills USING GIN (task_type);",
        "CREATE INDEX IF NOT EXISTS idx_skills_status    ON skills.skills (status);",

        # Full-text search on routing descriptions
        """CREATE INDEX IF NOT EXISTS idx_skills_routing_fts
           ON skills.skills USING GIN (to_tsvector('english', routing_description));""",

        # Run history per skill
        """CREATE INDEX IF NOT EXISTS idx_skill_runs_skill
           ON skills.skill_runs (skill_id, started_at DESC);""",
    ]
    for sql in indexes:
        cursor.execute(sql)


def main() -> None:
    print("Setting up skills schema...")

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        print("  Creating schema...")
        create_skills_schema(cursor)

        print("  Creating skills table...")
        create_skills_table(cursor)

        print("  Creating skill_runs table...")
        create_skill_runs_table(cursor)

        print("  Creating indexes...")
        create_indexes(cursor)

        conn.commit()
        print("Skills schema ready.")

    except psycopg2.Error as e:
        print(f"Database error: {e}")
        raise
    finally:
        if "cursor" in locals():
            cursor.close()
        if "conn" in locals():
            conn.close()


if __name__ == "__main__":
    main()
