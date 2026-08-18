#!/usr/bin/env python3
"""
Database setup for the skills schema.

Creates the skills schema inside the existing capillaries database.
Safe to re-run — all statements use IF NOT EXISTS.

Usage:
    python -m capillaries.db.setup_skills
    python src/capillaries/db/setup_skills.py
"""

import psycopg2
from capillaries.config.paths import DB_CONFIG, EMBED_DIM


def create_skills_schema(cursor) -> None:
    cursor.execute("CREATE SCHEMA IF NOT EXISTS skills;")


def create_skills_table(cursor) -> None:
    # .replace() rather than an f-string: the DDL uses `'{}'` array defaults.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skills.skills (
            skill_id    UUID    PRIMARY KEY DEFAULT gen_random_uuid(),

            -- Identity
            name        VARCHAR NOT NULL,
            tag        VARCHAR UNIQUE NOT NULL,  -- stable key across versions
                                                  -- e.g. 'gtm-strategy-builder'

            -- What this skill does, in one line.
            -- Used by the orchestrator to match a request to a skill.
            summary TEXT NOT NULL,

            -- The ordered prompts that make up this skill.
            -- [{prompt_id, stage, step_order, rationale, pinned_hash}]
            -- pinned_hash records the prompt's content_hash at validation time.
            -- Skills always run on current prompt content — drift is not a blocker.
            -- Use pinned_hash to correlate quality changes with prompt edits
            -- during periodic review, not as a gate on skill execution.
            steps       JSONB NOT NULL DEFAULT '[]',

            -- Classification (mirrors prompt taxonomy for routing)
            domain          VARCHAR[] DEFAULT '{}',
            intent          VARCHAR[] DEFAULT '{}',
            task_type       VARCHAR[] DEFAULT '{}',

            -- Versioning
            version         INTEGER NOT NULL DEFAULT 1,
            changelog       TEXT,

            -- Change tracking, same shape as prompts.content_hash /
            -- last_updated: automatic, set on every write, independent of
            -- `version` (a counter) and `last_evaluated` (a human signal).
            content_hash    VARCHAR,
            last_updated    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            -- Quality (updated by aggregating skill_runs)
            success_rate    FLOAT,
            total_runs      INTEGER DEFAULT 0,
            last_run_at     TIMESTAMP,

            -- Lifecycle
            status      VARCHAR NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft', 'active', 'inactive')),

            -- Human review signal, mirrors prompts.last_evaluated: when
            -- someone last confirmed this skill still works, independent of
            -- `version` (which only counts re-promotions, not review events).
            last_evaluated DATE,

            -- Freeform notes, same as prompts.notes
            notes       TEXT,

            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by  VARCHAR DEFAULT 'manual',  -- 'manual' | 'orchestrator'

            -- Data source, same convention as prompts.source
            source      VARCHAR DEFAULT 'private',  -- 'private' | 'public'

            -- Semantic search on summary; width from EMBED_DIM,
            -- same convention as prompts.embedding / embedding_version
            routing_embedding VECTOR(EMBED_DIM),
            embedding_version VARCHAR,

            -- Lexical search, same shape as prompts.search_tsv: name (A) +
            -- summary (B) + taxonomy (unweighted). Kept up to date by
            -- SkillPromoter on every write, not a trigger — mirrors how
            -- obsidian_sync/ingest.py computes prompts.search_tsv inline.
            search_tsv  TSVECTOR,

            UNIQUE (tag, version)
        );
    """.replace("VECTOR(EMBED_DIM)", f"VECTOR({EMBED_DIM})"))
    # Table may already exist from before these columns were added.
    for stmt in [
        "ALTER TABLE skills.skills ADD COLUMN IF NOT EXISTS last_evaluated DATE;",
        "ALTER TABLE skills.skills ADD COLUMN IF NOT EXISTS content_hash VARCHAR;",
        "ALTER TABLE skills.skills ADD COLUMN IF NOT EXISTS last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP;",
        "ALTER TABLE skills.skills ADD COLUMN IF NOT EXISTS source VARCHAR DEFAULT 'private';",
        "ALTER TABLE skills.skills ADD COLUMN IF NOT EXISTS embedding_version VARCHAR;",
        "ALTER TABLE skills.skills ADD COLUMN IF NOT EXISTS notes TEXT;",
        "ALTER TABLE skills.skills ADD COLUMN IF NOT EXISTS search_tsv TSVECTOR;",
    ]:
        cursor.execute(stmt)
    cursor.execute("ALTER TABLE skills.skills DROP COLUMN IF EXISTS complexity_level;")


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


def create_skill_sessions_table(cursor) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skills.skill_sessions (
            session_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            skill_id        UUID NOT NULL REFERENCES skills.skills(skill_id),
            trace_id        VARCHAR NOT NULL,
            current_step    INTEGER NOT NULL DEFAULT 0,
            status          VARCHAR NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'completed', 'aborted', 'expired')),

            -- Context accumulator: compressed summary updated after each step
            context_summary TEXT DEFAULT '',

            -- Per-step outputs (append-only JSONB array)
            step_outputs    JSONB DEFAULT '[]',

            -- Metadata
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at      TIMESTAMP DEFAULT (CURRENT_TIMESTAMP + INTERVAL '24 hours'),

            -- Variables provided by the agent across all steps
            agent_context   JSONB DEFAULT '{}'
        );
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_skill_sessions_active
        ON skills.skill_sessions (session_id)
        WHERE status = 'active';
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_skill_sessions_expire
        ON skills.skill_sessions (expires_at)
        WHERE status = 'active';
    """)


def create_agent_feedback_table(cursor) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skills.agent_feedback (
            feedback_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            trace_id        VARCHAR NOT NULL,
            session_id      UUID REFERENCES skills.skill_sessions(session_id),

            -- What was recommended
            mode            VARCHAR NOT NULL,  -- 'single', 'skill', 'chain'
            prompt_id       VARCHAR,           -- for single-prompt recommendations
            skill_id        UUID,              -- for skill recommendations

            -- Agent's assessment
            outcome         VARCHAR NOT NULL CHECK (outcome IN ('success', 'partial', 'failure', 'skipped')),
            quality_score   FLOAT CHECK (quality_score BETWEEN 0 AND 1),
            failure_step    INTEGER,
            failure_reason  VARCHAR,
            notes           TEXT,

            -- Prompt modifications (JSONB array)
            prompt_modifications JSONB DEFAULT '[]',

            -- Per-step feedback (JSONB array)
            per_step_feedback    JSONB DEFAULT '[]',

            -- Context at time of feedback
            situation_text  TEXT,              -- original situation from the route request
            inferred_domain VARCHAR[],
            inferred_stage  VARCHAR,

            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_feedback_prompt
        ON skills.agent_feedback (prompt_id, created_at DESC)
        WHERE prompt_id IS NOT NULL;
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_feedback_skill
        ON skills.agent_feedback (skill_id, created_at DESC)
        WHERE skill_id IS NOT NULL;
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_feedback_outcome
        ON skills.agent_feedback (outcome);
    """)


def create_materialized_views(cursor) -> None:
    cursor.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS prompt_quality_prior AS
        SELECT
            prompt_id,
            COUNT(*) AS feedback_count,
            AVG(CASE
                WHEN outcome = 'success' THEN 1.0
                WHEN outcome = 'partial' THEN 0.5
                WHEN outcome = 'failure' THEN 0.0
                ELSE NULL
            END) AS success_rate,
            AVG(quality_score) FILTER (WHERE quality_score IS NOT NULL) AS avg_quality,
            (COUNT(*) * AVG(CASE WHEN outcome = 'success' THEN 1.0 WHEN outcome = 'partial' THEN 0.5 ELSE 0.0 END)
             + 5 * 0.5) / (COUNT(*) + 5) AS bayesian_quality
        FROM skills.agent_feedback
        WHERE prompt_id IS NOT NULL
          AND outcome != 'skipped'
        GROUP BY prompt_id;
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_pqp_prompt
        ON prompt_quality_prior (prompt_id);
    """)


def create_indexes(cursor) -> None:
    indexes = [
        # Active skill lookup by tag — the most common query pattern
        """CREATE INDEX IF NOT EXISTS idx_skills_tag_active
           ON skills.skills (tag, version DESC)
           WHERE status = 'active';""",

        # Taxonomy filtering for routing
        "CREATE INDEX IF NOT EXISTS idx_skills_domain    ON skills.skills USING GIN (domain);",
        "CREATE INDEX IF NOT EXISTS idx_skills_intent    ON skills.skills USING GIN (intent);",
        "CREATE INDEX IF NOT EXISTS idx_skills_task_type ON skills.skills USING GIN (task_type);",
        "CREATE INDEX IF NOT EXISTS idx_skills_status    ON skills.skills (status);",

        # Full-text search on the materialized search_tsv (name + summary +
        # taxonomy), same shape as idx_prompts_search_tsv.
        """CREATE INDEX IF NOT EXISTS idx_skills_search_tsv
           ON skills.skills USING GIN (search_tsv);""",

        # Semantic search on summary embedding
        """CREATE INDEX IF NOT EXISTS idx_skills_routing_embedding
           ON skills.skills USING hnsw (routing_embedding vector_cosine_ops)
           WITH (m = 16, ef_construction = 64);""",

        # Run history per skill
        """CREATE INDEX IF NOT EXISTS idx_skill_runs_skill
           ON skills.skill_runs (skill_id, started_at DESC);""",
    ]
    for sql in indexes:
        cursor.execute(sql)
    # Superseded by idx_skills_search_tsv (materialized column instead of an
    # on-the-fly to_tsvector() expression index).
    cursor.execute("DROP INDEX IF EXISTS skills.idx_skills_routing_fts;")


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

        print("  Creating skill_sessions table...")
        create_skill_sessions_table(cursor)

        print("  Creating agent_feedback table...")
        create_agent_feedback_table(cursor)

        print("  Creating materialized views...")
        create_materialized_views(cursor)

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
