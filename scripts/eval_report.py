"""
Generate a human-readable evaluation report.

For each query, generates all candidate response chains — single-prompt and
multi-step — ranks them by mean rerank score, and shows the best N.

A "chain" is any complete recommendation: could be one great prompt, a
plan→execute pair, or a full clarify→plan→execute→verify→reflect workflow.
They all compete on the same ranked list so you can compare approaches.

Usage:
    python scripts/eval_report.py                        # default queries, top 5
    python scripts/eval_report.py --top-k 3              # fewer chains per query
    python scripts/eval_report.py --out report.txt       # custom output path
    python scripts/eval_report.py --query "your query"   # single query
"""

from __future__ import annotations

import argparse
import asyncio
import textwrap
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from prompt_flow.search.api import PromptSearch

SEPARATOR = "=" * 80

STAGES = ["clarify", "plan", "execute", "verify", "reflect"]

# Scores below this are flagged as weak matches, but never excluded.
WEAK_MATCH_THRESHOLD = -3.0

QUERIES = [
    # Simple / single-intent
    ("write a product requirements document for a new feature", {}),
    ("build a 13-week cash flow model", {}),
    ("analyze customer churn", {"domain": ["business"]}),
    ("write a go-to-market strategy", {}),
    ("evaluate an AI tool or vendor", {}),
    ("run a personal sanity check on a decision", {}),

    # Two-stage
    ("prioritize our technical debt and create a remediation roadmap",
     {"domain": ["technical"]}),
    ("build a sales strategy document for a new market segment",
     {"domain": ["business", "strategy"]}),
    ("choose between RAG fine-tuning and prompt engineering", {}),

    # Three-stage
    ("decide whether to build or buy a new data pipeline, document the decision, "
     "then stress-test it",
     {"domain": ["technical", "business"]}),
    ("raise a Series A: model the financials, build the pitch, then pressure-test "
     "the narrative",
     {"domain": ["finance", "business"]}),
    ("launch a new product feature from requirements through to launch readiness",
     {"domain": ["product", "business"]}),

    # Four+ stage
    ("audit our engineering team bottlenecks, plan fixes, implement changes, "
     "then verify impact",
     {"domain": ["technical", "business"]}),
    ("define our company AI strategy: assess readiness, plan adoption, execute "
     "rollout, validate results",
     {"domain": ["AI", "business", "strategy"]}),
]


# ── Chain data structure ─────────────────────────────────────────────────

@dataclass
class Chain:
    """A candidate response: one or more prompts in stage order."""
    steps: list[tuple[str, object]]  # (stage_label, RankedResult)

    @property
    def score(self) -> float:
        """Mean rerank score — the chain's overall quality signal."""
        return sum(r.rerank_score for _, r in self.steps) / len(self.steps)

    @property
    def min_score(self) -> float:
        """Weakest link in the chain."""
        return min(r.rerank_score for _, r in self.steps)

    @property
    def dedup_key(self) -> frozenset:
        return frozenset((s, r.prompt_id) for s, r in self.steps)

    @property
    def label(self) -> str:
        if len(self.steps) == 1:
            return "SINGLE PROMPT"
        stages = " → ".join(s.upper() for s, _ in self.steps)
        return f"{len(self.steps)}-STEP CHAIN  ({stages})"


def _generate_candidates(
    singles: list,
    stage_results: dict[str, list],
) -> list[Chain]:
    """Build all candidate chains from unfiltered singles + per-stage results.

    Candidates include:
      - Each unfiltered top result as a 1-step chain
      - Every contiguous subsequence (length >= 2) of populated stages
      - One alternative full-length chain using 2nd-best per stage
    """
    candidates: list[Chain] = []

    # 1. Singles from unfiltered search
    for r in singles:
        stage = r.metadata.get("primary_stage", "execute")
        candidates.append(Chain(steps=[(stage, r)]))

    # 2. Multi-step: all contiguous subsequences of available stages
    available = [s for s in STAGES if s in stage_results]
    for start in range(len(available)):
        for end in range(start + 2, len(available) + 1):
            sub = available[start:end]
            steps = [(s, stage_results[s][0]) for s in sub]
            candidates.append(Chain(steps=steps))

    # 3. Alt full chain: 2nd-best per stage where available, else 1st
    if len(available) >= 2:
        alt_steps = []
        has_any_alt = False
        for s in available:
            rs = stage_results[s]
            if len(rs) > 1:
                alt_steps.append((s, rs[1]))
                has_any_alt = True
            else:
                alt_steps.append((s, rs[0]))
        if has_any_alt:
            candidates.append(Chain(steps=alt_steps))

    # Deduplicate by (stage, prompt_id) set
    seen: set[frozenset] = set()
    unique: list[Chain] = []
    for c in candidates:
        key = c.dedup_key
        if key not in seen:
            seen.add(key)
            unique.append(c)

    unique.sort(key=lambda c: c.score, reverse=True)
    return unique


# ── Formatting ───────────────────────────────────────────────────────────

def _fmt_text(text: str, max_chars: int = 600) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return textwrap.indent(text, "    ")
    truncated = text[:max_chars].rsplit("\n", 1)[0]
    return textwrap.indent(truncated, "    ") + "\n    [... truncated]"


def _render_chain(lines: list, rank: int, chain: Chain, threshold: float) -> None:
    """Render one ranked chain into the report."""
    # Scale text length by chain size so the report stays readable
    if len(chain.steps) == 1:
        text_chars = 600
    elif len(chain.steps) <= 3:
        text_chars = 450
    else:
        text_chars = 350

    lines.append(f"{'─'*60}")
    score_detail = f"avg={chain.score:.2f}  min={chain.min_score:.2f}"
    lines.append(f"#{rank}  {chain.label}   ({score_detail})")
    lines.append("")

    for step_num, (stage, result) in enumerate(chain.steps, 1):
        weak = result.rerank_score < threshold
        flag = "  ⚠ WEAK" if weak else ""

        if len(chain.steps) == 1:
            prefix = ""
        else:
            prefix = f"Step {step_num}  "

        lines.append(
            f"  {prefix}[{stage.upper()}]  {result.prompt_id}{flag}"
        )
        lines.append(
            f"  rerank={result.rerank_score:.2f}  rrf={result.rrf_score:.4f}  "
            f"domain={result.metadata.get('domain', [])}  "
            f"complexity={result.metadata.get('complexity_level', '?')}"
        )
        lines.append("")
        lines.append(_fmt_text(result.prompt_text, max_chars=text_chars))
        lines.append("")


# ── Report generator ─────────────────────────────────────────────────────

async def run_report(
    queries: list[tuple[str, dict]],
    top_k: int,
    out_path: Path,
    threshold: float = WEAK_MATCH_THRESHOLD,
) -> None:
    """For each query, generate all candidate chains, rank them, show top N."""
    ps = PromptSearch()
    lines: list[str] = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines.append("PROMPT EVALUATION REPORT")
    lines.append(f"Generated  : {timestamp}")
    lines.append(f"Showing    : top {top_k} chains per query (single or multi-step)")
    lines.append(f"Weak flag  : rerank < {threshold}")
    lines.append(f"Ranking    : mean rerank score across chain steps")
    lines.append(f"Queries    : {len(queries)}")
    lines.append("")

    for i, (query, base_filters) in enumerate(queries, 1):
        # ── Unfiltered search: best overall prompts ───────────────────
        unfiltered = await ps.search(query, filters=base_filters,
                                     top_k=max(top_k, 5))
        singles = unfiltered.results

        # ── Per-stage search: for building multi-step chains ──────────
        stage_results: dict[str, list] = {}
        empty_stages: list[str] = []
        for stage in STAGES:
            filters = {**base_filters, "primary_stage": stage}
            resp = await ps.search(query, filters=filters, top_k=3)
            if resp.results:
                stage_results[stage] = resp.results
            else:
                empty_stages.append(stage)

        # ── Generate, rank, and pick top chains ───────────────────────
        candidates = _generate_candidates(singles, stage_results)
        shown = candidates[:top_k]

        # ── Query header ──────────────────────────────────────────────
        lines.append(SEPARATOR)
        lines.append(f"TEST {i}/{len(queries)}")
        lines.append(f"REQUEST: {query}")
        if base_filters:
            lines.append(f"FILTERS: {base_filters}")
        lines.append(
            f"CANDIDATES: {len(candidates)} chains generated  "
            f"(stages with data: {len(stage_results)}/{len(STAGES)})"
        )
        if empty_stages:
            lines.append(f"EMPTY STAGES: {', '.join(empty_stages)}")
        lines.append("")

        if not shown:
            lines.append("  No prompts found.")
            lines.append("")
            continue

        for rank, chain in enumerate(shown, 1):
            _render_chain(lines, rank, chain, threshold)

        lines.append("")

    # ── Footer ────────────────────────────────────────────────────────
    lines.append(SEPARATOR)
    lines.append("")
    lines.append("HOW TO READ THIS REPORT")
    lines.append("  Chains are ranked by mean rerank score across all steps.")
    lines.append("  A SINGLE PROMPT ranks high when one prompt covers the full request.")
    lines.append("  A MULTI-STEP CHAIN ranks high when each stage has a strong match.")
    lines.append("  Short chains often outscore long ones (fewer weak links to average in).")
    lines.append("  Compare: if #1 is a single and #2 is a chain, the single may suffice —")
    lines.append("  but the chain shows how to decompose the work if you need more depth.")
    lines.append(f"  ⚠ WEAK = rerank < {threshold} (poor fit for that stage).")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to: {out_path}")
    print(f"  {len(queries)} queries  |  top {top_k} chains each")


# ── CLI ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate prompt search: rank single and multi-step chains together."
    )
    parser.add_argument("--top-k", type=int, default=5,
                        help="Number of best chains to show per query (default 5)")
    parser.add_argument("--out", type=str, default=None,
                        help="Output path (default: tests/artifacts/eval_<timestamp>.txt)")
    parser.add_argument("--query", type=str, default=None,
                        help="Run a single custom query instead of defaults")
    parser.add_argument("--threshold", type=float, default=WEAK_MATCH_THRESHOLD,
                        help=f"Score below which steps are flagged weak "
                             f"(default {WEAK_MATCH_THRESHOLD})")
    args = parser.parse_args()

    artifacts = Path(__file__).parent.parent / "tests" / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")

    queries = [(args.query, {})] if args.query else QUERIES
    out = Path(args.out) if args.out else artifacts / f"eval_{stamp}.txt"

    asyncio.run(run_report(queries, args.top_k, out, threshold=args.threshold))


if __name__ == "__main__":
    main()
