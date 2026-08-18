#!/usr/bin/env python3
"""
Ingest our own (non-public_prompts) skill files into the `prompts` table so
`cap optimize` can target them by title.

`scripts/ingest_public.py` only walks `public_prompts/`, by design — the
capillaries skill at `skills/capillaries/SKILL.md` lives outside that tree
and is a single monolithic file (no step decomposition), so it needs its own
upsert rather than the step-wiring logic ingest_public.py uses for
public_prompts/skills/*.

Usage:
    python scripts/ingest_own_skills.py
"""

import hashlib
import sys
from pathlib import Path

import frontmatter

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Case A, non-public skills eligible for DSPy optimization. Hardcoded, not
# auto-discovered: exactly one entry today, and guessing "is this file an
# optimizable skill" from directory structure alone is the kind of
# classifier that isn't worth building for one file.
OWN_SKILLS = [
    PROJECT_ROOT / "skills" / "capillaries" / "SKILL.md",
]


def ingest() -> None:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    import psycopg2
    from capillaries.config import DB_CONFIG

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    seen_titles = []

    for path in OWN_SKILLS:
        post = frontmatter.load(str(path))
        title = post.metadata.get("name", path.parent.name)
        text = post.content.strip()
        content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]

        # Ingest writes raw truth and nothing derived. A new row arrives with a
        # null embedding; an updated one has its embedding dropped only when the
        # text actually changed, so `setup_db.py --embed` (which fills prompts
        # missing them) regenerates exactly what went stale. Without this the
        # row keeps a vector of the previous text — retrieval matching on
        # content that is no longer there, with nothing to signal it.
        cur.execute("""
            INSERT INTO prompts (title, tag, file_path, prompt_text, source, content_hash, status)
            VALUES (%s, %s, %s, %s, 'own', %s, 'active')
            ON CONFLICT (title) DO UPDATE SET
                prompt_text  = EXCLUDED.prompt_text,
                content_hash = EXCLUDED.content_hash,
                last_updated = CURRENT_TIMESTAMP,
                embedding = CASE
                    WHEN prompts.content_hash IS DISTINCT FROM EXCLUDED.content_hash
                    THEN NULL ELSE prompts.embedding END,
                embedding_version = CASE
                    WHEN prompts.content_hash IS DISTINCT FROM EXCLUDED.content_hash
                    THEN NULL ELSE prompts.embedding_version END
        """, (title, title, str(path.relative_to(PROJECT_ROOT)), text, content_hash))
        seen_titles.append(title)
        print(f"  {title} <- {path.relative_to(PROJECT_ROOT)}")

    # Scoped to source='own' so public/vault-owned rows are never touched by
    # this prune, mirroring ingest_public.py's own-scoped DELETE.
    cur.execute("DELETE FROM prompts WHERE source = 'own' AND NOT (title = ANY(%s))",
                (seen_titles,))
    if cur.rowcount:
        print(f"Pruned {cur.rowcount} own-source prompts no longer in OWN_SKILLS")

    conn.commit()

    cur.execute("SELECT count(*) FROM prompts WHERE source = 'own' AND embedding IS NULL")
    unembedded = cur.fetchone()[0]

    cur.close()
    conn.close()
    print(f"Upserted {len(seen_titles)} own skills")
    if unembedded:
        print(f"\n{unembedded} own prompt(s) have no embedding and cannot be retrieved.")
        print("Run:  PYTHONPATH=src python3 scripts/setup_db.py --embed")


def _demo() -> None:
    """Smallest runnable check: every path in OWN_SKILLS parses as frontmatter
    with a non-empty body, before we ever touch the DB."""
    for path in OWN_SKILLS:
        assert path.exists(), f"missing: {path}"
        post = frontmatter.load(str(path))
        assert post.content.strip(), f"empty body: {path}"
        assert post.metadata.get("name"), f"no `name` in frontmatter: {path}"
    print("ok:", len(OWN_SKILLS), "own skill file(s) valid")


if __name__ == "__main__":
    if "--check" in sys.argv:
        _demo()
    else:
        ingest()
