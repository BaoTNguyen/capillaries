"""
Generate a human-readable evaluation report using the skills-first search model.

For each query, the report shows three tiers:
  A. Top single prompts — best individual matches from retrieval + reranking
  B. Skill matches     — validated skills from skills.skills (only if tier A
                          is below SINGLE_THRESHOLD)
  C. Custom skill suggestion — assembled from best prompt per stage (only if
                          no existing skill matches)

Usage:
    python -m prompt_flow.search.eval                        # default queries, top 5
    python -m prompt_flow.search.eval --top-k 3              # fewer singles per query
    python -m prompt_flow.search.eval --out report.txt       # custom output path
    python -m prompt_flow.search.eval --query "your query"   # single query
"""

from __future__ import annotations

import argparse
import asyncio
import textwrap
from datetime import datetime
from pathlib import Path

from prompt_flow.search.api import (
    PromptSearch,
    SearchResponse,
    SINGLE_THRESHOLD,
    WEAK_STAGE_THRESHOLD,
    STAGES,
)

SEPARATOR = "=" * 80

WEAK_MATCH_THRESHOLD = WEAK_STAGE_THRESHOLD

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


# ── Formatting ───────────────────────────────────────────────────────────

def _fmt_text(text: str, max_chars: int = 600) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return textwrap.indent(text, "    ")
    truncated = text[:max_chars].rsplit("\n", 1)[0]
    return textwrap.indent(truncated, "    ") + "\n    [... truncated]"


def _render_single(lines: list, rank: int, result, threshold: float) -> None:
    """Render one ranked single prompt."""
    weak = result.rerank_score < threshold
    flag = "  ⚠ WEAK" if weak else ""
    stage = result.metadata.get("primary_stage", "?")

    lines.append(f"  #{rank}  [{stage.upper()}]  {result.prompt_id}{flag}")
    lines.append(
        f"      rerank={result.rerank_score:.2f}  rrf={result.rrf_score:.4f}  "
        f"domain={result.metadata.get('domain', [])}  "
        f"complexity={result.metadata.get('complexity_level', '?')}"
    )
    lines.append("")
    lines.append(_fmt_text(result.prompt_text, max_chars=500))
    lines.append("")


def _render_skill(lines: list, match) -> None:
    """Render a matched skill with its steps."""
    lines.append(f"  SKILL: {match.name}  (slug={match.slug}  v{match.version})")
    lines.append(f"  match_score={match.match_score:.4f}  "
                 f"domain={match.domain}  intent={match.intent}")
    lines.append(f"  routing: {match.routing_description}")
    lines.append("")
    for step in match.steps:
        lines.append(
            f"    Step {step['step_order']}  [{step['stage'].upper()}]  "
            f"{step['prompt_id']}"
        )
        if step.get("rationale"):
            lines.append(f"      rationale: {step['rationale']}")
        lines.append("")
        lines.append(_fmt_text(step.get("prompt_text", ""), max_chars=300))
        lines.append("")


def _render_suggestion(lines: list, steps: list) -> None:
    """Render a custom skill suggestion."""
    if not steps:
        lines.append("  No stages produced a match above the weak threshold.")
        lines.append("")
        return

    stage_list = " → ".join(s.stage.upper() for s in steps)
    lines.append(f"  SUGGESTED: {len(steps)}-step skill  ({stage_list})")
    lines.append("")
    for i, step in enumerate(steps, 1):
        weak = step.rerank_score < WEAK_MATCH_THRESHOLD
        flag = "  ⚠ WEAK" if weak else ""
        lines.append(
            f"    Step {i}  [{step.stage.upper()}]  {step.prompt_id}{flag}"
        )
        lines.append(
            f"      rerank={step.rerank_score:.2f}  "
            f"domain={step.metadata.get('domain', [])}  "
            f"complexity={step.metadata.get('complexity_level', '?')}"
        )
        lines.append("")
        lines.append(_fmt_text(step.prompt_text, max_chars=300))
        lines.append("")


# ── Report generator ─────────────────────────────────────────────────────

async def run_report(
    queries: list[tuple[str, dict]],
    top_k: int,
    out_path: Path,
    threshold: float = WEAK_MATCH_THRESHOLD,
    rerank_only: bool = False,
) -> None:
    """For each query, run the skills-first search and render results."""
    ps = PromptSearch(rerank_only=rerank_only)
    lines: list[str] = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines.append("PROMPT EVALUATION REPORT  (skills-first)")
    lines.append(f"Generated      : {timestamp}")
    lines.append(f"Single threshold: rerank >= {SINGLE_THRESHOLD} "
                 f"(above = recommend single prompt)")
    lines.append(f"Weak threshold  : rerank < {threshold}")
    lines.append(f"Queries         : {len(queries)}")
    lines.append("")

    summary_rows: list[tuple[str, str, float]] = []

    for i, (query, base_filters) in enumerate(queries, 1):
        resp = await ps.search(query, filters=base_filters, top_k=top_k)

        best_score = resp.results[0].rerank_score if resp.results else float("-inf")
        summary_rows.append((query, resp.recommendation, best_score))

        # ── Query header ──────────────────────────────────────────────
        lines.append(SEPARATOR)
        lines.append(f"TEST {i}/{len(queries)}")
        lines.append(f"REQUEST: {query}")
        if base_filters:
            lines.append(f"FILTERS: {base_filters}")
        lines.append(f"RECOMMENDATION: {resp.recommendation.upper()}")
        lines.append(f"CANDIDATES: {resp.total_candidates}")
        lines.append("")

        # ── Section A: Top single prompts ─────────────────────────────
        lines.append(f"── A. TOP SINGLE PROMPTS {'─' * 40}")
        lines.append("")
        if resp.results:
            for rank, result in enumerate(resp.results[:top_k], 1):
                _render_single(lines, rank, result, threshold)
        else:
            lines.append("  No prompts found.")
            lines.append("")

        # ── Section B: Skill match (only if not single_prompt) ────────
        if resp.recommendation != "single_prompt":
            lines.append(f"── B. SKILL MATCH {'─' * 46}")
            lines.append("")
            if resp.skill_match:
                _render_skill(lines, resp.skill_match)
            else:
                lines.append("  No matching skill found.")
                lines.append("")

        # ── Section C: Custom suggestion (only if custom_skill) ───────
        if resp.recommendation == "custom_skill":
            lines.append(f"── C. CUSTOM SKILL SUGGESTION {'─' * 34}")
            lines.append("")
            if resp.suggested_steps:
                _render_suggestion(lines, resp.suggested_steps)
            else:
                lines.append("  No viable custom skill could be assembled.")
                lines.append("")

        lines.append("")

    # ── Summary table ─────────────────────────────────────────────────
    lines.append(SEPARATOR)
    lines.append("")
    lines.append("SUMMARY")
    lines.append(f"  {'Query':<70} {'Rec':<15} {'Best':>6}")
    lines.append(f"  {'─'*70} {'─'*15} {'─'*6}")
    for query, rec, score in summary_rows:
        q = query[:68] + ".." if len(query) > 70 else query
        lines.append(f"  {q:<70} {rec:<15} {score:>6.2f}")
    lines.append("")

    # ── Footer ────────────────────────────────────────────────────────
    lines.append("HOW TO READ THIS REPORT")
    lines.append(f"  SINGLE_PROMPT: Top result scored >= {SINGLE_THRESHOLD} — "
                 "one prompt handles the query well.")
    lines.append(f"  SKILL: Top single was < {SINGLE_THRESHOLD} but a validated "
                 "skill matched — use the pre-built workflow.")
    lines.append(f"  CUSTOM_SKILL: Neither a single prompt nor an existing skill "
                 "fit — review the suggested per-stage assembly.")
    lines.append(f"  ⚠ WEAK = rerank < {threshold} (poor fit for that stage).")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to: {out_path}")
    print(f"  {len(queries)} queries  |  top {top_k} singles each")


# ── CLI ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate prompt search with the skills-first model."
    )
    parser.add_argument("--top-k", type=int, default=5,
                        help="Number of single prompts to show per query (default 5)")
    parser.add_argument("--out", type=str, default=None,
                        help="Output path (default: tests/artifacts/eval_<timestamp>.txt)")
    parser.add_argument("--query", type=str, default=None,
                        help="Run a single custom query instead of defaults")
    parser.add_argument("--threshold", type=float, default=WEAK_MATCH_THRESHOLD,
                        help=f"Score below which steps are flagged weak "
                             f"(default {WEAK_MATCH_THRESHOLD})")
    parser.add_argument("--rerank-only", action="store_true",
                        help="Skip retrieval, rerank all prompts directly")
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent.parent.parent
    artifacts = project_root / "tests" / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")

    queries = [(args.query, {})] if args.query else QUERIES
    out = Path(args.out) if args.out else artifacts / f"eval_{stamp}.txt"

    asyncio.run(run_report(queries, args.top_k, out, threshold=args.threshold,
                           rerank_only=args.rerank_only))


if __name__ == "__main__":
    main()
