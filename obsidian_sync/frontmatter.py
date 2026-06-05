"""
DB → Obsidian: sync classified metadata from PostgreSQL back to markdown frontmatter.
The Obsidian Base (Prompt Database.base) reads frontmatter, so updates here
surface automatically in the Base view.

Field mapping (DB → Obsidian frontmatter):
    intent            → Intent          (list, Title Case for display)
    task_type         → Task Type       (list, Title Case for display)
    domain            → Category        (list, preserve original casing)
    status            → status          (string, Title Case)
    complexity_level  → Complexity      (int)

DB stores taxonomy values in lowercase. This module Title-Cases them for
Obsidian display. The ingest module lowercases them on the way back in.
"""

import psycopg2
import frontmatter
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List
from prompt_flow.config.paths import DB_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    handlers=[
        logging.FileHandler('obsidian_sync.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# DB field → (frontmatter key, value transform)
FIELD_MAP = {
    'intent':               ('Intent',               lambda v: [s.title() for s in v] if v else None),
    'task_type':            ('Task Type',            lambda v: [s.title() for s in v] if v else None),
    'domain':               ('Category',             lambda v: v if v else None),  # AI stays AI, etc.
    'status':               ('status',               lambda v: v.title() if v else None),
    'complexity_level':     ('Complexity',           lambda v: v),
    'models_tested':        ('Models Tested',        lambda v: v if v else []),
    'last_evaluated':       ('Last Evaluated',       lambda v: str(v) if v else None),
    'notes':                ('Notes',                lambda v: v if v else None),
}


def get_classified_prompts() -> List[Dict[str, Any]]:
    """Fetch all prompts that have been classified."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        SELECT title, file_path,
               intent, task_type, domain, status,
               complexity_level,
               models_tested, last_evaluated, notes
        FROM prompts
        WHERE backfill_status IN ('complete', 'needs_review')
          AND last_classified IS NOT NULL
    """)
    columns = [
        'title', 'file_path',
        'intent', 'task_type', 'domain', 'status',
        'complexity_level',
        'models_tested', 'last_evaluated', 'notes',
    ]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def sync_prompt_to_file(prompt: Dict[str, Any], dry_run: bool = False) -> bool:
    """Merge classified fields into the markdown file's YAML frontmatter."""
    file_path = Path(prompt['file_path'])

    if not file_path.exists():
        logger.warning(f"  SKIP (file missing): {prompt['title']}")
        return False

    try:
        post = frontmatter.load(str(file_path))
    except Exception as e:
        logger.error(f"  ERROR reading {file_path.name}: {e}")
        return False

    # Fields that should be written even when empty (so they appear in Obsidian Base)
    ALWAYS_WRITE = {'models_tested', 'last_evaluated', 'notes'}

    changed = False
    for db_field, (fm_key, transform) in FIELD_MAP.items():
        db_value = prompt.get(db_field)
        if db_value is None and db_field not in ALWAYS_WRITE:
            continue

        new_value = transform(db_value) if db_value is not None else None

        old_value = post.metadata.get(fm_key)

        # Skip if the value is already set and non-empty
        # (don't overwrite manual edits with LLM classifications)
        if old_value is not None and old_value != [] and old_value != '':
            continue

        post.metadata[fm_key] = new_value
        changed = True

    if changed and not dry_run:
        try:
            frontmatter.dump(post, str(file_path))
        except Exception as e:
            logger.error(f"  ERROR writing {file_path.name}: {e}")
            return False

    return changed


def mark_synced(titles: List[str]):
    """Update last_updated in DB so we know these have been synced."""
    if not titles:
        return
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        UPDATE prompts
        SET last_updated = CURRENT_TIMESTAMP
        WHERE title = ANY(%s)
    """, (titles,))
    conn.commit()
    cur.close()
    conn.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Sync DB classifications to Obsidian frontmatter')
    parser.add_argument('--dry-run', action='store_true', help='Show changes without writing files')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of files to sync (0=all)')
    args = parser.parse_args()

    prompts = get_classified_prompts()
    if not prompts:
        logger.info("No classified prompts to sync.")
        return

    logger.info(f"Found {len(prompts)} classified prompts to sync")
    if args.dry_run:
        logger.info("DRY RUN — no files will be modified")

    synced = []
    skipped = 0
    unchanged = 0

    items = prompts[:args.limit] if args.limit else prompts

    for p in items:
        result = sync_prompt_to_file(p, dry_run=args.dry_run)
        if result:
            synced.append(p['title'])
            logger.info(f"  ✓ {p['title']}")
        elif Path(p['file_path']).exists():
            unchanged += 1
        else:
            skipped += 1

    if synced and not args.dry_run:
        mark_synced(synced)

    logger.info(f"\nSync complete: {len(synced)} updated, {unchanged} unchanged, {skipped} skipped (missing files)")


if __name__ == '__main__':
    main()
