#!/usr/bin/env python3
"""
Ingest public prompts and skills into PostgreSQL and generate JSON bundles
for the Vite frontend build.

Usage:
    python scripts/ingest_public.py              # both DB + JSON
    python scripts/ingest_public.py --json-only  # just generate JSON files
    python scripts/ingest_public.py --db-only    # just insert into PostgreSQL
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import frontmatter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = PROJECT_ROOT / "public_prompts"
FRONTEND_PUBLIC = PROJECT_ROOT / "demo" / "frontend" / "public"
SKILLS_DIR = PUBLIC_DIR / "skills"

VALID_INTENTS = {"adapt", "automate", "build", "communicate", "decide", "explore", "improve", "learn", "prepare", "reflect", "validate"}
VALID_TASK_TYPES = {"analyze", "compare", "debug", "evaluate", "model", "optimize", "design", "generate", "synthesize", "explain"}
VALID_DOMAINS = {"AI", "business", "career", "finance", "learning", "personal", "product", "strategy", "writing", "technical"}


def parse_prompt_file(path: Path) -> dict | None:
    try:
        post = frontmatter.load(str(path))
    except Exception as e:
        print(f"  WARN: failed to parse {path.name}: {e}")
        return None

    meta = post.metadata
    text = post.content.strip()
    if not text:
        return None

    prompt_id = path.stem

    intent = meta.get("intent", [])
    if isinstance(intent, str):
        intent = [intent]
    intent = [i.lower() for i in intent if i.lower() in VALID_INTENTS]

    task_type = meta.get("task_type", [])
    if isinstance(task_type, str):
        task_type = [task_type]
    task_type = [t.lower() for t in task_type if t.lower() in VALID_TASK_TYPES]

    domain = meta.get("domain", [])
    if isinstance(domain, str):
        domain = [domain]
    domain = [d for d in domain if d.lower() in {v.lower() for v in VALID_DOMAINS}]

    complexity = meta.get("complexity_level")
    if isinstance(complexity, int) and 1 <= complexity <= 5:
        pass
    else:
        complexity = None

    return {
        "id": prompt_id,
        "title": prompt_id.replace("-", " ").title(),
        "prompt_text": text,
        "intent": intent,
        "task_type": task_type,
        "domain": domain,
        "complexity_level": complexity,
        "source": "public",
        "file_path": str(path),
        "content_hash": hashlib.sha256(text.encode()).hexdigest()[:16],
    }


def collect_prompts() -> list[dict]:
    prompts = []
    for dept_dir in sorted(PUBLIC_DIR.iterdir()):
        if not dept_dir.is_dir() or dept_dir.name == "skills":
            continue
        for md_file in sorted(dept_dir.glob("*.md")):
            p = parse_prompt_file(md_file)
            if p:
                prompts.append(p)
                print(f"  {dept_dir.name}/{md_file.name}")
    return prompts


def collect_skills() -> list[dict]:
    skills = []
    if not SKILLS_DIR.exists():
        return skills

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        index_path = skill_dir / "index.md"
        if not index_path.exists():
            print(f"  WARN: {skill_dir.name} has no index.md, skipping")
            continue

        try:
            post = frontmatter.load(str(index_path))
        except Exception as e:
            print(f"  WARN: failed to parse {index_path}: {e}")
            continue

        meta = post.metadata
        body = post.content.strip()

        overview = ""
        when_to_use = ""
        how_to_use = ""
        current_section = None
        for line in body.split("\n"):
            if line.strip().startswith("## Overview"):
                current_section = "overview"
                continue
            elif line.strip().startswith("## When to Use"):
                current_section = "when_to_use"
                continue
            elif line.strip().startswith("## How to Use"):
                current_section = "how_to_use"
                continue
            elif line.strip().startswith("## "):
                current_section = None
                continue

            if current_section == "overview":
                overview += line + "\n"
            elif current_section == "when_to_use":
                when_to_use += line + "\n"
            elif current_section == "how_to_use":
                how_to_use += line + "\n"

        files = []
        file_manifest = meta.get("files", [])

        for file_entry in file_manifest:
            file_path = skill_dir / file_entry["path"]
            if not file_path.exists():
                print(f"  WARN: {skill_dir.name}/{file_entry['path']} not found")
                continue

            content = file_path.read_text(encoding="utf-8")
            if file_entry["path"].endswith(".md"):
                try:
                    fp = frontmatter.load(str(file_path))
                    content = fp.content.strip()
                except Exception:
                    pass

            files.append({
                "path": file_entry["path"],
                "type": file_entry.get("type", "prompt"),
                "language": file_entry.get("language"),
                "description": file_entry.get("description", ""),
                "content": content,
            })

        for other_file in sorted(skill_dir.iterdir()):
            if other_file.name == "index.md":
                continue
            already = {f["path"] for f in files}
            if other_file.name in already:
                continue
            content = other_file.read_text(encoding="utf-8")
            ftype = "prompt" if other_file.suffix == ".md" else "code" if other_file.suffix in {".py", ".js", ".sql", ".sh"} else "config"
            lang_map = {".py": "python", ".js": "javascript", ".sql": "sql", ".sh": "bash", ".yaml": "yaml", ".yml": "yaml", ".csv": "csv", ".json": "json"}

            if other_file.suffix == ".md":
                try:
                    fp = frontmatter.load(str(other_file))
                    content = fp.content.strip()
                except Exception:
                    pass

            files.append({
                "path": other_file.name,
                "type": ftype,
                "language": lang_map.get(other_file.suffix),
                "description": "",
                "content": content,
            })

        domain = meta.get("domain", [])
        if isinstance(domain, str):
            domain = [domain]
        intent = meta.get("intent", [])
        if isinstance(intent, str):
            intent = [intent]
        task_type = meta.get("task_type", [])
        if isinstance(task_type, str):
            task_type = [task_type]

        skill = {
            "slug": meta.get("slug", skill_dir.name),
            "name": meta.get("name", skill_dir.name.replace("-", " ").title()),
            "routing_description": meta.get("routing_description", ""),
            "overview": overview.strip(),
            "when_to_use": when_to_use.strip(),
            "how_to_use": how_to_use.strip(),
            "domain": domain,
            "intent": intent,
            "task_type": task_type,
            "complexity_level": meta.get("complexity_level"),
            "status": meta.get("status", "active"),
            "files": files,
        }
        skills.append(skill)
        prompt_count = sum(1 for f in files if f["type"] == "prompt")
        code_count = sum(1 for f in files if f["type"] == "code")
        config_count = sum(1 for f in files if f["type"] in ("config", "template"))
        print(f"  {skill_dir.name}: {prompt_count} prompts, {code_count} code, {config_count} configs")

    return skills


def write_json(prompts, skills):
    FRONTEND_PUBLIC.mkdir(parents=True, exist_ok=True)
    prompts_path = FRONTEND_PUBLIC / "public_prompts.json"
    skills_path = FRONTEND_PUBLIC / "public_skills.json"

    prompts_json = [{k: v for k, v in p.items() if k not in ("file_path", "content_hash")} for p in prompts]
    with open(prompts_path, "w") as f:
        json.dump(prompts_json, f, indent=2)
    print(f"Wrote {len(prompts_json)} prompts to {prompts_path}")

    with open(skills_path, "w") as f:
        json.dump(skills, f, indent=2)
    print(f"Wrote {len(skills)} skills to {skills_path}")


def insert_db(prompts, skills):
    import psycopg2
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from capillaries.config import DB_CONFIG

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("DELETE FROM prompts WHERE source = 'public'")
    deleted = cur.rowcount
    if deleted:
        print(f"Cleared {deleted} existing public prompts")

    for p in prompts:
        cur.execute("""
            INSERT INTO prompts (prompt_id, file_path, prompt_text, intent, task_type, domain,
                                 complexity_level, source, content_hash, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'public', %s, 'active')
            ON CONFLICT (prompt_id) DO UPDATE SET
                prompt_text = EXCLUDED.prompt_text,
                intent = EXCLUDED.intent,
                task_type = EXCLUDED.task_type,
                domain = EXCLUDED.domain,
                complexity_level = EXCLUDED.complexity_level,
                source = 'public',
                content_hash = EXCLUDED.content_hash
        """, (
            p["id"], p["file_path"], p["prompt_text"],
            p["intent"], p["task_type"], p["domain"],
            p["complexity_level"], p["content_hash"],
        ))

    print(f"Inserted {len(prompts)} prompts into DB")

    for skill in skills:
        import uuid
        skill_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"skill:{skill['slug']}"))

        cur.execute("DELETE FROM skills.skills WHERE skill_id = %s", (skill_id,))

        cur.execute("""
            INSERT INTO skills.skills (skill_id, name, slug, routing_description, domain, intent,
                                       task_type, complexity_level, version, status, steps)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, 'active', '[]'::jsonb)
        """, (
            skill_id, skill["name"], skill["slug"], skill["routing_description"],
            skill["domain"], skill["intent"], skill["task_type"],
            skill["complexity_level"],
        ))

        steps_json = []
        step_order = 0
        for f in skill["files"]:
            if f["type"] == "prompt":
                prompt_id = f["path"].replace(".md", "").replace("-prompt", "")
                cur.execute("SELECT title FROM prompts WHERE title = %s", (prompt_id,))
                if not cur.fetchone():
                    cur.execute("""
                        INSERT INTO prompts (title, file_path, prompt_text, source, content_hash, status)
                        VALUES (%s, %s, %s, 'public', %s, 'active')
                        ON CONFLICT (title) DO NOTHING
                    """, (prompt_id, f["path"], f["content"], hashlib.sha256(f["content"].encode()).hexdigest()[:16]))

                step_order += 1
                steps_json.append({
                    "prompt_id": prompt_id,
                    "step_order": step_order,
                })

        if steps_json:
            import json
            cur.execute(
                "UPDATE skills.skills SET steps = %s WHERE skill_id = %s",
                (json.dumps(steps_json), skill_id),
            )

    conn.commit()
    print(f"Inserted {len(skills)} skills into DB")
    cur.close()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Ingest public prompts and skills")
    parser.add_argument("--json-only", action="store_true", help="Only generate JSON files")
    parser.add_argument("--db-only", action="store_true", help="Only insert into database")
    args = parser.parse_args()

    print("Collecting prompts...")
    prompts = collect_prompts()
    print(f"Found {len(prompts)} prompts\n")

    print("Collecting skills...")
    skills = collect_skills()
    print(f"Found {len(skills)} skills\n")

    if not args.db_only:
        print("Generating JSON bundles...")
        write_json(prompts, skills)
        print()

    if not args.json_only:
        print("Inserting into database...")
        insert_db(prompts, skills)
        print()

    print("Done!")


if __name__ == "__main__":
    main()
