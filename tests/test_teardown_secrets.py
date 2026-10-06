"""remove_secrets(): own prompt, never under --force or --dry-run, file only."""
import subprocess
from pathlib import Path

import pytest

TEARDOWN = Path(__file__).resolve().parents[1] / "scripts" / "teardown.sh"


def run(tmp_path, *, dry=False, force=False, answer="", create=True):
    secrets = tmp_path / "vh" / "secrets" / "capillaries" / "env"
    if create:
        secrets.parent.mkdir(parents=True)
        secrets.write_text("API_KEY=x\n")
    script = (f'TEARDOWN_LIB=1 source "{TEARDOWN}"; '
              f'DRY_RUN={str(dry).lower()}; FORCE={str(force).lower()}; remove_secrets')
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "VASCULAR_HOME": str(tmp_path / "vh")}
    r = subprocess.run(["bash", "-c", script], input=answer, env=env, cwd=tmp_path,
                       capture_output=True, text=True, timeout=30)
    return r, secrets


@pytest.mark.parametrize("kw", [{"force": True}, {"dry": True}, {"answer": "n\n"}])
def test_kept(tmp_path, kw):
    r, secrets = run(tmp_path, **kw)
    assert r.returncode == 0, r.stderr
    assert secrets.exists()


def test_force_says_kept(tmp_path):
    r, _ = run(tmp_path, force=True)
    assert "secrets file kept:" in r.stdout


def test_yes_removes_file_only(tmp_path):
    r, secrets = run(tmp_path, answer="y\n")
    assert r.returncode == 0, r.stderr
    assert not secrets.exists()
    assert secrets.parent.is_dir() and (tmp_path / "vh" / "secrets").is_dir()


def test_absent_file(tmp_path):
    r, _ = run(tmp_path, create=False)
    assert r.returncode == 0, r.stderr
