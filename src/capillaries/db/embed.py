"""
Generate and store pgvector embeddings for all prompts.

Calls the embedding server (scripts/serve_embeddings.py) which serves
snowflake-arctic-embed-m-v2.0 via an OpenAI-compatible /v1/embeddings endpoint.

Usage:
    python -m capillaries.db.embed              # embed all missing
    python -m capillaries.db.embed --reembed    # reembed everything
"""

import argparse
import asyncio
import sys
import time

import httpx
import psycopg2
import psycopg2.extras

from capillaries.config import DB_CONFIG, EMBED_URL, EMBED_MODEL
from capillaries.search.retriever import expand_acronyms

EMBED_DIM = 768
BATCH_SIZE = 32
CONCURRENCY = 4
MAX_CHARS = 4_000


async def get_embedding(client: httpx.AsyncClient, text: str, title: str | None = None) -> list[float]:
    """Return embedding vector for document text.

    snowflake-arctic-embed-m-v2.0 does not need a document prefix —
    only queries use an instruction prefix (handled in retriever.py / gate.py).
    When title is provided, it's prepended to anchor template-heavy prompts
    to their functional topic.
    """
    embed_text = f"{title}\n\n{text}" if title else text
    resp = await client.post(
        EMBED_URL,
        json={"input": expand_acronyms(embed_text)[:MAX_CHARS], "model": EMBED_MODEL},
        timeout=60.0,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Embed error {resp.status_code}: {resp.text[:200]}")
    return resp.json()["data"][0]["embedding"]


async def embed_batch(
    client: httpx.AsyncClient,
    rows: list[tuple[str, str]],
    sem: asyncio.Semaphore,
) -> list[tuple[str, list[float]]]:
    """Embed a batch of (title, text) rows concurrently."""

    async def _one(title: str, text: str) -> tuple[str, list[float]]:
        async with sem:
            vec = await get_embedding(client, text, title=title)
            return title, vec

    return await asyncio.gather(*[_one(t, txt) for t, txt in rows])


async def run(reembed: bool = False) -> None:
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    if reembed:
        cur.execute(
            "SELECT title, prompt_text FROM prompts "
            "WHERE length(trim(prompt_text)) > 0 ORDER BY title"
        )
    else:
        cur.execute(
            "SELECT title, prompt_text FROM prompts "
            "WHERE embedding IS NULL AND length(trim(prompt_text)) > 0 ORDER BY title"
        )

    rows = cur.fetchall()
    total = len(rows)

    if total == 0:
        print("All prompts already have embeddings.")
        cur.close()
        conn.close()
        return

    print(f"Embedding {total} prompts with {EMBED_MODEL}...")
    t0 = time.time()
    done = 0

    sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient() as client:
        for i in range(0, total, BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            results = await embed_batch(client, batch, sem)

            # Bulk update
            psycopg2.extras.execute_batch(
                cur,
                """
                UPDATE prompts
                SET embedding = %s::vector,
                    embedding_version = %s
                WHERE title = %s
                """,
                [(str(vec), EMBED_MODEL, title) for title, vec in results],
            )
            conn.commit()

            done += len(batch)
            elapsed = time.time() - t0
            rate = done / elapsed
            remaining = (total - done) / rate if rate > 0 else 0
            print(
                f"  {done}/{total}  ({rate:.1f}/s)  ~{remaining:.0f}s remaining",
                end="\r",
            )

    print(f"\nDone. Embedded {done} prompts in {time.time() - t0:.1f}s.")

    print("Building HNSW index (m=16, ef_construction=64)...")
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_prompts_embedding
        ON prompts USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )
    conn.commit()
    print("Index built.")

    cur.close()
    conn.close()


async def run_skills(reembed: bool = False) -> None:
    """Embed skill routing_descriptions into skills.skills.routing_embedding."""
    conn = psycopg2.connect(**DB_CONFIG)

    cur = conn.cursor()
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'skills' AND table_name = 'skills'
                AND column_name = 'routing_embedding'
            ) THEN
                ALTER TABLE skills.skills ADD COLUMN routing_embedding VECTOR(768);
            END IF;
        END $$;
    """)
    conn.commit()
    cur.close()
    conn.autocommit = False
    cur = conn.cursor()

    if reembed:
        cur.execute(
            "SELECT skill_id::text, routing_description FROM skills.skills "
            "WHERE status = 'active' AND length(trim(routing_description)) > 0"
        )
    else:
        cur.execute(
            "SELECT skill_id::text, routing_description FROM skills.skills "
            "WHERE status = 'active' AND routing_embedding IS NULL "
            "AND length(trim(routing_description)) > 0"
        )

    rows = cur.fetchall()
    total = len(rows)

    if total == 0:
        print("All active skills already have embeddings.")
        cur.close()
        conn.close()
        return

    print(f"Embedding {total} skill routing_descriptions with {EMBED_MODEL}...")
    t0 = time.time()

    sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient() as client:
        results = await embed_batch(client, rows, sem)

        psycopg2.extras.execute_batch(
            cur,
            """
            UPDATE skills.skills
            SET routing_embedding = %s::vector
            WHERE skill_id = %s::uuid
            """,
            [(str(vec), pid) for pid, vec in results],
        )
        conn.commit()

    print(f"Done. Embedded {total} skills in {time.time() - t0:.1f}s.")

    print("Building skills HNSW index...")
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_skills_routing_embedding
        ON skills.skills USING hnsw (routing_embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )
    conn.commit()
    print("Skills index built.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reembed",
        action="store_true",
        help="Reembed all prompts (and skills), not just those missing embeddings",
    )
    parser.add_argument(
        "--skills-only",
        action="store_true",
        help="Only embed skill routing_descriptions, skip prompts",
    )
    args = parser.parse_args()

    if args.skills_only:
        asyncio.run(run_skills(reembed=args.reembed))
    else:
        asyncio.run(run(reembed=args.reembed))
        asyncio.run(run_skills(reembed=args.reembed))
