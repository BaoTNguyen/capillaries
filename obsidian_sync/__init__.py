"""Obsidian vault <-> PostgreSQL sync utilities.

Submodules:
    ingest       — Obsidian -> DB (load .md files, parse frontmatter, insert prompts)
    frontmatter  — DB -> Obsidian (write classifications back to markdown frontmatter)
    skills_vault — DB <-> Obsidian (export/import skills as .md files)
"""

from pathlib import Path

from capillaries.config.paths import OBSIDIAN_VAULT_PATH

BASE_DB_PATH: Path | None = (
    OBSIDIAN_VAULT_PATH / "Bases/Prompt Database.base"
    if OBSIDIAN_VAULT_PATH else None
)

from obsidian_sync.ingest import (
    load_prompts_from_obsidian,
    insert_prompts_batch,
    parse_frontmatter_to_canonical,
    generate_content_hash,
)
from obsidian_sync.frontmatter import (
    get_classified_prompts,
    sync_prompt_to_file,
    mark_synced,
)

__all__ = [
    "BASE_DB_PATH",
    "load_prompts_from_obsidian",
    "insert_prompts_batch",
    "parse_frontmatter_to_canonical",
    "generate_content_hash",
    "get_classified_prompts",
    "sync_prompt_to_file",
    "mark_synced",
]
