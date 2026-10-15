"""
Score each retrieval channel on its own. No fusion anywhere.

Benchmarks, and what each is worth:

  notes    (n=261)  A prompt's `notes` field as the query, its own prompt_id as
                    the label. Verified held-out: 0 of 970 chunks match their
                    own notes, and `notes` appears in no chunk_text, neither
                    tsvector, and nothing embedded. **The only clean labelled
                    benchmark in the repo.**

  golden   (n=20)   Hand-written in tests/test_search.py. Real, but small and
                    lexically loaded — its queries share words with the titles
                    they expect, which flatters exact search.

  title    (n=300)  A prompt's own title as the query. **CONTAMINATED — do not
                    use for decisions.** chunk.py writes the title into every
                    chunk's breadcrumb, so it lands in search_tsv at weight A
                    and in the embedded text (verified 2072/2072). Reported
                    only to show how large the leak is.

Usage:
    python3 -m capillaries.search.bench_channels
    python3 -m capillaries.search.bench_channels --bench notes
"""

from __future__ import annotations

import argparse
import statistics as st
import sys
from pathlib import Path

import psycopg2

from capillaries.config import DB_CONFIG
from capillaries.search.channels import exact_search, keyword_search, vector_search


def _load(bench: str) -> list[tuple[str, str]]:
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            if bench == "notes":
                cur.execute("SELECT prompt_id::text, notes FROM prompts "
                            "WHERE notes IS NOT NULL AND length(trim(notes)) > 40")
                return cur.fetchall()
            if bench == "title":
                cur.execute("SELECT prompt_id::text, title FROM prompts "
                            "ORDER BY md5(title) LIMIT 300")
                return cur.fetchall()
            if bench == "golden":
                sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tests"))
                # lazy: tests/ only joins sys.path on the line above, so this cannot be hoisted
                from test_search import GOLDEN_SET  # noqa: E402
                out = []
                for query, expected, _k, _label in GOLDEN_SET:
                    cur.execute("SELECT prompt_id::text FROM prompts "
                                "WHERE title ILIKE %s LIMIT 1", (f"%{expected}%",))
                    row = cur.fetchone()
                    if row:
                        out.append((row[0], query))
                return out
    finally:
        conn.close()
    raise ValueError(bench)


def score(fn, pop: list[tuple[str, str]]) -> dict:
    """recall@1/5/10, MRR@10, and how often the channel returns nothing."""
    r1 = r5 = r10 = empty = 0
    rr: list[float] = []
    for gold, query in pop:
        hits = fn(query, top_k=10)
        if not hits:
            empty += 1
            rr.append(0.0)
            continue
        ids = [h.prompt_id for h in hits]
        rank = ids.index(gold) + 1 if gold in ids else None
        r1 += rank == 1
        r5 += bool(rank and rank <= 5)
        r10 += bool(rank)
        rr.append(1.0 / rank if rank else 0.0)
    n = len(pop)
    return {"n": n, "R@1": r1 / n, "R@5": r5 / n, "R@10": r10 / n,
            "MRR": st.mean(rr), "empty": empty / n}


def overlap(pop: list[tuple[str, str]], k: int = 10) -> dict:
    """How much do the two channels agree on the answers they get right?

    'best pick' is an ORACLE: it counts a query as solved if *either* channel
    found the answer. No system can do this without knowing the answer already
    — it is the ceiling any router or fusion could reach, not a result.
    """
    v_only = l_only = both = neither = 0
    for gold, query in pop:
        v = gold in [h.prompt_id for h in vector_search(query, top_k=k)]
        l = gold in [h.prompt_id for h in keyword_search(query, top_k=k)]
        both += v and l
        v_only += v and not l
        l_only += l and not v
        neither += not v and not l
    n = len(pop)
    return {"n": n, "both": both / n, "vector_only": v_only / n,
            "lexical_only": l_only / n, "neither": neither / n,
            "oracle": (both + v_only + l_only) / n}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", default="all",
                    choices=["all", "notes", "golden", "title"])
    args = ap.parse_args()

    benches = ["notes", "golden", "title"] if args.bench == "all" else [args.bench]
    warn = {"title": "  CONTAMINATED — title is indexed at weight A; ignore for decisions",
            "golden": "  small (n=20) and lexically loaded",
            "notes": "  clean, held-out"}

    for b in benches:
        pop = _load(b)
        print(f"\n=== {b} (n={len(pop)}){warn[b]}")
        print(f"{'channel':20} {'R@1':>7} {'R@5':>7} {'R@10':>7} {'MRR':>7} {'empty':>7}")
        for name, fn in [("exact (AND)", exact_search),
                         ("keyword (key terms)", keyword_search),
                         ("vector", vector_search)]:
            s = score(fn, pop)
            print(f"{name:20} {s['R@1']:>6.1%} {s['R@5']:>7.1%} {s['R@10']:>7.1%} "
                  f"{s['MRR']:>7.3f} {s['empty']:>7.1%}")

        o = overlap(pop)
        print(f"  overlap @10 — both {o['both']:.1%} | vector only {o['vector_only']:.1%} | "
              f"lexical only {o['lexical_only']:.1%} | neither {o['neither']:.1%}")
        print(f"  ORACLE best-pick (upper bound, needs the answer): {o['oracle']:.1%}")


if __name__ == "__main__":
    main()
