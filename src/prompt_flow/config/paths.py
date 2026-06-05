"""
Centralized path and database configuration for Prompt Flow.

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


def _detect_vault_path() -> Path:
    """Return the Obsidian vault path for the current environment.

    Set OBSIDIAN_VAULT_PATH in your .env file or shell:
      Linux:   OBSIDIAN_VAULT_PATH=/home/<user>/Documents/Obsidian/Main Vault
      Windows: OBSIDIAN_VAULT_PATH=C:/Users/<user>/Obsidian Vaults/Main Vault
      WSL:     OBSIDIAN_VAULT_PATH=/c/Users/<user>/Obsidian Vaults/Main Vault
    """
    env_path = os.getenv("OBSIDIAN_VAULT_PATH")
    if env_path:
        return Path(env_path)

    raise EnvironmentError(
        "OBSIDIAN_VAULT_PATH is not set. "
        "Copy .env.example to .env and fill in your vault path."
    )


OBSIDIAN_VAULT_PATH: Path = _detect_vault_path()
PROMPTS_PATH: Path = OBSIDIAN_VAULT_PATH / "Areas/AI/Prompts"
SKILLS_PATH: Path = OBSIDIAN_VAULT_PATH / "Areas/AI/Skills"
BASE_DB_PATH: Path = OBSIDIAN_VAULT_PATH / "Bases/Prompt Database.base"

# --- Database configuration ---
# Set these in .env (see .env.example). Defaults work for a local PostgreSQL
# install using Unix socket auth (no password).
DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "/var/run/postgresql"),
    "port":     int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "prompt_flow"),
    "user":     os.getenv("DB_USER", ""),
    "password": os.getenv("DB_PASSWORD", ""),
}

# --- Embedding server ---
# Supports any OpenAI-compatible /v1/embeddings endpoint.
# Default: scripts/serve_embeddings.py serving snowflake-arctic-embed-m-v2.0
EMBED_URL = os.getenv("EMBED_URL", "http://127.0.0.1:8003/v1/embeddings")
EMBED_MODEL = os.getenv("EMBED_MODEL", "snowflake-arctic-embed-m-v2.0")
