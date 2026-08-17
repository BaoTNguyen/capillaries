"""
Obsidian → DB: load markdown prompt files, parse frontmatter, and insert into PostgreSQL.
"""

import hashlib
import re
import frontmatter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from capillaries.search.retriever import expand_acronyms


def tagify(name: str) -> str:
    """'GTM Strategy Builder' -> 'gtm-strategy-builder'.

    Same transform as skills.promote._tagify — duplicated rather than
    imported so obsidian_sync doesn't reach into capillaries.skills for a
    five-line pure function.
    """
    tag = name.lower().strip()
    tag = re.sub(r"[^\w\s-]", "", tag)
    tag = re.sub(r"[\s_]+", "-", tag)
    tag = re.sub(r"-+", "-", tag).strip("-")
    return tag


def generate_content_hash(content: str) -> str:
    """Generate hash for content change detection."""
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def parse_frontmatter_to_canonical(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Convert frontmatter to canonical schema."""
    canonical = {}

    field_mappings = {
        'Original Link': 'original_link',
        'Intent': 'intent',
        'Task Type': 'task_type',
        'Category': 'domain',
        'status': 'status',
        'Status': 'status',
        'Last Evaluated': 'last_evaluated',
        'Summary': 'summary',
        'notes': 'notes',
        'Notes': 'notes',
    }

    for original_key, canonical_key in field_mappings.items():
        if original_key in metadata:
            value = metadata[original_key]

            if canonical_key in ['intent', 'task_type', 'domain']:
                if isinstance(value, str):
                    vals = [v.strip() for v in value.split(',') if v.strip()]
                elif isinstance(value, list):
                    vals = value
                else:
                    vals = [str(value)] if value else []
                if canonical_key in ('intent', 'task_type'):
                    vals = [v.lower() for v in vals]
                    if canonical_key == 'task_type':
                        # 'evaluate' was merged into 'analyze' (89% of
                        # 'evaluate'-tagged prompts already carried 'analyze').
                        vals = list(dict.fromkeys(
                            'analyze' if v == 'evaluate' else v for v in vals
                        ))
                elif canonical_key == 'domain':
                    # DB stores domain lowercase; 'AI' is an acronym exception,
                    # not a casing choice, so it's the one value kept uppercase.
                    vals = list(dict.fromkeys(
                        'AI' if v.lower() == 'ai' else v.lower() for v in vals
                    ))
                canonical[canonical_key] = vals
            elif canonical_key == 'status':
                v = str(value).lower().strip()
                canonical[canonical_key] = v if v in ('draft', 'active', 'inactive') else 'active'
            else:
                canonical[canonical_key] = value

    return canonical


def load_prompts_from_obsidian(prompts_path: Path) -> List[Dict[str, Any]]:
    """Load and parse all prompt files from Obsidian vault."""
    prompts = []

    if not prompts_path.exists():
        print(f"Error: Prompts path does not exist: {prompts_path}")
        return prompts

    print(f"Loading prompts from: {prompts_path}")

    for md_file in prompts_path.rglob("*.md"):
        if "Clippings" in str(md_file):
            continue

        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                post = frontmatter.load(f)

            title = md_file.stem
            canonical_metadata = parse_frontmatter_to_canonical(post.metadata)

            prompt_data = {
                'title': title,
                'file_path': str(md_file),
                'prompt_text': post.content,
                'content_hash': generate_content_hash(post.content),
                'file_mtime': datetime.fromtimestamp(md_file.stat().st_mtime),
                **canonical_metadata
            }

            if title.startswith("Image Gen"):
                prompt_data["modality"] = "image"
            elif "video" in title.lower() or "remotion" in title.lower():
                prompt_data["modality"] = "video"
            else:
                prompt_data["modality"] = "text"

            prompts.append(prompt_data)

        except Exception as e:
            print(f"Error processing {md_file}: {e}")
            continue

    print(f"Loaded {len(prompts)} prompts (excluding Clippings)")
    return prompts


def insert_prompts_batch(cursor, prompts: List[Dict[str, Any]], *, prune_orphans: bool = True):
    """Insert prompts, optionally pruning rows absent from the vault batch."""

    insert_sql = """
    INSERT INTO prompts (
        title, tag, file_path, prompt_text, content_hash, file_mtime,
        intent, task_type, domain, status,
        original_link, notes, last_evaluated, summary,
        modality,
        backfill_status, last_updated, search_tsv
    ) VALUES (
        %(title)s, %(tag)s, %(file_path)s, %(prompt_text)s, %(content_hash)s, %(file_mtime)s,
        %(intent)s, %(task_type)s, %(domain)s, %(status)s,
        %(original_link)s, %(notes)s, %(last_evaluated)s, %(summary)s,
        %(modality)s,
        'pending', CURRENT_TIMESTAMP,
        setweight(to_tsvector('english', %(expanded_title)s), 'A') ||
        setweight(to_tsvector('english', COALESCE(%(summary)s, '')), 'B') ||
        to_tsvector('english',
            %(expanded_text)s || ' ' ||
            COALESCE(array_to_string(%(intent)s::varchar[], ' '), '') || ' ' ||
            COALESCE(array_to_string(%(task_type)s::varchar[], ' '), '') || ' ' ||
            COALESCE(array_to_string(%(domain)s::varchar[], ' '), '')
        )
    ) ON CONFLICT (title) DO UPDATE SET
        prompt_text = EXCLUDED.prompt_text,
        summary = EXCLUDED.summary,
        content_hash = EXCLUDED.content_hash,
        file_mtime = EXCLUDED.file_mtime,
        last_updated = CURRENT_TIMESTAMP,
        search_tsv = EXCLUDED.search_tsv,
        tag = COALESCE(prompts.tag, EXCLUDED.tag),
        backfill_status = CASE
            WHEN prompts.content_hash != EXCLUDED.content_hash THEN 'pending'
            ELSE prompts.backfill_status
        END
    """

    seen_tags: set[str] = set()
    batch_data = []
    for prompt in prompts:
        tag = tagify(prompt['title'])
        if tag in seen_tags:
            suffix = 2
            while f"{tag}-{suffix}" in seen_tags:
                suffix += 1
            tag = f"{tag}-{suffix}"
        seen_tags.add(tag)

        data = {
            'title': prompt['title'],
            'tag': tag,
            'file_path': prompt['file_path'],
            'prompt_text': prompt['prompt_text'],
            'content_hash': prompt['content_hash'],
            'file_mtime': prompt['file_mtime'],
            'intent': prompt.get('intent', []),
            'task_type': prompt.get('task_type', []),
            'domain': prompt.get('domain', []),
            'status': prompt.get('status', 'active'),
            'original_link': prompt.get('original_link'),
            'notes': prompt.get('notes'),
            'last_evaluated': prompt.get('last_evaluated'),
            'summary': prompt.get('summary'),
            'modality': prompt.get('modality', 'text'),
            'expanded_title': expand_acronyms(prompt['title']),
            'expanded_text': expand_acronyms(prompt['prompt_text']),
        }
        batch_data.append(data)

    cursor.executemany(insert_sql, batch_data)
    print(f"Inserted/updated {len(batch_data)} prompts")

    if not prune_orphans:
        return

    vault_titles = [d['title'] for d in batch_data]
    cursor.execute(
        # Scoped to source='private'. The vault owns private prompts; the
        # demo set (source='public', from public_prompts/ via
        # scripts/ingest_public.py) lives only in Postgres and has no vault
        # file, so an unscoped prune treats every one of them as an orphan and
        # deletes the lot — which is exactly what happened once.
        "DELETE FROM prompts "
        "WHERE source = 'private' AND title != ALL(%s) RETURNING title",
        (vault_titles,),
    )
    deleted = [row[0] for row in cursor.fetchall()]
    if deleted:
        print(f"Deleted {len(deleted)} orphaned prompts: {deleted}")
    else:
        print("No orphaned prompts to delete")
