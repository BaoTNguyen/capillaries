"""
Interactive skill management CLI.

Promote eval chains to skills, or build and edit skills manually.

Usage:
    # Promote from search
    python -m capillaries.skills.cli --query "write a go-to-market strategy"

    # Create a skill from scratch (no search required)
    python -m capillaries.skills.cli --create

    # View a skill's full details
    python -m capillaries.skills.cli --show llm-build-tune-analyzer

    # Edit a skill's metadata or steps interactively
    python -m capillaries.skills.cli --edit llm-build-tune-analyzer

    # Add a step to an existing skill
    python -m capillaries.skills.cli --add-step llm-build-tune-analyzer

    # Remove a step from a skill
    python -m capillaries.skills.cli --remove-step llm-build-tune-analyzer

    # List skills
    python -m capillaries.skills.cli --list
    python -m capillaries.skills.cli --list --status draft

    # Activate or inactivate
    python -m capillaries.skills.cli --activate <skill_id>
    python -m capillaries.skills.cli --inactivate <skill_id>
"""

from __future__ import annotations

import argparse
import asyncio

from capillaries.search.api import PromptSearch
from capillaries.skills.promote import SkillPromoter, _slugify

# ── Display helpers ───────────────────────────────────────────────────────

def _print_skill(skill: dict, verbose: bool = True) -> None:
    steps = skill.get("steps") or []
    runs = skill.get("total_runs") or 0
    rate = f"{skill['success_rate']:.0%}" if skill.get("success_rate") is not None else "—"
    print(f"\n  [{skill['status']:10}]  v{skill['version']}  {skill['slug']}")
    print(f"  Name    : {skill['name']}")
    print(f"  ID      : {skill['skill_id']}")
    print(f"  Routing : {skill['routing_description']}")
    print(f"  Domain  : {skill.get('domain', [])}  |  Intent: {skill.get('intent', [])}  |  Type: {skill.get('task_type', [])}")
    print(f"  Runs    : {runs}  |  Success: {rate}  |  Complexity: {skill.get('complexity_level', '—')}")
    if verbose and steps:
        print(f"  Steps   :")
        for s in sorted(steps, key=lambda x: x.get("step_order", 0)):
            print(f"    {s['step_order']}. {s['prompt_id']}")
            if s.get("rationale"):
                print(f"         {s['rationale']}")


def _print_skill_list(skills: list[dict]) -> None:
    if not skills:
        print("  No skills found.")
        return
    for s in skills:
        runs = s.get("total_runs") or 0
        rate = f"{s['success_rate']:.0%}" if s.get("success_rate") is not None else "—"
        print(f"  [{s['status']:10}]  v{s['version']}  {s['slug']}")
        print(f"             {s['name']}")
        print(f"             runs={runs}  success={rate}  id={s['skill_id']}")
        print()


def _prompt_field(label: str, current: str = "", required: bool = False) -> str:
    """Prompt for a text field. Shows current value; blank input keeps it."""
    hint = f" [{current}]" if current else ""
    while True:
        val = input(f"  {label}{hint}: ").strip()
        if val:
            return val
        if current:
            return current
        if not required:
            return ""
        print("  (required)")


def _prompt_list(label: str, current: list | None = None) -> list[str]:
    """Prompt for a comma-separated list."""
    current_str = ", ".join(current or [])
    hint = f" [{current_str}]" if current_str else ""
    raw = input(f"  {label}{hint}: ").strip()
    if not raw and current:
        return current
    return [v.strip() for v in raw.split(",") if v.strip()]


def _collect_steps(existing: list | None = None) -> list[dict]:
    """Interactively collect steps, starting from existing if provided."""
    steps = list(existing or [])

    if steps:
        print("\n  Current steps:")
        for s in sorted(steps, key=lambda x: x.get("step_order", 0)):
            print(f"    {s['step_order']}. {s['prompt_id']}")
            if s.get("rationale"):
                print(f"         {s['rationale']}")

    print("\n  Add steps (blank prompt_id to finish):")
    order = max((s.get("step_order", 0) for s in steps), default=0) + 1

    while True:
        print(f"\n  Step {order}:")
        prompt_id = input("    Prompt ID: ").strip()
        if not prompt_id:
            break
        rationale = input("    Rationale (optional): ").strip() or None
        steps.append({
            "prompt_id":  prompt_id,
            "step_order": order,
            "rationale":  rationale,
        })
        order += 1

    return steps


# ── Command implementations ───────────────────────────────────────────────

def run_show(slug_or_id: str) -> None:
    promoter = SkillPromoter()
    skill = promoter.get(slug_or_id)
    if not skill:
        print(f"Skill not found: {slug_or_id}")
        return
    _print_skill(skill, verbose=True)
    print()


def run_create() -> None:
    """Create a skill from scratch without running a search."""
    promoter = SkillPromoter()
    print("\nCreate new skill\n")

    name = _prompt_field("Name", required=True)
    slug_suggestion = _slugify(name)
    slug_input = input(f"  Slug [{slug_suggestion}]: ").strip()
    slug = slug_input or slug_suggestion

    routing = _prompt_field("Routing description (one line — what triggers this skill)", required=True)
    domain = _prompt_list("Domain (comma-separated, e.g. AI, technical)")
    intent = _prompt_list("Intent (comma-separated, e.g. analyze, plan)")
    task_type = _prompt_list("Task type (comma-separated, e.g. analysis, planning)")

    complexity_raw = input("  Complexity (1-5, blank to skip): ").strip()
    complexity = int(complexity_raw) if complexity_raw.isdigit() and 1 <= int(complexity_raw) <= 5 else None

    steps = _collect_steps()

    # Confirm
    print(f"\n{'─'*60}")
    print(f"  Name    : {name}")
    print(f"  Slug    : {slug}")
    print(f"  Routing : {routing}")
    print(f"  Domain  : {domain}  Intent: {intent}  Type: {task_type}")
    print(f"  Steps   : {len(steps)}")
    for s in steps:
        print(f"    {s['step_order']}. {s['prompt_id']}")
    print(f"{'─'*60}")

    if input("\nSave? (y/n): ").strip().lower() != "y":
        print("Cancelled.")
        return

    skill = promoter.create(
        name=name, slug=slug,
        routing_description=routing,
        steps=steps,
        domain=domain or None,
        intent=intent or None,
        task_type=task_type or None,
        complexity_level=complexity,
    )
    print(f"\nSkill saved.")
    print(f"  skill_id : {skill.skill_id}")
    print(f"  slug     : {skill.slug}  v{skill.version}")
    print(f"  status   : {skill.status}")
    print(f"\nActivate when validated:")
    print(f"  python -m capillaries.skills.cli --activate {skill.skill_id}")


def run_edit(slug_or_id: str) -> None:
    """Interactively edit a skill's metadata and/or steps."""
    promoter = SkillPromoter()
    skill = promoter.get(slug_or_id)
    if not skill:
        print(f"Skill not found: {slug_or_id}")
        return

    print(f"\nEditing: {skill['name']}  (v{skill['version']}  {skill['status']})")
    print("Press Enter to keep the current value.\n")

    name = _prompt_field("Name", current=skill["name"])
    routing = _prompt_field("Routing description", current=skill["routing_description"])
    domain = _prompt_list("Domain", current=skill.get("domain"))
    intent = _prompt_list("Intent", current=skill.get("intent"))
    task_type = _prompt_list("Task type", current=skill.get("task_type"))
    complexity_raw = input(f"  Complexity (1-5) [{skill.get('complexity_level', '')}]: ").strip()
    complexity = int(complexity_raw) if complexity_raw.isdigit() and 1 <= int(complexity_raw) <= 5 else skill.get("complexity_level")
    changelog = input("  Changelog note (what changed): ").strip() or None

    promoter.update_metadata(
        slug_or_id,
        name=name,
        routing_description=routing,
        domain=domain or None,
        intent=intent or None,
        task_type=task_type or None,
        complexity_level=complexity,
        changelog=changelog,
    )
    print("  Metadata updated.")

    if input("\nEdit steps? (y/n): ").strip().lower() == "y":
        steps = _collect_steps(existing=skill.get("steps", []))
        promoter.set_steps(slug_or_id, steps)
        print(f"  Steps updated ({len(steps)} total).")

    print("\nDone.")


def run_add_step(slug_or_id: str) -> None:
    """Add a single step to an existing skill."""
    promoter = SkillPromoter()
    skill = promoter.get(slug_or_id)
    if not skill:
        print(f"Skill not found: {slug_or_id}")
        return

    current_steps = skill.get("steps") or []
    print(f"\nAdding step to: {skill['name']}")
    if current_steps:
        print("Current steps:")
        for s in sorted(current_steps, key=lambda x: x.get("step_order", 0)):
            print(f"  {s['step_order']}. {s['prompt_id']}")

    print()
    prompt_id = input("  Prompt ID: ").strip()
    if not prompt_id:
        print("Cancelled.")
        return

    rationale = input("  Rationale (optional): ").strip() or None

    max_order = max((s.get("step_order", 0) for s in current_steps), default=0)
    order_raw = input(f"  Insert at position (1-{max_order+1}, default {max_order+1}): ").strip()
    order = int(order_raw) if order_raw.isdigit() else max_order + 1

    # Shift existing steps at or above the target position
    for s in current_steps:
        if s.get("step_order", 0) >= order:
            s["step_order"] += 1

    current_steps.append({
        "prompt_id":  prompt_id,
        "step_order": order,
        "rationale":  rationale,
    })
    current_steps.sort(key=lambda s: s.get("step_order", 0))

    promoter.set_steps(slug_or_id, current_steps)
    print(f"\nStep added at position {order}.")
    print("Updated steps:")
    for s in current_steps:
        print(f"  {s['step_order']}. {s['prompt_id']}")


def run_remove_step(slug_or_id: str) -> None:
    """Remove a step from a skill by step number."""
    promoter = SkillPromoter()
    skill = promoter.get(slug_or_id)
    if not skill:
        print(f"Skill not found: {slug_or_id}")
        return

    steps = skill.get("steps") or []
    if not steps:
        print("Skill has no steps.")
        return

    print(f"\nSteps in: {skill['name']}")
    for s in sorted(steps, key=lambda x: x.get("step_order", 0)):
        print(f"  {s['step_order']}. {s['prompt_id']}")

    order_raw = input("\n  Remove step number: ").strip()
    if not order_raw.isdigit():
        print("Cancelled.")
        return

    order = int(order_raw)
    new_steps = [s for s in steps if s.get("step_order") != order]

    if len(new_steps) == len(steps):
        print(f"No step with number {order}.")
        return

    # Re-number remaining steps
    for i, s in enumerate(sorted(new_steps, key=lambda x: x.get("step_order", 0)), 1):
        s["step_order"] = i

    promoter.set_steps(slug_or_id, new_steps)
    print(f"\nStep {order} removed. Updated steps:")
    for s in new_steps:
        print(f"  {s['step_order']}. {s['prompt_id']}")


# ── Search-based promotion ────────────────────────────────────────────────

async def run_promote(query: str, filters: dict, top_k: int) -> None:
    print(f"\nSearching: \"{query}\"")
    print("Loading models...\n")
    ps = PromptSearch()
    resp = await ps.search(query, filters=filters, top_k=top_k)

    print(f"Recommendation: {resp.recommendation.upper()}")
    print(f"Candidates: {resp.total_candidates}\n")

    # Show top single prompts
    promotable: list[tuple[str, dict]] = []  # (label, step_dict) for promotion

    if resp.results:
        print(f"── Single Prompts {'─'*42}")
        for rank, result in enumerate(resp.results[:top_k], 1):
            print(f"  #{rank}  {result.prompt_id}  "
                  f"rerank={result.rerank_score:.2f}")
            promotable.append((
                f"Single: {result.prompt_id}",
                {"prompt_id": result.prompt_id,
                 "step_order": 1, "rationale": None},
            ))

    # Show skill match
    if resp.skill_match:
        print(f"\n── Existing Skill Match {'─'*37}")
        m = resp.skill_match
        print(f"  {m.name}  (slug={m.slug}  v{m.version}  score={m.match_score:.4f})")
        for step in m.steps:
            print(f"    {step['step_order']}. {step['prompt_id']}")
        print("  (Already exists — no promotion needed)")


    if not promotable:
        print("\nNo results to promote.")
        return

    print(f"\n{'='*60}")
    print("\nOptions:")
    for i, (label, _) in enumerate(promotable, 1):
        print(f"  {i}. {label}")

    choice = input(f"\nPromote which? (1-{len(promotable)}, or q to quit): ").strip()
    if choice.lower() == "q" or not choice:
        print("Cancelled.")
        return

    try:
        idx = int(choice) - 1
        assert 0 <= idx < len(promotable)
    except (ValueError, AssertionError):
        print("Invalid choice.")
        return

    _, selected = promotable[idx]
    # Normalize to list of steps
    steps = selected if isinstance(selected, list) else [selected]

    print(f"\nPromoting {len(steps)} step(s)")
    print()

    name = _prompt_field("Skill name", required=True)
    slug_suggestion = _slugify(name)
    slug_input = input(f"  Slug [{slug_suggestion}]: ").strip()
    slug = slug_input or slug_suggestion
    routing = _prompt_field("Routing description", current=query, required=True)

    promoter = SkillPromoter()
    skill = promoter.create(
        name=name, slug=slug,
        routing_description=routing,
        steps=steps,
    )
    print(f"\nSkill saved.")
    print(f"  skill_id : {skill.skill_id}")
    print(f"  slug     : {skill.slug}  v{skill.version}")
    print(f"  status   : {skill.status}")
    print(f"\nActivate when validated:")
    print(f"  python -m capillaries.skills.cli --activate {skill.skill_id}")


# ── CLI ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage skills: promote from search, create manually, or edit."
    )
    parser.add_argument("--query", type=str, help="Search query to promote a chain from")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--create", action="store_true",
                        help="Create a skill from scratch")
    parser.add_argument("--show", type=str, metavar="SLUG_OR_ID",
                        help="Show full skill details")
    parser.add_argument("--edit", type=str, metavar="SLUG_OR_ID",
                        help="Edit a skill's metadata and/or steps interactively")
    parser.add_argument("--add-step", type=str, metavar="SLUG_OR_ID",
                        help="Add a step to an existing skill")
    parser.add_argument("--remove-step", type=str, metavar="SLUG_OR_ID",
                        help="Remove a step from a skill")
    parser.add_argument("--list", action="store_true", help="List all skills")
    parser.add_argument("--status", type=str, default=None,
                        help="Filter --list by status")
    parser.add_argument("--activate", type=str, metavar="SKILL_ID")
    parser.add_argument("--inactivate", type=str, metavar="SKILL_ID")
    args = parser.parse_args()

    promoter = SkillPromoter()

    if args.list:
        skills = promoter.list_skills(status=args.status)
        label = f"({args.status})" if args.status else "(all)"
        print(f"\nSkills {label}:\n")
        _print_skill_list(skills)
    elif args.show:
        run_show(args.show)
    elif args.create:
        run_create()
    elif args.edit:
        run_edit(args.edit)
    elif args.add_step:
        run_add_step(args.add_step)
    elif args.remove_step:
        run_remove_step(args.remove_step)
    elif args.activate:
        promoter.activate(args.activate)
        print(f"Skill {args.activate} → active")
    elif args.inactivate:
        promoter.inactivate(args.inactivate)
        print(f"Skill {args.inactivate} → inactive")
    elif args.query:
        asyncio.run(run_promote(args.query, {}, args.top_k))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
