"""write_capillaries_secrets() in scripts/setup.sh, run in isolation under tmp_path."""

import os
import re
import stat
import subprocess
from pathlib import Path

SETUP = Path(__file__).resolve().parent.parent / "scripts" / "setup.sh"
TEXT = SETUP.read_text()
START = TEXT.index("write_capillaries_secrets() {")
FUNC = TEXT[START : TEXT.index("\n}\n", START) + 3]
STUBS = 'info(){ echo "$*"; }; success(){ echo "$*"; }; warn(){ echo "$*"; }\n'

SECRETS = {
    "DB_PASSWORD": "pw-Zq81-distinct",
    "ANTHROPIC_API_KEY": "sk-ant-Xy77-distinct",
    "OPENAI_API_KEY": "sk-oai-Wv42-distinct",
}


def run(tmp_path, **values):
    env = {k: v for k, v in os.environ.items() if k not in SECRETS}
    env.update(HOME=str(tmp_path), VASCULAR_HOME=str(tmp_path / "vh"))
    env.update({k: values.get(k, "") for k in SECRETS})
    script = "set -euo pipefail\n" + STUBS + FUNC + "write_capillaries_secrets\n"
    return subprocess.run(
        ["bash", "-c", script], cwd=tmp_path, env=env,
        capture_output=True, text=True, check=True,
    )


def mode(p):
    return stat.S_IMODE(p.stat().st_mode)


def entries(path):
    return [l for l in path.read_text().splitlines() if l and not l.startswith("#")]


def test_all_values_written_private(tmp_path):
    r = run(tmp_path, **SECRETS)
    f = tmp_path / "vh" / "secrets" / "capillaries" / "env"
    assert sorted(entries(f)) == sorted(f"{k}={v}" for k, v in SECRETS.items())
    assert mode(f) == 0o600
    assert mode(f.parent) == 0o700
    assert mode(f.parent.parent) == 0o700
    for v in SECRETS.values():
        assert v not in r.stdout and v not in r.stderr


def test_only_nonempty_keys(tmp_path):
    run(tmp_path, DB_PASSWORD=SECRETS["DB_PASSWORD"])
    f = tmp_path / "vh" / "secrets" / "capillaries" / "env"
    assert entries(f) == [f"DB_PASSWORD={SECRETS['DB_PASSWORD']}"]


def test_all_empty_creates_nothing(tmp_path):
    run(tmp_path)
    assert not (tmp_path / "vh" / "secrets").exists()


def test_existing_file_untouched(tmp_path):
    d = tmp_path / "vh" / "secrets" / "capillaries"
    d.mkdir(parents=True)
    f = d / "env"
    f.write_bytes(b"DB_PASSWORD=old\n")
    f.chmod(0o640)
    r = run(tmp_path, **SECRETS)
    assert f.read_bytes() == b"DB_PASSWORD=old\n"
    assert mode(f) == 0o640
    assert str(f) in r.stdout


def test_dangling_symlink_not_followed(tmp_path):
    d = tmp_path / "vh" / "secrets" / "capillaries"
    d.mkdir(parents=True)
    target = tmp_path / "elsewhere"
    (d / "env").symlink_to(target)
    run(tmp_path, **SECRETS)
    assert not target.exists()
    assert (d / "env").is_symlink()


def test_env_heredoc_has_no_secrets():
    heredoc = re.search(r"<<ENVEOF\n(.*?)\nENVEOF", TEXT, re.S).group(1)
    for k in SECRETS:
        assert f"{k}=$" not in heredoc
