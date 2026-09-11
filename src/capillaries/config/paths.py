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
EMBED_MODEL = os.getenv("EMBED_MODEL", "Qwen/Qwen3-Embedding-0.6B")

# Vector width, and the single source of truth for it. The schema pins this in
# four places; they all read from here so a model change is one edit.
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))

# The rerank score below which rank 1 is not worth serving.
#
# The serving floor is deliberately high while automatic injection is driven by
# retrieval alone. It is configurable for replay and calibration work.
# Until 2026-08-18 only the prose said so. Every retrieval surface returned
# rank 1 at whatever it scored, so "Are there any remaining issues here?" came
# back as a confident single prompt at 0.095.
#
# It lives here rather than in find.py because four surfaces need it and two of
# them cannot import each other: find(), agent/route.py (which serves both
# /agent/route and the MCP tools), and the CLI on top of find().
#
# This is a floor, not a fix. It blocks the observed "Set up tier A" false
# positive at 0.704, but high-scoring adjacent matches still need labels before
# the reranker can make a calibrated appropriateness decision.
MIN_CONFIDENCE = float(os.getenv("CAPILLARIES_MIN_CONFIDENCE", "0.8"))


def clears_floor(score: float | None) -> bool:
    """The one serve/refuse decision, so the log and the caller cannot disagree.

    find() applied this floor while search() logged unconditionally one layer
    below it, so serving_log recorded refused candidates as served -- 3,579 rows
    reading as routing wins when the top score could be 1.8e-05. The decision
    lives here now and both layers ask it the same question.
    """
    return score is not None and score >= MIN_CONFIDENCE


# Prepended to queries only — documents are embedded raw. Asymmetric retrieval
# models each want their own convention, so this belongs with the model name
# rather than copied into every call site.
#
# Empty for Qwen3-Embedding, and that is a measured choice, not an oversight.
# The model card offers an "Instruct: {task}\nQuery: {q}" form; on this corpus
# it scored WORSE at every k (notes-as-query recall: 7.3/16.1/24.1% instructed
# vs 8.8/19.5/24.9% plain). The previous model wanted
# "Represent this sentence for searching relevant passages: " — carrying that
# over would have been silently wrong.
QUERY_PREFIX = os.getenv("EMBED_QUERY_PREFIX", "")
