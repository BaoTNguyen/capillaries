"""
Centralized path configuration for Prompt Flow system.
Detects the current OS/environment and selects the appropriate paths.
"""

import os
import sys
from pathlib import Path

# --- Windows native path ---
WINDOWS_VAULT_PATH = Path("C:/Users/baotn/Obsidian Vaults/Main Vault")

# --- WSL path (Windows vault mounted under WSL) ---
# WINDOWS_WSL_VAULT_PATH = Path("/c/Users/baotn/Obsidian Vaults/Main Vault")

# --- Linux native path ---
# LINUX_VAULT_PATH = Path("~/Documents/Obsidian/Main Vault")

def _detect_vault_path() -> Path:
    """Return the vault path appropriate for the current environment."""
    # Honour an explicit override first
    env_path = os.getenv("OBSIDIAN_VAULT_PATH")
    if env_path:
        return Path(env_path)

    # Windows native
    if sys.platform == "win32":
        return WINDOWS_VAULT_PATH

    # Uncomment to support Linux native:
    # if LINUX_VAULT_PATH.exists():
    #     return LINUX_VAULT_PATH

    # Uncomment to support WSL:
    # if WINDOWS_WSL_VAULT_PATH.exists():
    #     return WINDOWS_WSL_VAULT_PATH

    # Default to Windows path (surfaces a clear error if it doesn't exist)
    return WINDOWS_VAULT_PATH


OBSIDIAN_VAULT_PATH: Path = _detect_vault_path()
PROMPTS_PATH: Path = OBSIDIAN_VAULT_PATH / "Areas/AI/Prompts"
BASE_DB_PATH: Path = OBSIDIAN_VAULT_PATH / "Bases/Prompt Database.base"

# --- Database configuration ---
# Windows uses TCP; Linux/WSL can use a Unix socket ("/var/run/postgresql")
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "prompt_flow"),
    "user": os.getenv("DB_USER", "baotn"),
    "password": os.getenv("DB_PASSWORD", ""),
}
