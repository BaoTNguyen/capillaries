"""CLI for lifecycle management commands."""

from __future__ import annotations

import argparse

from capillaries.lifecycle.inactivate import (
    inactivate_stale_prompts,
    inactivate_stale_skills,
)
from capillaries.lifecycle.cascade import find_dependent_skills
from capillaries.lifecycle.review import (
    review_inactive_prompts,
    review_inactive_skills,
    find_similar_active_prompts,
)


def cmd_inactivate(args: argparse.Namespace) -> None:
    """Run auto-inactivation rules."""
    print("Checking for stale prompts...")
    prompts = inactivate_stale_prompts(dry_run=args.dry_run)

    if prompts:
        action = "Would inactivate" if args.dry_run else "Inactivated"
        print(f"\n{action} {len(prompts)} prompt(s):")
        for title in prompts:
            print(f"  - {title}")
            deps = find_dependent_skills(title)
            if deps:
                print(f"    ⚠ Referenced by active skills:")
                for d in deps:
                    print(f"      {d['name']} ({d['tag']}) step {d['step_order']}")
    else:
        print("  No stale prompts found.")

    print("\nChecking for stale skills...")
    skills = inactivate_stale_skills(dry_run=args.dry_run)

    if skills:
        action = "Would inactivate" if args.dry_run else "Inactivated"
        print(f"\n{action} {len(skills)} skill(s):")
        for s in skills:
            print(f"  - {s['name']} ({s['tag']})")
    else:
        print("  No stale skills found.")

    if args.dry_run:
        print("\n(dry run — no changes made)")


def cmd_review(args: argparse.Namespace) -> None:
    """Surface inactive items for quarterly review."""
    if not args.skills_only:
        prompts = review_inactive_prompts()
        if prompts:
            print(f"{'=' * 80}")
            print(f"INACTIVE PROMPTS ({len(prompts)})")
            print(f"{'=' * 80}")
            for p in prompts:
                print(f"\n  {p['title']}")
                print(f"    Domain:           {', '.join(p['domain'] or [])}")
                print(f"    Intent:           {', '.join(p['intent'] or [])}")
                print(f"    Last direct use:  {p['last_direct_use'] or 'never'}")
                print(f"    Total runs:       {p['total_runs']}")
                print(f"    Success rate:     {p['success_rate'] or 'N/A'}")
                print(f"    Active skills:    {p['active_skill_count']}")
                print(f"    Golden examples:  {p['golden_example_count']}")
                print(f"    Variants:         {p['variant_count']}")

                similar = find_similar_active_prompts(p['title'])
                if similar:
                    print(f"    Similar active:")
                    for s in similar:
                        sim = f"{s['similarity']:.3f}" if s['similarity'] else "N/A"
                        print(f"      {s['title']} (sim: {sim})")
        else:
            print("No inactive prompts.")

    if not args.prompts_only:
        skills = review_inactive_skills()
        if skills:
            print(f"\n{'=' * 80}")
            print(f"INACTIVE SKILLS ({len(skills)})")
            print(f"{'=' * 80}")
            for s in skills:
                print(f"\n  {s['name']} ({s['tag']})")
                print(f"    Last run:             {s['last_run_at'] or 'never'}")
                print(f"    Total runs:           {s['total_runs']}")
                print(f"    Success rate:         {s['success_rate'] or 'N/A'}")
                print(f"    Steps:                {s['step_count']}")
                print(f"    Inactive prompts:     {s['inactive_prompt_count']}")
        else:
            print("No inactive skills.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prompt lifecycle management")
    sub = parser.add_subparsers(dest="command", required=True)

    inact = sub.add_parser("inactivate", help="Auto-inactivate stale prompts and skills")
    inact.add_argument("--dry-run", action="store_true", help="Preview without making changes")

    rev = sub.add_parser("review", help="Surface inactive items for quarterly review")
    rev.add_argument("--prompts-only", action="store_true")
    rev.add_argument("--skills-only", action="store_true")

    args = parser.parse_args()

    if args.command == "inactivate":
        cmd_inactivate(args)
    elif args.command == "review":
        cmd_review(args)


if __name__ == "__main__":
    main()
