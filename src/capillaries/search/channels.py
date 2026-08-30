"""
Two independent retrieval channels. No fusion, no weights, no shared ranking.

Each function answers the same question — "which prompts match this query?" —
by a completely different method, and each is scored on its own. Nothing here
combines them; that decision is deliberately deferred until there is enough
labelled data to make it on evidence.

    exact_search("budget_exhausted per episode")   # literal terms, unstemmed
    vector_search("help me decide between options") # meaning, embeddings

Both return the same shape, so they can be compared directly:
    [Hit(prompt_id, title, score, chunk_id, matched), ...]

Run either from the CLI:
    python3 -m capillaries.search.channels exact  "serve.py"
    python3 -m capillaries.search.channels vector "help me think through a decision"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import psycopg2
import psycopg2.extras

from capillaries.config import DB_CONFIG

CANDIDATES = 50          # chunks pulled before rolling up to parents
TOP_K = 10               # parents returned


@dataclass
class Hit:
    prompt_id: str
    title: str
    score: float
    chunk_id: str        # the specific chunk that matched best
    matched: list[str] = field(default_factory=list)   # exact: which terms hit

    def __repr__(self) -> str:
        m = f" {self.matched}" if self.matched else ""
        return f"{self.score:.4f}  {self.title[:48]}{m}"


# --- Exact channel -------------------------------------------------------

# Function words carry no term-identity, and AND-ing them guarantees zero
# results on any natural-language query. Not a stemmer or a stopword *list* in
# the linguistic sense — just the tokens that would sink an AND query.
_NOISE = frozenset("""
a an the and or but if then else of in on at to for from with without by as is
are was were be been being do does did have has had can could should would will
my me i you your it its this that these those there here what how why when
""".split())

_TOKEN = re.compile(r"[A-Za-z0-9_][\w./-]*")


def exact_terms(query: str) -> list[str]:
    """Literal search terms: everything that isn't a function word.

    Case is folded but nothing is stemmed — `exact_tsv` is built with the
    'simple' configuration precisely so `snake_case`, `--flags`, `serve.py`
    and `L-6-v2` survive as lexemes instead of being stemmed into something a
    query can no longer name.
    """
    return [t.lower() for t in _TOKEN.findall(query)
            if t.lower() not in _NOISE and len(t) > 1]


# DF is counted over PROMPTS, not chunks. Chunk-level DF understates document
# frequency (a term in one chunk of a five-chunk prompt counts 1/2072 instead
# of 1/916) — measured: decision 18.6% of chunks vs 25.0% of prompts, budget
# 8.0% vs 11.2%. Threshold set at document scale accordingly.
#
# Generic on this corpus: decision 25.0%, make/next/plan/help/review 15-20%.
# Discriminative: budget 11.2%, financial 10.5%, quarter 6.9%, cash 3.1%.
MAX_DF = 0.15
MAX_TERMS = 4          # the rarest few carry the query; more only adds noise


def key_terms(query: str, db_config: dict | None = None) -> list[tuple[str, float]]:
    """The discriminative terms in a query, rarest first, with their DF.

    This is the step that makes keyword search usable on a natural-language
    query. "help me make a financial plan for next quarter" AND-ed whole
    matches nothing — but the query is really *about* `financial` and
    `quarter`, and those are exactly the terms the corpus says are rare.
    Frequency does the work a hand-written stopword list can't: it adapts to
    whatever this particular vault happens to talk about constantly.

    Returns [] when every term is common, which correctly means "this query has
    no keyword handle — use the vector channel".
    """
    candidates = exact_terms(query)
    if not candidates:
        return []

    conn = psycopg2.connect(**(db_config or DB_CONFIG))
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM prompts WHERE status = 'active'")
            total = cur.fetchone()[0] or 1
            out: list[tuple[str, float]] = []
            for t in dict.fromkeys(candidates):     # dedupe, keep order
                try:
                    cur.execute(
                        "SELECT count(*) FROM prompts "
                        "WHERE exact_tsv @@ to_tsquery('simple', %s)",
                        (f"'{t}'",),
                    )
                    df = cur.fetchone()[0] / total
                except psycopg2.errors.SyntaxError:
                    conn.rollback()
                    continue
                if 0 < df <= MAX_DF:
                    out.append((t, df))
    finally:
        conn.close()

    out.sort(key=lambda x: x[1])            # rarest first
    return out[:MAX_TERMS]


def keyword_search(
    query: str,
    top_k: int = TOP_K,
    db_config: dict | None = None,
    filters: dict | None = None,
) -> list[Hit]:
    """Keyword search over the extracted key terms, relaxing until it matches.

    Three tiers, strictest first. The tier that fired is reported in
    Hit.matched, because "matched all four rare terms" and "matched any one of
    them" are very different claims and the caller should be able to tell.
    """
    terms = key_terms(query, db_config)
    if not terms:
        return []

    words = [t for t, _ in terms]
    tiers = [
        (" & ".join(f"'{w}'" for w in words), "all"),
        (" & ".join(f"'{w}'" for w in words[:2]), "top2"),
        (" | ".join(f"'{w}'" for w in words), "any"),
    ]

    for tsquery, tier in tiers:
        hits = _run_tsquery(tsquery, top_k, [f"{tier}:{','.join(words)}"], db_config, filters)
        if hits:
            return hits
    return []


def _filter_sql(filters: dict | None) -> tuple[str, list]:
    """Metadata prefilter, reusing the retriever's clause builder.

    Filters express *eligibility* and stay a hard WHERE, never a score boost —
    an inactive or out-of-domain prompt with a great score is still ineligible.
    """
    from capillaries.search.retriever import _build_filter_clause
    # Qualified: both queries below join prompts as `p`, and prompt_chunks now
    # has a status column of its own, so a bare `status` is ambiguous.
    clause, params = _build_filter_clause(filters or {}, alias="p.")
    return clause, params


def _run_tsquery(tsquery, top_k, matched, db_config, filters=None) -> list[Hit]:
    """Match at DOCUMENT level, not chunk level.

    Chunking is right for embeddings and wrong for keywords. Measured on the
    golden-set queries: document-level AND finds 77 prompts, chunk-level AND
    finds 50 — chunking discards 35% of legitimate matches, because a query's
    terms are genuinely present in the prompt but land in different sections
    (`financial` in the role block, `model` in the output spec). A keyword
    doesn't dilute across a long document the way an embedding does, so there
    is nothing to gain by splitting and a third of the recall to lose.
    """
    clause, fparams = _filter_sql(filters)
    sql = f"""
        SELECT ''::text AS chunk_id, p.prompt_id::text, p.title,
               ts_rank_cd(p.exact_tsv, to_tsquery('simple', %s), 1|4|32) AS score
        FROM prompts p
        WHERE p.exact_tsv @@ to_tsquery('simple', %s)
          AND {clause}
        ORDER BY score DESC
        LIMIT %s
    """
    conn = psycopg2.connect(**(db_config or DB_CONFIG))
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(sql, [tsquery, tsquery] + fparams + [CANDIDATES])
                rows = cur.fetchall()
            except psycopg2.errors.SyntaxError:
                return []
    finally:
        conn.close()
    return _rollup([(r[0], r[1], r[2], float(r[3])) for r in rows], top_k, matched)


def exact_search(
    query: str,
    top_k: int = TOP_K,
    require_all: bool = True,
    db_config: dict | None = None,
    filters: dict | None = None,
) -> list[Hit]:
    """Chunks containing the query's literal terms.

    require_all=True ANDs the terms, which is what makes this *exact*: a hit
    contains every term the user typed. It returns nothing rather than
    something approximate, and that is the intended behaviour — this channel
    is meant to be silent when it cannot help.
    """
    terms = exact_terms(query)
    if not terms:
        return []

    op = " & " if require_all else " | "
    tsquery = op.join(f"'{t}'" for t in terms)
    return _run_tsquery(tsquery, top_k, terms, db_config, filters)


# --- Vector channel ------------------------------------------------------

def vector_search(
    query: str,
    top_k: int = TOP_K,
    db_config: dict | None = None,
    filters: dict | None = None,
) -> list[Hit]:
    """Chunks closest to the query in embedding space.

    Shares no code path with exact_search on purpose — the point is to measure
    each independently, so neither can quietly prop the other up.
    """
    import httpx

    from capillaries.config import EMBED_MODEL, EMBED_URL, QUERY_PREFIX

    resp = httpx.post(
        EMBED_URL,
        json={"input": QUERY_PREFIX + query, "model": EMBED_MODEL},
        timeout=30.0,
    )
    resp.raise_for_status()
    vec = "[" + ",".join(map(str, resp.json()["data"][0]["embedding"])) + "]"

    clause, fparams = _filter_sql(filters)
    sql = f"""
        SELECT c.chunk_id::text, c.prompt_id::text, p.title,
               1 - (c.embedding <=> %s::halfvec) AS score
        FROM prompt_chunks c
        JOIN prompts p USING (prompt_id)
        -- c.status is what makes the partial chunk index usable; the p.*
        -- clause still carries taxonomy, and its own status check is a cheap
        -- backstop if the sync trigger ever lags.
        WHERE c.embedding IS NOT NULL AND c.status = 'active' AND {clause}
        ORDER BY c.embedding <=> %s::halfvec
        LIMIT %s
    """
    conn = psycopg2.connect(**(db_config or DB_CONFIG))
    try:
        with conn.cursor() as cur:
            # ef_search is left at its default: the iterative scan continues
            # the walk until CANDIDATES is met, which is what the old
            # `max(2 * CANDIDATES, 100)` was guessing at.
            cur.execute("SET LOCAL hnsw.iterative_scan = 'relaxed_order'")
            cur.execute(sql, [vec] + fparams + [vec, CANDIDATES])
            rows = cur.fetchall()
    finally:
        conn.close()

    return _rollup([(r[0], r[1], r[2], float(r[3])) for r in rows], top_k, [])


# --- Shared plumbing (not shared ranking) --------------------------------

def _rollup(rows, top_k: int, matched: list[str]) -> list[Hit]:
    """Chunks -> parents, best chunk wins.

    Max rather than mean: one strongly matching section is a real match, and
    averaging would penalise long prompts for having other sections.
    """
    best: dict[str, Hit] = {}
    for chunk_id, prompt_id, title, score in rows:
        cur = best.get(prompt_id)
        if cur is None or score > cur.score:
            best[prompt_id] = Hit(prompt_id, title, score, chunk_id, matched)
    return sorted(best.values(), key=lambda h: (-h.score, h.prompt_id))[:top_k]


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)

    mode, q = sys.argv[1], " ".join(sys.argv[2:])
    hits = exact_search(q) if mode == "exact" else vector_search(q)
    if mode == "exact":
        print(f"terms: {exact_terms(q)}")
    print(f"{len(hits)} hits")
    for h in hits:
        print("  ", h)
