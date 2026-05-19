"""
Obsidian → DB: load markdown prompt files, parse frontmatter, and insert into PostgreSQL.
"""

import hashlib
import frontmatter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


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
        'Models Tested': 'models_tested',
        'Parent Prompt': 'parent_prompt',
        'Last Evaluated': 'last_evaluated',
        'Expected Input': 'expected_input',
        'Expected Output': 'expected_output',
        'notes': 'notes',
        'Notes': 'notes',
    }

    for original_key, canonical_key in field_mappings.items():
        if original_key in metadata:
            value = metadata[original_key]

            if canonical_key in ['intent', 'task_type', 'domain', 'models_tested']:
                if isinstance(value, str):
                    vals = [v.strip() for v in value.split(',') if v.strip()]
                elif isinstance(value, list):
                    vals = value
                else:
                    vals = [str(value)] if value else []
                if canonical_key in ('intent', 'task_type'):
                    vals = [v.lower() for v in vals]
                canonical[canonical_key] = vals
            elif canonical_key == 'status':
                v = str(value).lower().strip()
                canonical[canonical_key] = v if v in ('active', 'deferred', 'archived') else 'active'
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

            prompt_id = md_file.stem
            canonical_metadata = parse_frontmatter_to_canonical(post.metadata)

            prompt_data = {
                'prompt_id': prompt_id,
                'file_path': str(md_file),
                'prompt_text': post.content,
                'content_hash': generate_content_hash(post.content),
                'file_mtime': datetime.fromtimestamp(md_file.stat().st_mtime),
                **canonical_metadata
            }

            prompts.append(prompt_data)

        except Exception as e:
            print(f"Error processing {md_file}: {e}")
            continue

    print(f"Loaded {len(prompts)} prompts (excluding Clippings)")
    return prompts


def insert_prompts_batch(cursor, prompts: List[Dict[str, Any]]):
    """Insert prompts into database with batch processing."""

    insert_sql = """
    INSERT INTO prompts (
        prompt_id, file_path, prompt_text, content_hash, file_mtime,
        intent, task_type, domain, status,
        parent_prompt, original_link, models_tested, notes, last_evaluated,
        expected_input, expected_output,
        backfill_status, last_updated, search_vector
    ) VALUES (
        %(prompt_id)s, %(file_path)s, %(prompt_text)s, %(content_hash)s, %(file_mtime)s,
        %(intent)s, %(task_type)s, %(domain)s, %(status)s,
        %(parent_prompt)s, %(original_link)s, %(models_tested)s, %(notes)s, %(last_evaluated)s,
        %(expected_input)s, %(expected_output)s,
        'pending', CURRENT_TIMESTAMP,
        to_tsvector('english',
            %(prompt_text)s || ' ' ||
            COALESCE(array_to_string(%(intent)s::varchar[], ' '), '') || ' ' ||
            COALESCE(array_to_string(%(task_type)s::varchar[], ' '), '') || ' ' ||
            COALESCE(array_to_string(%(domain)s::varchar[], ' '), '')
        )
    ) ON CONFLICT (prompt_id) DO UPDATE SET
        prompt_text = EXCLUDED.prompt_text,
        content_hash = EXCLUDED.content_hash,
        file_mtime = EXCLUDED.file_mtime,
        last_updated = CURRENT_TIMESTAMP,
        backfill_status = CASE
            WHEN prompts.content_hash != EXCLUDED.content_hash THEN 'pending'
            ELSE prompts.backfill_status
        END
    """

    batch_data = []
    for prompt in prompts:
        data = {
            'prompt_id': prompt['prompt_id'],
            'file_path': prompt['file_path'],
            'prompt_text': prompt['prompt_text'],
            'content_hash': prompt['content_hash'],
            'file_mtime': prompt['file_mtime'],
            'intent': prompt.get('intent', []),
            'task_type': prompt.get('task_type', []),
            'domain': prompt.get('domain', []),
            'status': prompt.get('status', 'active'),
            'parent_prompt': prompt.get('parent_prompt'),
            'original_link': prompt.get('original_link'),
            'models_tested': prompt.get('models_tested', []),
            'notes': prompt.get('notes'),
            'last_evaluated': prompt.get('last_evaluated'),
            'expected_input': prompt.get('expected_input'),
            'expected_output': prompt.get('expected_output'),
        }
        batch_data.append(data)

    cursor.executemany(insert_sql, batch_data)
    print(f"Inserted/updated {len(batch_data)} prompts")

    vault_ids = [d['prompt_id'] for d in batch_data]
    cursor.execute(
        "DELETE FROM prompts WHERE prompt_id != ALL(%s) RETURNING prompt_id",
        (vault_ids,),
    )
    deleted = [row[0] for row in cursor.fetchall()]
    if deleted:
        print(f"Deleted {len(deleted)} orphaned prompts: {deleted}")
    else:
        print("No orphaned prompts to delete")
