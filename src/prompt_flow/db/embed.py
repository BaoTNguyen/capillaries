"""
Generate and store pgvector embeddings for all prompts using Ollama.

Usage:
    python -m prompt_flow.db.embed              # embed all missing
    python -m prompt_flow.db.embed --reembed    # reembed everything
"""

import argparse
import asyncio
import sys
import time

import httpx
import psycopg2
import psycopg2.extras

from prompt_flow.config import DB_CONFIG

OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768
BATCH_SIZE = 32  # prompts per batch (embedding is fast, batch larger than classify)
CONCURRENCY = 4  # parallel Ollama requests
# nomic-embed-text context is 8192 tokens. Some content tokenizes densely
# (code, symbols, non-ASCII), so cap conservatively at ~4k chars ≈ 2k-4k tokens.
MAX_CHARS = 4_000


async def get_embedding(client: httpx.AsyncClient, text: str, prefix: str = "search_document: ") -> list[float]:
    """Return embedding vector for text.

    nomic-embed-text is asymmetric: documents should be prefixed with
    'search_document: ' and queries with 'search_query: ' for best retrieval quality.
    Text is truncated to MAX_CHARS before prefixing to stay within context limits.
    """
    resp = await client.post(
        OLLAMA_EMBED_URL,
        json={"model": EMBED_MODEL, "prompt": prefix + text[:MAX_CHARS]},
        timeout=60.0,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Ollama error {resp.status_code}: {resp.text[:200]}")
    return resp.json()["embedding"]


async def embed_batch(
    client: httpx.AsyncClient,
    rows: list[tuple[str, str]],
    sem: asyncio.Semaphore,
) -> list[tuple[str, list[float]]]:
    """Embed a batch of (prompt_id, text) rows concurrently."""

    async def _one(prompt_id: str, text: str) -> tuple[str, list[float]]:
        async with sem:
            vec = await get_embedding(client, text)
            return prompt_id, vec

    return await asyncio.gather(*[_one(pid, txt) for pid, txt in rows])


async def run(reembed: bool = False) -> None:
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    if reembed:
        cur.execute(
            "SELECT prompt_id, prompt_text FROM prompts "
            "WHERE length(trim(prompt_text)) > 0 ORDER BY prompt_id"
        )
    else:
        cur.execute(
            "SELECT prompt_id, prompt_text FROM prompts "
            "WHERE embedding IS NULL AND length(trim(prompt_text)) > 0 ORDER BY prompt_id"
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
                WHERE prompt_id = %s
                """,
                [(str(vec), EMBED_MODEL, pid) for pid, vec in results],
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

    # Build HNSW index — better recall than IVFFlat at this scale
    # m=16: connections per node (higher = better recall, more memory)
    # ef_construction=64: search width during build (higher = better quality, slower build)
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reembed",
        action="store_true",
        help="Reembed all prompts, not just those missing embeddings",
    )
    args = parser.parse_args()
    asyncio.run(run(reembed=args.reembed))
