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

from capillaries.search.retriever import expand_acronyms
from pathlib import Path

import frontmatter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = PROJECT_ROOT / "public_prompts"
FRONTEND_PUBLIC = PROJECT_ROOT / "demo" / "frontend" / "public"
SKILLS_DIR = PUBLIC_DIR / "skills"

VALID_INTENTS = {"adapt", "automate", "build", "communicate", "decide", "explore", "improve", "learn", "prepare", "reflect", "validate"}
VALID_TASK_TYPES = {"analyze", "compare", "debug", "model", "optimize", "design", "generate", "synthesize", "explain"}
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

    return {
        "id": prompt_id,
        "title": prompt_id.replace("-", " ").title(),
        "prompt_text": text,
        "intent": intent,
        "task_type": task_type,
        "domain": domain,
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
        domain = [d for d in domain if d in VALID_DOMAINS]

        intent = meta.get("intent", [])
        if isinstance(intent, str):
            intent = [intent]
        intent = [i.lower() for i in intent if i.lower() in VALID_INTENTS]

        task_type = meta.get("task_type", [])
        if isinstance(task_type, str):
            task_type = [task_type]
        task_type = [t.lower() for t in task_type if t.lower() in VALID_TASK_TYPES]

        skill = {
            "tag": meta.get("tag", skill_dir.name),
            "name": meta.get("name", skill_dir.name.replace("-", " ").title()),
            "summary": meta.get("summary", ""),
            "overview": overview.strip(),
            "when_to_use": when_to_use.strip(),
            "how_to_use": how_to_use.strip(),
            "domain": domain,
            "intent": intent,
            "task_type": task_type,
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

    # No up-front DELETE. Clearing and re-inserting regenerates every
    # prompt_id, which breaks serving_log rows, golden_examples and any
    # skills.steps written by an earlier run. Prompts are upserted on `title`
    # below — the same natural key the vault ingest uses — and anything no
    # longer present in the source is pruned at the end, by title.
    seen_titles: list[str] = []

    for p in prompts:
        # `title`, not `prompt_id`: the schema made prompt_id a UUID with a
        # generated default and title the NOT NULL UNIQUE natural key. The tag
        # is the natural key here, so it belongs in title.
        cur.execute("""
            INSERT INTO prompts (title, tag, file_path, prompt_text, intent, task_type, domain,
                                 source, content_hash, status, search_tsv)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'public', %s, 'active',
                    setweight(to_tsvector('english', %s), 'A') ||
                    to_tsvector('english', %s))
            ON CONFLICT (title) DO UPDATE SET
                prompt_text = EXCLUDED.prompt_text,
                intent = EXCLUDED.intent,
                task_type = EXCLUDED.task_type,
                domain = EXCLUDED.domain,
                source = 'public',
                content_hash = EXCLUDED.content_hash,
                search_tsv = EXCLUDED.search_tsv,
                tag = COALESCE(prompts.tag, EXCLUDED.tag)
        """, (
            # Department prompt filenames are already kebab-case (path.stem),
            # so title itself is tag-shaped — no separate slugify needed.
            p["id"], p["id"], p["file_path"], p["prompt_text"],
            p["intent"], p["task_type"], p["domain"],
            p["content_hash"],
            # search_tsv was omitted here entirely, so all 67 public prompts sat
            # with a NULL tsvector and the lexical channel could not see one of
            # them. Acronyms are expanded the same way obsidian_sync/ingest.py
            # does it, so both sources index alike.
            expand_acronyms(p["id"]), expand_acronyms(p["prompt_text"]),
        ))

    seen_titles.extend(p["id"] for p in prompts)
    print(f"Upserted {len(prompts)} department prompts")

    import json
    import uuid

    for skill in skills:
        # Steps are wired exactly like prompts: `title` is the natural key, the
        # row is upserted rather than deleted, and the real generated UUID comes
        # back via RETURNING. The previous version stored the filename stem in
        # `steps[].prompt_id`, which is not a UUID and joins to nothing — that
        # is how the hand-authored skill ended up with three dead references.
        steps_json = []
        step_order = 0
        for f in skill["files"]:
            if f["type"] != "prompt" or not f["path"].endswith(".md"):
                continue

            # Title convention matches the department prompts: the file stem
            # with the redundant `-prompt` suffix removed.
            title = f["path"][:-3]
            if title.endswith("-prompt"):
                title = title[: -len("-prompt")]
            content_hash = hashlib.sha256(f["content"].encode()).hexdigest()[:16]

            cur.execute("""
                INSERT INTO prompts (title, tag, file_path, prompt_text, domain, intent,
                                     task_type, source, content_hash, status, search_tsv)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'public', %s, 'active',
                        setweight(to_tsvector('english', %s), 'A') ||
                        to_tsvector('english', %s))
                ON CONFLICT (title) DO UPDATE SET
                    file_path        = EXCLUDED.file_path,
                    prompt_text      = EXCLUDED.prompt_text,
                    domain           = EXCLUDED.domain,
                    intent           = EXCLUDED.intent,
                    task_type        = EXCLUDED.task_type,
                    source           = 'public',
                    content_hash     = EXCLUDED.content_hash,
                    search_tsv       = EXCLUDED.search_tsv,
                    last_updated     = CURRENT_TIMESTAMP,
                    tag              = COALESCE(prompts.tag, EXCLUDED.tag)
                RETURNING prompt_id::text
            """, (
                title, title, f"public_prompts/skills/{skill['tag']}/{f['path']}",
                f["content"], skill["domain"], skill["intent"], skill["task_type"],
                content_hash,
                expand_acronyms(title), expand_acronyms(f["content"]),
            ))
            prompt_id = cur.fetchone()[0]
            seen_titles.append(title)

            step_order += 1
            steps_json.append({
                "prompt_id":   prompt_id,          # a real UUID, joinable to prompts
                "step_order":  step_order,
                "rationale":   f.get("description") or None,
                "pinned_hash": content_hash,       # content at wiring time
            })

        # Upsert on tag rather than DELETE + INSERT: skills.skill_sessions has
        # a foreign key onto skills.skills, so deleting a skill that has ever
        # been run raises ForeignKeyViolation.
        cur.execute("""
            INSERT INTO skills.skills (skill_id, name, tag, summary, domain,
                                       intent, task_type, version, status, steps,
                                       content_hash, source, search_tsv)
            VALUES (%(skill_id)s, %(name)s, %(tag)s, %(summary)s, %(domain)s,
                    %(intent)s, %(task_type)s, 1, 'active', %(steps)s::jsonb,
                    %(content_hash)s, 'public',
                    setweight(to_tsvector('english', %(name)s), 'A') ||
                    setweight(to_tsvector('english', %(summary)s), 'B') ||
                    to_tsvector('english',
                        COALESCE(array_to_string(%(domain)s::varchar[], ' '), '') || ' ' ||
                        COALESCE(array_to_string(%(intent)s::varchar[], ' '), '') || ' ' ||
                        COALESCE(array_to_string(%(task_type)s::varchar[], ' '), '')
                    ))
            ON CONFLICT (tag) DO UPDATE SET
                name                = EXCLUDED.name,
                summary = EXCLUDED.summary,
                domain              = EXCLUDED.domain,
                intent              = EXCLUDED.intent,
                task_type           = EXCLUDED.task_type,
                steps               = EXCLUDED.steps,
                content_hash        = EXCLUDED.content_hash,
                source              = 'public',
                search_tsv          = EXCLUDED.search_tsv,
                last_updated        = CURRENT_TIMESTAMP,
                version             = skills.skills.version + 1
        """, {
            "skill_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"skill:{skill['tag']}")),
            "name": skill["name"], "tag": skill["tag"], "summary": skill["summary"],
            "domain": skill["domain"], "intent": skill["intent"], "task_type": skill["task_type"],
            "steps": json.dumps(steps_json),
            "content_hash": hashlib.sha256(
                (skill["summary"] + json.dumps(steps_json, sort_keys=True)).encode()
            ).hexdigest()[:16],
        })
        print(f"  {skill['tag']:28} {len(steps_json)} steps")

    # Prune public prompts that vanished from the source tree. Scoped to
    # source='public' so vault-owned rows are never touched.
    cur.execute("DELETE FROM prompts WHERE source = 'public' AND NOT (title = ANY(%s))",
                (seen_titles,))
    if cur.rowcount:
        print(f"Pruned {cur.rowcount} public prompts no longer in the source tree")

    conn.commit()
    print(f"Upserted {len(skills)} skills")
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
