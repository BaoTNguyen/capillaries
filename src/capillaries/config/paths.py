"""
Centralized path and database configuration for Capillaries.

All environment-specific values (paths, credentials) are loaded from
environment variables. Set these in a .env file (see .env.example) or
export them in your shell — never hardcode them here.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional; env vars can be set externally

_DEFAULT_DATA_DIR = Path.home() / ".capillaries"

# Optional — only needed for Obsidian vault sync (obsidian_sync package).
_vault_env = os.getenv("OBSIDIAN_VAULT_PATH")
OBSIDIAN_VAULT_PATH: Path | None = Path(_vault_env) if _vault_env else None


def _resolve_path(env_key: str, vault_subpath: str, default_name: str) -> Path:
    """Resolve a data path with three-tier fallback.

    1. Explicit env var (e.g. PROMPTS_PATH=/my/prompts)
    2. Derived from OBSIDIAN_VAULT_PATH if set
    3. Default under ~/.capillaries/
    """
    explicit = os.getenv(env_key)
    if explicit:
        return Path(explicit)
    if OBSIDIAN_VAULT_PATH:
        return OBSIDIAN_VAULT_PATH / vault_subpath
    return _DEFAULT_DATA_DIR / default_name


PROMPTS_PATH: Path = _resolve_path("PROMPTS_PATH", "Areas/AI/Prompts", "prompts")
SKILLS_PATH: Path = _resolve_path("SKILLS_PATH", "Areas/AI/Skills", "skills")

# --- Database configuration ---
DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "/var/run/postgresql"),
    "port":     int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "capillaries"),
    "user":     os.getenv("DB_USER", ""),
    "password": os.getenv("DB_PASSWORD", ""),
}

# --- Embedding server ---
EMBED_URL = os.getenv("EMBED_URL", "http://127.0.0.1:8003/v1/embeddings")
EMBED_MODEL = os.getenv("EMBED_MODEL", "snowflake-arctic-embed-m-v2.0")
