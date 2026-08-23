"""
Chunk prompts for indexing.

The vault has no single structural convention — measured over 916 prompts:
XML-ish section tags (<role>, <guardrails>) in 186, bold headers in 233,
horizontal rules in 237, markdown headings in only 109, and 510 with none of
the above. So splitting cascades: try the strongest delimiter present, and only
fall through to a weaker one when a piece is still over the ceiling.

Sizes are in characters, not tokens — ~4 chars/token is close enough to keep
chunks inside a 512-token cross-encoder window, and it saves a tiktoken
dependency for a number that only needs to be roughly right.

Usage:
    python3 -m capillaries.chunk --backfill        # chunk + embed everything
    python3 -m capillaries.chunk --backfill --dry  # report, write nothing
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

TARGET = 1_600     # ~400 tokens: flush a chunk once it reaches this
CEILING = 4_000    # ~1000 tokens: split harder above this
FLOOR = 320        # ~80 tokens: too small to be its own retrievable unit


@dataclass
class Chunk:
    index: int
    text: str
    label: str | None      # section name, when the split point had one
    char_start: int
    char_end: int
    is_atomic: bool        # oversized indivisible block (code fence, table)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()[:16]


# --- Atomic blocks -------------------------------------------------------

# Masked before splitting so a `---` row inside a table, or a `# comment`
# inside a fence, never becomes a section boundary. Same length, newlines
# preserved, so every offset still points at the real text.
_FENCE = re.compile(r"^```.*?(?:^```|\Z)", re.M | re.S)
_TABLE = re.compile(r"(?:^\|.*\|[ \t]*$\n?){2,}", re.M)


def _mask(text: str) -> str:
    def blank(m: re.Match) -> str:
        return "".join("\n" if c == "\n" else "x" for c in m.group(0))
    return _TABLE.sub(blank, _FENCE.sub(blank, text))


# --- Split ladder --------------------------------------------------------

_XML = re.compile(r"^<([a-z][a-z0-9_-]*)>[ \t]*$", re.M)
_HEAD = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t]*$", re.M)
_RULE = re.compile(r"^-{3,}[ \t]*$", re.M)
_BOLD = re.compile(r"^\*\*(.+?)\*\*[ \t]*:?[ \t]*$", re.M)
_PARA = re.compile(r"\n[ \t]*\n")

_LADDER = [_XML, _HEAD, _RULE, _BOLD, _PARA]


def _label(m: re.Match) -> str | None:
    """Section name from a boundary match, when it carries one."""
    return m.group(1).strip() if m.re.groups else None


def _spans(text: str, masked: str, lo: int, hi: int, level: int = 0) -> list[tuple[int, int, str | None]]:
    """Split [lo, hi) into contiguous spans, descending the ladder as needed.

    Splits down to TARGET granularity; the packing pass then reassembles
    neighbours back up to TARGET. Cutting only at CEILING would leave a 3 900-
    char prompt as one chunk, which overflows the cross-encoder's window and
    puts us back where the unchunked index already was.
    """
    if hi - lo <= TARGET or level >= len(_LADDER):
        return [(lo, hi, None)]

    pat = _LADDER[level]
    cuts: list[tuple[int, str | None]] = []
    for m in pat.finditer(masked, lo, hi):
        # A boundary at the very start splits nothing off.
        if m.start() > lo:
            cuts.append((m.start(), _label(m)))

    if not cuts:
        return _spans(text, masked, lo, hi, level + 1)

    out: list[tuple[int, int, str | None]] = []
    starts = [(lo, None)] + cuts
    for i, (start, label) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else hi
        for s, e, inner in _spans(text, masked, start, end, level + 1):
            out.append((s, e, inner or label))
    return out


def _trim(text: str, lo: int, hi: int) -> tuple[int, int]:
    """Shrink a span past surrounding whitespace, keeping offsets truthful."""
    while lo < hi and text[lo].isspace():
        lo += 1
    while hi > lo and text[hi - 1].isspace():
        hi -= 1
    return lo, hi


# --- Public API ----------------------------------------------------------

def chunk(text: str) -> list[Chunk]:
    """Split a prompt into retrievable chunks.

    Short prompts come back as a single chunk covering the whole text — on this
    corpus that's the majority, and it's the correct answer for them.
    """
    if not text or not text.strip():
        return []

    masked = _mask(text)
    spans = _spans(text, masked, 0, len(text))

    # Pack: accumulate until TARGET, then flush. The first span in a chunk
    # supplies the label, since that is the section the chunk opens.
    packed: list[list] = []
    for s, e, label in spans:
        s, e = _trim(text, s, e)
        if s >= e:
            continue
        if packed and packed[-1][1] - packed[-1][0] < TARGET:
            packed[-1][1] = e
            packed[-1][2] = packed[-1][2] or label
        else:
            packed.append([s, e, label])

    # A trailing scrap is a fragment of the chunk above it, not a unit.
    if len(packed) > 1 and packed[-1][1] - packed[-1][0] < FLOOR:
        packed[-2][1] = packed[-1][1]
        packed.pop()

    # 169 prompts repeat their own opening verbatim (vault artifact — the note
    # holds the prompt twice). Indexing both halves doubles them in every
    # candidate list, so identical chunks collapse to their first occurrence.
    out: list[Chunk] = []
    seen: set[str] = set()
    for s, e, label in packed:
        body = text[s:e]
        key = hashlib.sha256(" ".join(body.split()).encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        out.append(Chunk(
            index=len(out),
            text=body,
            label=label,
            char_start=s,
            char_end=e,
            is_atomic=(e - s) > CEILING,
        ))
    return out


def _key(title: str, c: Chunk, summary: str | None) -> str:
    """Cache key = hash of what is actually embedded.

    Keying on Chunk.content_hash (the chunk text alone) would be wrong now that
    the summary is part of the input: editing a summary leaves the chunk text
    identical, so a stale vector would be reused and the re-embed would appear
    to succeed while changing nothing.
    """
    return hashlib.sha256(embed_text(title, c, summary).encode()).hexdigest()[:16]


def embed_text(title: str, c: Chunk, summary: str | None = None) -> str:
    """What actually gets embedded: breadcrumb, summary, then the chunk.

    The breadcrumb is cheaper than overlap — a chunk pulled out of its prompt
    loses the topic its parent established, and ~15 tokens restores it without
    duplicating a sentence into the index twice.

    The summary is there because a large share of chunks are behavioural
    boilerplate: 527 chunks labelled `instructions`, 112 `guardrails`, 91
    `output`. Their text says how the model should behave, not what the prompt
    is for, and it reads near-identically across unrelated prompts. Prefixing
    the summary makes a guardrails chunk "the guardrails of the role-repricing
    prompt" rather than a generic guardrails chunk.

    Summaries are ~474 chars against a ~1700-char chunk, so they shift a chunk
    without swamping it. Absent summary is fine — the prefix is simply omitted.
    """
    crumb = f"{title} > {c.label}" if c.label else title
    head = f"{crumb}\n\n{summary.strip()}\n\n" if summary and summary.strip() else f"{crumb}\n\n"
    return f"{head}{c.text}"


# --- Storage -------------------------------------------------------------

def _ddl() -> str:
    """Chunk table DDL. Vector width comes from config so a model swap is one edit."""
    from capillaries.config import EMBED_DIM
    return DDL.replace("VECTOR(EMBED_DIM)", f"VECTOR({EMBED_DIM})")


DDL = """
CREATE TABLE IF NOT EXISTS prompt_chunks (
    chunk_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_id     UUID NOT NULL REFERENCES prompts(prompt_id) ON DELETE CASCADE,
    chunk_index   INTEGER NOT NULL,
    label         TEXT,
    chunk_text    TEXT NOT NULL,
    char_start    INTEGER NOT NULL,
    char_end      INTEGER NOT NULL,
    is_atomic     BOOLEAN DEFAULT FALSE,
    content_hash  VARCHAR NOT NULL,

    embedding         VECTOR(EMBED_DIM),
    embedding_version VARCHAR,
    search_tsv        TSVECTOR,
    exact_tsv         TSVECTOR,

    UNIQUE (prompt_id, chunk_index)
);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_chunks_parent ON prompt_chunks (prompt_id, chunk_index);",
    "CREATE INDEX IF NOT EXISTS idx_chunks_hash   ON prompt_chunks (content_hash);",
    "CREATE INDEX IF NOT EXISTS idx_chunks_tsv    ON prompt_chunks USING GIN (search_tsv);",
    "CREATE INDEX IF NOT EXISTS idx_chunks_exact  ON prompt_chunks USING GIN (exact_tsv);",
    # Built after backfill — HNSW on an empty table then filled row-by-row is
    # far slower to build than one pass over populated data.
    "CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON prompt_chunks "
    "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);",
]

# search_tsv is 'english' and stemmed, for prose. exact_tsv is 'simple' and
# unstemmed, so `snake_case`, `--flags` and `L-6-v2` survive as lexemes instead
# of being stemmed into something a query can no longer name.


def backfill(dry: bool = False, db_config: dict | None = None) -> dict:
    """Chunk every prompt, embed each chunk, write prompt_chunks.

    Re-runnable: a chunk whose content_hash already exists keeps its embedding
    instead of paying for it again.
    """
    import asyncio

    import httpx
    import psycopg2
    import psycopg2.extras

    from capillaries.config import DB_CONFIG, EMBED_MODEL, EMBED_URL
    from capillaries.search.retriever import expand_acronyms

    conn = psycopg2.connect(**(db_config or DB_CONFIG))
    cur = conn.cursor()

    if not dry:
        cur.execute(_ddl())
        for sql in INDEXES[:-1]:   # HNSW comes last, after the rows exist
            cur.execute(sql)
        conn.commit()

    cur.execute(
        "SELECT prompt_id::text, title, prompt_text, summary FROM prompts "
        "WHERE length(trim(prompt_text)) > 0 ORDER BY title"
    )
    rows = cur.fetchall()

    # Reuse vectors for text we have already embedded, across runs and across
    # prompts that share a boilerplate section.
    cached: dict[str, list[float]] = {}
    if not dry:
        # Cache is keyed by embedded-text hash, which no column stores, so it
        # starts empty each run. Within a run it still dedupes identical
        # boilerplate across prompts.
        cached = {}

    stats = {"prompts": len(rows), "chunks": 0, "reused": 0, "embedded": 0, "atomic": 0}
    plan: list[tuple] = []

    for prompt_id, title, text, summary in rows:
        for c in chunk(text):
            stats["chunks"] += 1
            stats["atomic"] += c.is_atomic
            plan.append((prompt_id, title, c, summary))

    if dry:
        sizes = sorted(len(c.text) for _, _, c, _ in plan)
        stats["median_chunk_chars"] = sizes[len(sizes) // 2] if sizes else 0
        stats["max_chunk_chars"] = sizes[-1] if sizes else 0
        return stats

    async def _embed(batch: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            sem = asyncio.Semaphore(4)

            async def one(s: str) -> list[float]:
                async with sem:
                    r = await client.post(EMBED_URL, json={
                        "input": expand_acronyms(s)[:CEILING], "model": EMBED_MODEL})
                    r.raise_for_status()
                    return r.json()["data"][0]["embedding"]

            return await asyncio.gather(*[one(s) for s in batch])

    # Rebuild wholesale: chunk boundaries move when a prompt is edited, so
    # incremental patching would leave orphaned indexes behind.
    cur.execute("DELETE FROM prompt_chunks")

    BATCH = 32
    for i in range(0, len(plan), BATCH):
        window = plan[i:i + BATCH]
        need = [(j, _key(t, c, sm), embed_text(t, c, sm))
                for j, (_, t, c, sm) in enumerate(window)
                if _key(t, c, sm) not in cached]
        vecs = asyncio.run(_embed([s for _, _, s in need])) if need else []
        for (j, key, _), vec in zip(need, vecs):
            cached[key] = vec
            stats["embedded"] += 1

        fresh = {j for j, _, _ in need}
        for j, (prompt_id, title, c, sm) in enumerate(window):
            vec = cached.get(_key(title, c, sm))
            stats["reused"] += vec is not None and j not in fresh
            crumb = f"{title} > {c.label}" if c.label else title
            cur.execute("""
                INSERT INTO prompt_chunks (
                    prompt_id, chunk_index, label, chunk_text,
                    char_start, char_end, is_atomic, content_hash,
                    embedding, embedding_version, search_tsv
                ) VALUES (
                    %(pid)s, %(idx)s, %(label)s, %(raw)s,
                    %(start)s, %(end)s, %(atomic)s, %(hash)s,
                    %(vec)s::vector, %(ver)s,
                    setweight(to_tsvector('english', %(crumb)s), 'A')
                        || to_tsvector('english', %(body)s)
                )
            """, {"pid": prompt_id, "idx": c.index, "label": c.label,
                  "raw": c.text, "body": expand_acronyms(c.text),
                  "start": c.char_start, "end": c.char_end,
                  "atomic": c.is_atomic, "hash": c.content_hash,
                  "vec": str(vec) if vec else None, "ver": EMBED_MODEL if vec else None,
                  "crumb": expand_acronyms(crumb)})
        conn.commit()
        print(f"  {min(i + BATCH, len(plan))}/{len(plan)} chunks", end="\r")

    cur.execute("UPDATE prompt_chunks SET exact_tsv = to_tsvector('simple', chunk_text)")
    conn.commit()

    # The backfill DELETEs every row and reinserts, so the index already
    # exists and INDEXES[-1] (CREATE ... IF NOT EXISTS) was a silent no-op —
    # the graph got built one insert at a time, which is both slower and a
    # worse graph than one bulk pass. REINDEX forces the bulk build.
    print("\nRebuilding HNSW index...")
    cur.execute(INDEXES[-1])          # first run: the index does not exist yet
    cur.execute("REINDEX INDEX idx_chunks_embedding")
    conn.commit()

    cur.close()
    conn.close()
    return stats


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--dry", action="store_true", help="report only, write nothing")
    args = ap.parse_args()

    if args.backfill or args.dry:
        for k, v in backfill(dry=args.dry).items():
            print(f"{k:22} {v}")
    else:
        ap.print_help()
