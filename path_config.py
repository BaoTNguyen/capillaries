"""
Centralized path configuration for Prompt Flow system.
Detects the current OS/environment and selects the appropriate paths.
Windows paths are preserved for WSL usage.
"""

import os
from pathlib import Path

# --- Windows / WSL path ---
WINDOWS_VAULT_PATH = Path("/c/Users/baotn/Obsidian Vaults/Main Vault")

# --- Linux native path ---
LINUX_VAULT_PATH = Path("~/Documents/Obsidian/Main Vault")

def _detect_vault_path() -> Path:
    """Return the vault path appropriate for the current environment."""
    # Honour an explicit override first
    env_path = os.getenv("OBSIDIAN_VAULT_PATH")
    if env_path:
        return Path(env_path)

    # Prefer Linux path when running natively on Linux
    if LINUX_VAULT_PATH.exists():
        return LINUX_VAULT_PATH

    # Fall back to Windows/WSL path
    if WINDOWS_VAULT_PATH.exists():
        return WINDOWS_VAULT_PATH

    # Default to Linux path even if it doesn't exist yet (surfaces a clear error)
    return LINUX_VAULT_PATH


OBSIDIAN_VAULT_PATH: Path = _detect_vault_path()
PROMPTS_PATH: Path = OBSIDIAN_VAULT_PATH / "Areas/AI/Prompts"
BASE_DB_PATH: Path = OBSIDIAN_VAULT_PATH / "Bases/Prompt Database.base"

# --- Database configuration ---
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "/var/run/postgresql"),  # Unix socket — avoids TCP password auth
    "database": os.getenv("DB_NAME", "prompt_flow"),
    "user": os.getenv("DB_USER", "your-db-user"),
    "password": os.getenv("DB_PASSWORD", ""),
}
