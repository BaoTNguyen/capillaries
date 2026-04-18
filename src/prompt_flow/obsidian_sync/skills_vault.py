"""
DB ↔ Obsidian: sync skills between PostgreSQL and the Obsidian vault.

Two directions:
  export  — DB → vault (markdown files under Areas/AI/Skills/)
  import  — vault → DB (create-or-update skills from markdown files)

Each skill is stored as a single .md file:
  <slug>.md

File format:
  ---
  name: "LLM Build & Tune Analyzer"
  slug: llm-build-tune-analyzer
  version: 1
  status: active
  routing_description: "..."
  domain: [AI, technical]
  intent: [analyze, plan]
  task_type: [analysis, planning]
  complexity_level: 4
  created_by: manual
  changelog: "..."
  ---

  ## Steps

  ### Step 1 · clarify · LLM Concept & Scope Clarifier
  **Rationale:** Names the exact LLM operation...

  <prompt text>

  ### Step 2 · plan · Premortem + Plan
  ...

Usage:
  python -m prompt_flow.obsidian_sync.skills_vault export
  python -m prompt_flow.obsidian_sync.skills_vault export --slug llm-build-tune-analyzer
  python -m prompt_flow.obsidian_sync.skills_vault import
  python -m prompt_flow.obsidian_sync.skills_vault import --file llm-build-tune-analyzer.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from prompt_flow.config import SKILLS_PATH
from prompt_flow.skills.promote import SkillPromoter


# ── Export ────────────────────────────────────────────────────────────────────

def export_skill(skill: dict, promoter: SkillPromoter, out_dir: Path) -> Path:
    """Write one skill to <slug>.md. Returns the path written."""
    from prompt_flow.skills.recall import SkillRecall
    recall = SkillRecall()
    steps = recall._resolve_steps(skill["steps"])

    # --- frontmatter ---
    meta = {
        "name":                 skill["name"],
        "slug":                 skill["slug"],
        "version":              skill["version"],
        "status":               skill["status"],
        "routing_description":  skill["routing_description"],
        "domain":               list(skill["domain"] or []),
        "intent":               list(skill["intent"] or []),
        "task_type":            list(skill["task_type"] or []),
        "complexity_level":     skill["complexity_level"],
        "created_by":           skill["created_by"],
        "changelog":            skill.get("changelog") or "",
    }
    frontmatter = yaml.dump(meta, allow_unicode=True, sort_keys=False).strip()

    # --- body ---
    lines = ["## Steps", ""]
    for step in steps:
        header = f"### Step {step['step_order']} · {step['stage']} · {step['prompt_id']}"
        lines.append(header)
        if step.get("rationale"):
            lines.append(f"**Rationale:** {step['rationale']}")
        lines.append("")
        lines.append(step.get("prompt_text") or "_prompt text not found_")
        lines.append("")

    body = "\n".join(lines).strip()
    content = f"---\n{frontmatter}\n---\n\n{body}\n"

    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{skill['slug']}.md"
    dest.write_text(content, encoding="utf-8")
    return dest


def cmd_export(args: argparse.Namespace) -> None:
    promoter = SkillPromoter()
    out_dir = SKILLS_PATH

    if args.slug:
        skill = promoter.get(args.slug)
        if not skill:
            print(f"Skill not found: {args.slug}", file=sys.stderr)
            sys.exit(1)
        skills = [skill]
    else:
        skills = promoter.list_skills()
        # Fetch full records (list_skills returns summary rows)
        skills = [promoter.get(str(s["skill_id"])) for s in skills]

    for skill in skills:
        path = export_skill(skill, promoter, out_dir)
        print(f"exported  {path.relative_to(SKILLS_PATH.parent.parent.parent)}")

    print(f"\n{len(skills)} skill(s) exported to {out_dir}")


# ── Import ────────────────────────────────────────────────────────────────────

def _parse_skill_file(path: Path) -> tuple[dict, list[dict]]:
    """
    Parse a skill markdown file.
    Returns (metadata_dict, steps_list).
    Steps are plain dicts: {prompt_id, stage, step_order, rationale}.
    """
    text = path.read_text(encoding="utf-8")

    if not text.startswith("---"):
        raise ValueError(f"{path.name}: missing YAML frontmatter")

    # Split frontmatter from body
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{path.name}: malformed frontmatter")

    meta = yaml.safe_load(parts[1])
    body = parts[2].strip()

    # Parse steps from body
    steps: list[dict] = []
    for block in body.split("### Step ")[1:]:
        first_line, *rest = block.strip().splitlines()
        # "1 · clarify · Prompt Title"
        header_parts = [p.strip() for p in first_line.split("·")]
        if len(header_parts) < 3:
            continue
        step_order = int(header_parts[0])
        stage      = header_parts[1]
        prompt_id  = header_parts[2]

        rationale = None
        for line in rest:
            if line.startswith("**Rationale:**"):
                rationale = line.removeprefix("**Rationale:**").strip()

        steps.append({
            "prompt_id":  prompt_id,
            "stage":      stage,
            "step_order": step_order,
            "rationale":  rationale,
        })

    return meta, steps


def cmd_import(args: argparse.Namespace) -> None:
    promoter = SkillPromoter()
    in_dir = SKILLS_PATH

    if args.file:
        files = [in_dir / args.file]
    else:
        files = sorted(in_dir.glob("*.md"))

    if not files:
        print("No .md files found in", in_dir)
        sys.exit(0)

    for path in files:
        try:
            meta, steps = _parse_skill_file(path)
        except Exception as exc:
            print(f"skip  {path.name}: {exc}", file=sys.stderr)
            continue

        slug = meta.get("slug") or path.stem
        existing = promoter.get(slug)

        if existing is None:
            skill = promoter.create(
                name=meta["name"],
                routing_description=meta["routing_description"],
                steps=steps,
                slug=slug,
                domain=meta.get("domain"),
                intent=meta.get("intent"),
                task_type=meta.get("task_type"),
                complexity_level=meta.get("complexity_level"),
                created_by=meta.get("created_by", "manual"),
            )
            action = "created"
            skill_id = skill.skill_id
        else:
            # Update metadata and replace steps
            promoter.update_metadata(
                slug,
                name=meta.get("name"),
                routing_description=meta.get("routing_description"),
                domain=meta.get("domain"),
                intent=meta.get("intent"),
                task_type=meta.get("task_type"),
                complexity_level=meta.get("complexity_level"),
                changelog=meta.get("changelog"),
            )
            if steps:
                promoter.set_steps(slug, steps)
            action = "updated"
            skill_id = str(existing["skill_id"])

        print(f"{action}  {slug}  ({skill_id})")

    print(f"\n{len(files)} file(s) processed from {in_dir}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync skills between PostgreSQL and the Obsidian vault."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    exp = sub.add_parser("export", help="DB → vault")
    exp.add_argument("--slug", help="Export a single skill by slug")

    imp = sub.add_parser("import", help="vault → DB")
    imp.add_argument("--file", help="Import a single .md file by name (e.g. my-skill.md)")

    args = parser.parse_args()

    if args.command == "export":
        cmd_export(args)
    elif args.command == "import":
        cmd_import(args)


if __name__ == "__main__":
    main()
