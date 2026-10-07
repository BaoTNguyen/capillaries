"""Credentials load from ~/.vascular/secrets/capillaries/env; .env fills the rest.

Each case runs in a fresh subprocess so config.paths' import-time loading
starts clean, with cwd and VASCULAR_HOME pointed into tmp_path.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("dotenv")

SRC = Path(__file__).resolve().parent.parent / "src"
SECRET_KEYS = ("DB_PASSWORD", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")


def _load(tmp_path, key, secrets=None, dotenv=None, shell=None):
    vh = tmp_path / "vh"
    if secrets is not None:
        f = vh / "secrets" / "capillaries" / "env"
        f.parent.mkdir(parents=True)
        f.write_text(f"{key}={secrets}\n")
    if dotenv is not None:
        (tmp_path / ".env").write_text(f"{key}={dotenv}\n")
    env = {k: v for k, v in os.environ.items() if k not in SECRET_KEYS}
    env.update(VASCULAR_HOME=str(vh), HOME=str(tmp_path), PYTHONPATH=str(SRC))
    if shell is not None:
        env[key] = shell
    r = subprocess.run(
        [sys.executable, "-c",
         f"import os, capillaries.config.paths; print(os.environ.get({key!r}))"],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_secrets_file_only(tmp_path):
    assert _load(tmp_path, "OPENAI_API_KEY", secrets="from-secrets") == "from-secrets"


def test_secrets_file_beats_dotenv(tmp_path):
    assert _load(tmp_path, "DB_PASSWORD", secrets="from-secrets", dotenv="from-dotenv") == "from-secrets"


def test_shell_env_beats_both(tmp_path):
    assert _load(tmp_path, "ANTHROPIC_API_KEY", secrets="s", dotenv="d", shell="from-shell") == "from-shell"


def test_missing_secrets_file_falls_back_to_dotenv(tmp_path):
    assert _load(tmp_path, "DB_PASSWORD", dotenv="from-dotenv") == "from-dotenv"
