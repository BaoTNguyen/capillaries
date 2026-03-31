"""
Interactive skill promotion CLI.

Runs a query, shows the top chains, and lets you pick one to save as a skill.

Usage:
    python scripts/promote_skill.py --query "write a go-to-market strategy"
    python scripts/promote_skill.py --query "build a cash flow model" --top-k 3
    python scripts/promote_skill.py --list
    python scripts/promote_skill.py --activate <skill_id>
    python scripts/promote_skill.py --deprecate <skill_id>
"""

from __future__ import annotations

import argparse
import asyncio
import textwrap

from prompt_flow.search.api import PromptSearch
from prompt_flow.skills.promote import SkillPromoter

# Reuse chain generation logic from eval_report
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from eval_report import STAGES, WEAK_MATCH_THRESHOLD, _generate_candidates, _fmt_text


# ── Display ───────────────────────────────────────────────────────────────

def _print_chain(rank: int, chain, threshold: float = WEAK_MATCH_THRESHOLD) -> None:
    print(f"\n  #{rank}  {chain.label}   (avg score: {chain.score:.2f}  min: {chain.min_score:.2f})")
    for step_num, (stage, result) in enumerate(chain.steps, 1):
        weak = result.rerank_score < threshold
        flag = "  ⚠ WEAK" if weak else ""
        prefix = f"Step {step_num}  " if len(chain.steps) > 1 else ""
        print(f"       {prefix}[{stage.upper()}]  {result.prompt_id}{flag}")
        print(f"       rerank={result.rerank_score:.2f}  "
              f"domain={result.metadata.get('domain', [])}  "
              f"stage={result.metadata.get('primary_stage', '?')}")
        snippet = result.prompt_text.strip()[:200].replace("\n", " ")
        print(f"       \"{snippet}...\"")


def _print_skill_list(skills: list[dict]) -> None:
    if not skills:
        print("  No skills found.")
        return
    for s in skills:
        runs = s["total_runs"] or 0
        rate = f"{s['success_rate']:.0%}" if s["success_rate"] is not None else "—"
        print(f"  [{s['status']:10}]  v{s['version']}  {s['slug']}")
        print(f"             {s['name']}")
        print(f"             {s['routing_description']}")
        print(f"             runs={runs}  success={rate}  id={s['skill_id']}")
        print()


# ── Search helpers ────────────────────────────────────────────────────────

async def _get_chains(query: str, filters: dict, top_k: int):
    ps = PromptSearch()

    unfiltered = await ps.search(query, filters=filters, top_k=max(top_k, 5))
    singles = unfiltered.results

    stage_results: dict[str, list] = {}
    for stage in STAGES:
        resp = await ps.search(query, filters={**filters, "primary_stage": stage}, top_k=3)
        if resp.results:
            stage_results[stage] = resp.results

    return _generate_candidates(singles, stage_results)


# ── Interactive flow ──────────────────────────────────────────────────────

async def run_promote(query: str, filters: dict, top_k: int) -> None:
    print(f"\nSearching: \"{query}\"")
    print("Loading models...\n")

    candidates = await _get_chains(query, filters, top_k)
    shown = candidates[:top_k]

    if not shown:
        print("No results found.")
        return

    print(f"Top {len(shown)} chains:\n")
    print("=" * 60)
    for rank, chain in enumerate(shown, 1):
        _print_chain(rank, chain)
        print()

    # Pick a chain
    print("=" * 60)
    choice = input(f"\nPromote which chain? (1-{len(shown)}, or q to quit): ").strip()
    if choice.lower() == "q" or not choice:
        print("Cancelled.")
        return

    try:
        idx = int(choice) - 1
        assert 0 <= idx < len(shown)
    except (ValueError, AssertionError):
        print("Invalid choice.")
        return

    selected = shown[idx]

    print(f"\nSelected: {selected.label}  (avg score: {selected.score:.2f})")
    for _, (stage, result) in enumerate(selected.steps, 1):
        print(f"  [{stage.upper()}]  {result.prompt_id}")

    # Collect metadata
    print()
    name = input("Skill name: ").strip()
    if not name:
        print("Name required. Cancelled.")
        return

    print(f"Routing description (one line — what triggers this skill):")
    print(f"  Suggestion: \"{query}\"")
    routing = input("  > ").strip()
    if not routing:
        routing = query

    # Confirm
    from prompt_flow.skills.promote import _slugify
    slug = _slugify(name)
    steps_summary = " → ".join(
        f"{stage.upper()}:{result.prompt_id}" for stage, result in selected.steps
    )
    print(f"\n{'─'*60}")
    print(f"  Name   : {name}")
    print(f"  Slug   : {slug}")
    print(f"  Route  : {routing}")
    print(f"  Steps  : {steps_summary}")
    print(f"  Status : draft (activate manually when validated)")
    print(f"{'─'*60}")

    confirm = input("\nSave as skill? (y/n): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    promoter = SkillPromoter()
    skill = promoter.promote(
        chain=selected,
        name=name,
        routing_description=routing,
    )

    print(f"\nSkill saved.")
    print(f"  skill_id : {skill.skill_id}")
    print(f"  slug     : {skill.slug}  v{skill.version}")
    print(f"  status   : {skill.status}")
    print(f"\nTo activate when validated:")
    print(f"  python scripts/promote_skill.py --activate {skill.skill_id}")


# ── CLI ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Promote eval chains to skills, or manage existing skills."
    )
    parser.add_argument("--query", type=str, help="Query to generate chains from")
    parser.add_argument("--top-k", type=int, default=5,
                        help="Chains to show for selection (default 5)")
    parser.add_argument("--list", action="store_true",
                        help="List all skills")
    parser.add_argument("--status", type=str, default=None,
                        help="Filter --list by status (draft, active, deprecated, archived)")
    parser.add_argument("--activate", type=str, metavar="SKILL_ID",
                        help="Set a skill to active")
    parser.add_argument("--deprecate", type=str, metavar="SKILL_ID",
                        help="Set a skill to deprecated")
    args = parser.parse_args()

    promoter = SkillPromoter()

    if args.list:
        skills = promoter.list_skills(status=args.status)
        label = f"({args.status})" if args.status else "(all)"
        print(f"\nSkills {label}:\n")
        _print_skill_list(skills)

    elif args.activate:
        promoter.activate(args.activate)
        print(f"Skill {args.activate} → active")

    elif args.deprecate:
        promoter.deprecate(args.deprecate)
        print(f"Skill {args.deprecate} → deprecated")

    elif args.query:
        asyncio.run(run_promote(args.query, {}, args.top_k))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
